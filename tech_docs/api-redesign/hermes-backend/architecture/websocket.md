# WebSocket Realtime Gateway — Hermes Backend

## Overview

The WebSocket gateway provides realtime event streaming to connected clients (browser UI on phone/laptop). Since the hermes-backend runs on a **Raspberry Pi 4** that clients access via **local WiFi hotspot**, all state lives on the Pi as the single source of truth. The WebSocket pushes realtime events; the REST API is the authoritative data access layer. There is no offline sync protocol — clients that disconnect simply fetch current state via REST on reconnection.

## Deployment Model

```
┌─────────────────────────────────────────────────────────┐
│                 Raspberry Pi (sBitx v2)                  │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │ hermes-backend│  │ radio-daemon │  │ hermes-gui    │ │
│  │ (Node.js API) │  │ (TX/RX over  │  │ (static files)│ │
│  │               │  │  HF Radio)   │  │               │ │
│  └──────┬───────┘  └──────────────┘  └───────────────┘ │
│         │                                                │
│         │  WiFi Hotspot (local only, no internet)        │
└─────────┼────────────────────────────────────────────────┘
          │
    ┌─────┴─────┐     ┌──────────┐
    │ Phone     │     │ Laptop   │
    │ (browser) │     │ (browser)│
    └───────────┘     └──────────┘
```

**Key principle**: The browser client is a **window into the Pi's state**, not an independent state holder. When the WebSocket disconnects (WiFi drop, browser tab closed, phone screen off), the client state is stale — on reconnect, the client fetches current state from the REST API and resumes receiving realtime pushes.

## Protocol Specification

### Connection

Connect to the WebSocket endpoint with the `hermes-v1` subprotocol:

```
ws://localhost:3000/gateway
wss://sbitx.local:3000/gateway  (production)

Subprotocols: hermes-v1
```

### Message Format

All messages are JSON-encoded with a `type` field:

```json
{
  "type": "MESSAGE_TYPE",
  "timestamp": "2026-07-27T15:30:00.000Z",
  "payload": { }
}
```

### Authentication Flow

```
Client                          Server
  │                                │
  │  CONNECT (hermes-v1)           │
  │──────────────────────────────▶ │
  │                                │ 10-second auth timeout starts
  │                                │
  │  AUTHENTICATE                  │
  │  { token: "<access_token>" }   │
  │──────────────────────────────▶ │
  │                                │ Verify JWT RS256 signature
  │                                │ Check expiry, RBAC claims
  │  AUTHENTICATED                 │
  │  { userId, callsign, role,     │
  │    locale, sessionId,          │
  │    serverTime, connectionId }  │
  │◀────────────────────────────── │
  │                                │
  │  SUBSCRIBE                     │
  │  { topics: ["conversation:*",  │
  │    "radio:telemetry"] }        │
  │──────────────────────────────▶ │
  │                                │
  │  SUBSCRIBED                    │
  │  { topics: [...] }             │
  │◀────────────────────────────── │
```

If the client does not send `AUTHENTICATE` within 10 seconds, the server closes the connection with code `4001` (auth timeout).

### Client → Server Messages

| Type | Description | Payload |
|------|-------------|---------|
| `AUTHENTICATE` | Authenticate with JWT | `{ token: string }` |
| `SUBSCRIBE` | Subscribe to topics | `{ topics: string[] }` |
| `UNSUBSCRIBE` | Unsubscribe from topics | `{ topics: string[] }` |
| `PING` | Heartbeat | `{ }` |

### Server → Client Messages

| Type | Description | Payload |
|------|-------------|---------|
| `AUTHENTICATED` | Auth successful | `{ userId, callsign, role, locale, serverTime, connectionId }` |
| `SUBSCRIBED` | Subscription confirmed | `{ topics: string[] }` |
| `ERROR` | Error occurred | `{ code: number, message: string }` |
| `PONG` | Heartbeat response | `{ serverTime }` |
| `MESSAGE_NEW` | New message in conversation | `{ message, conversationId }` |
| `MESSAGE_EDITED` | Message was edited | `{ message, conversationId }` |
| `MESSAGE_DELETED` | Message was soft-deleted | `{ messageId, conversationId }` |
| `MESSAGE_DELIVERED` | Delivery confirmed | `{ messageId, userId, channel }` |
| `MESSAGE_READ` | Messages were read | `{ conversationId, userId, readUpTo }` |
| `TYPING_START` | User started typing | `{ conversationId, userId }` |
| `TYPING_STOP` | User stopped typing | `{ conversationId, userId }` |
| `PRESENCE_UPDATE` | User presence changed | `{ userId, status }` |
| `RADIO_TELEMETRY` | Radio telemetry snapshot | `{ frequency, power, swr, ... }` |
| `RADIO_STATUS` | Radio connection changed | `{ connected }` |
| `STALE_CONNECTION` | Connection will close; client must reconnect and fetch state via REST | `{ reason: string }` |

## Topics

Topics use a hierarchical format with wildcards:

| Topic | Description | Push Rate |
|-------|-------------|:---:|
| `radio:telemetry` | Radio telemetry snapshots | 1 Hz |
| `radio:status` | Radio connection/disconnection | Event-driven |
| `conversation:*` | All conversation events for user's conversations | Event-driven |
| `conversation:{id}` | Events for a specific conversation | Event-driven |
| `presence:station` | User presence for the entire station | Event-driven |
| `system:announcement` | System-wide announcements | Event-driven |

## Reconnection Flow

When a client disconnects (WiFi drop, browser tab closed, phone screen off) and later reconnects, it fetches current state from the REST API — the WebSocket only pushes new events going forward:

```
Client                          Server
  │                                │
  │  CONNECT → AUTHENTICATE        │
  │  → SUBSCRIBE                   │
  │◀────────────────────────────── │ WebSocket ready — receiving realtime pushes
  │                                │
  │  REST: GET /conversations      │ ← Fetch current conversation list
  │──────────────────────────────▶ │
  │◀────────────────────────────── │
  │                                │
  │  REST: GET /conversations/:id  │ ← Fetch messages for active conversation
  │  /messages                     │
  │──────────────────────────────▶ │
  │◀────────────────────────────── │
  │                                │
  │  [New messages pushed via      │ ← WebSocket handles future events
  │   WebSocket in real time]      │
```

**Why no sync protocol**: Since the hermes-backend is the **single source of truth** (all data lives in SQLite on the Pi), a client that disconnects doesn't accumulate local changes. On reconnect, fetching current state via REST is simpler, more reliable, and eliminates the need for cursor management, delta batching, and conflict resolution.

## Heartbeat

```
Every 30 seconds:
  Client → Server: PING
  Server → Client: PONG { serverTime }

If no PING received in 60 seconds: Server closes connection (code 4002, heartbeat timeout)
```

## Connection Limits

| Limit | Value | Behavior |
|-------|:---:|----------|
| Max concurrent connections | 20 | New connection rejected with `4006` if exceeded |
| Auth timeout | 10 seconds | Connection closed with code `4001` |
| Heartbeat timeout | 60 seconds | Connection closed with code `4002` |
| Max topic subscriptions | 50 | Additional `SUBSCRIBE` messages rejected |
| TYPING_START rate limit | 1 per 2 seconds | Duplicate events dropped silently |

## Error Codes

| Code | Name | Description |
|:---:|------|-------------|
| `4001` | AUTH_TIMEOUT | Client did not authenticate within 10 seconds |
| `4002` | HEARTBEAT_TIMEOUT | No PING received in 60 seconds |
| `4003` | INVALID_TOKEN | JWT verification failed |
| `4004` | TOKEN_EXPIRED | JWT access token is expired |
| `4005` | INSUFFICIENT_PERMISSIONS | User role doesn't have WebSocket access |
| `4006` | CONNECTION_LIMIT_REACHED | Server at max 20 concurrent connections |
| `4007` | SUBSCRIPTION_LIMIT_REACHED | Client exceeded 50 topic subscriptions |
| `4008` | UNKNOWN_MESSAGE_TYPE | Server received unrecognized message type |
| `4009` | RATE_LIMITED | Client sent too many messages |
| `4010` | SLOW_CLIENT | Client send buffer exceeded; events dropped; reconnect required |

## Implementation Notes

- The WebSocket gateway uses `@fastify/websocket` (which wraps `ws` library)
- Each connection runs in its own async context
- Event bus subscription is set up after `SUBSCRIBE`; cleaned up on disconnect
- **Backpressure**: If a client's send buffer exceeds 64 KB, the server sends `STALE_CONNECTION` and closes the connection with code `4010`. The client must reconnect and fetch current state via REST. State-changing events (`MESSAGE_NEW`, `MESSAGE_DELETED`, etc.) are never silently dropped.
- **Informational events** (`RADIO_TELEMETRY`, `TYPING_*`) may be dropped under backpressure — the next telemetry snapshot replaces the dropped one
- Radio telemetry (1 Hz) is pushed to all subscribers of `radio:telemetry` via the in-process event bus (see [ADR-002](../adr/adr-002-in-process-event-bus.md))

## TypeScript Types

```typescript
// src/gateway/types.ts

interface HermesWebSocketMessage {
  type: string;
  timestamp?: string;
  payload?: Record<string, unknown>;
}

interface AuthMessage extends HermesWebSocketMessage {
  type: "AUTHENTICATE";
  payload: { token: string };
}

interface SubscribeMessage extends HermesWebSocketMessage {
  type: "SUBSCRIBE";
  payload: { topics: string[] };
}

// Server → Client

interface AuthenticatedMessage extends HermesWebSocketMessage {
  type: "AUTHENTICATED";
  payload: { userId: string; callsign: string; role: string; locale: string; serverTime: string; connectionId: string };
}

interface RadioTelemetryMessage extends HermesWebSocketMessage {
  type: "RADIO_TELEMETRY";
  payload: {
    frequency: number;
    power: number;
    swr: number;
    temperature: number;
    mode: string;
    timestamp: string;
  };
}
```

## References

- [RFC 6455 — The WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455)
- [ADR-002 — In-Process Event Bus](../adr/adr-002-in-process-event-bus.md)
- [REST API Spec](api.md) — Authoritative data access layer for state retrieval on reconnection