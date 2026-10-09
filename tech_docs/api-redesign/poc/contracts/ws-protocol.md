# HERMES WebSocket Protocol — `hermes-v1`

Contract for the realtime gateway. Pushed state travels here; stored state
travels over REST (`openapi.yaml`). One protocol, one envelope, one auth flow —
shared by the radio/modem daemons and the backend gateway.

Status: draft POC — structure only.

## Endpoint

```
wss://sbitx.local/gateway
Subprotocols: hermes-v1
```

The gateway authenticates, then relays topics from the in-process event bus
(ADR-002) to subscribed clients. The browser is a window into the station's
state, not an independent holder: on reconnect it fetches current state via
REST and resumes pushes.

## Envelope

Every message (both directions) is JSON:

```json
{
  "type": "MESSAGE_TYPE",
  "requestId": "optional-client-correlation-id",
  "payload": {},
  "timestamp": "2026-07-17T12:00:00.000Z",
  "version": 1
}
```

| Field | Direction | Meaning |
| --- | --- | --- |
| `type` | both | Message/event type (see tables) |
| `requestId` | client→server, echoed | Correlation for request/response pairs |
| `payload` | both | Type-specific body |
| `timestamp` | both | ISO 8601 UTC |
| `version` | both | Protocol version, always `1` |

## Connection & auth flow

```
Client                                    Server
  │  CONNECT (subprotocol: hermes-v1)       │
  │───────────────────────────────────────▶ │  10s auth timeout starts
  │  AUTHENTICATE { token }                 │
  │───────────────────────────────────────▶ │  verify JWT RS256 + RBAC claims
  │  AUTHENTICATED { userId, callsign,      │
  │                  role, locale,          │
  │                  connectionId }         │
  │◀─────────────────────────────────────── │
  │  SUBSCRIBE { topics: [...] }            │
  │───────────────────────────────────────▶ │
  │  SUBSCRIBED { topics: [...] }           │
  │◀─────────────────────────────────────── │
```

## Client → Server

| Type | Payload | Notes |
| --- | --- | --- |
| `AUTHENTICATE` | `{ token }` | JWT access token |
| `SUBSCRIBE` | `{ topics: string[] }` | Max 50 topics |
| `UNSUBSCRIBE` | `{ topics: string[] }` | |
| `PING` | `{}` | Heartbeat every 30 s |
| `SYNC_REQUEST` | `{ cursors }` | Reconnect catch-up |
| `RADIO_COMMAND` | `{ command, ... }` | Rate-limited 10/min |

## Server → Client

| Type | Description |
| --- | --- |
| `AUTHENTICATED` | Auth accepted |
| `SUBSCRIBED` | Subscription confirmed |
| `PONG` | `{ serverTime }` |
| `RADIO_TELEMETRY` | Full radio state snapshot (1 Hz) |
| `RADIO_STATE_CHANGE` | PTT / connection / protection change |
| `MESSAGE_NEW` / `MESSAGE_UPDATED` / `MESSAGE_DELETED` | Message lifecycle |
| `MESSAGE_DELIVERED` / `MESSAGE_READ` | Delivery / read receipts |
| `REACTION_ADDED` / `REACTION_REMOVED` | Reactions |
| `TYPING_START` / `TYPING_STOP` | Typing indicators |
| `PRESENCE_UPDATE` | User online/offline/away |
| `SYNC_DELTA` / `SYNC_COMPLETE` / `SYNC_SUMMARY` | Reconnect sync |
| `SYSTEM_NOTIFICATION` | System-level notice |
| `CLOCK_SYNCED` | Clock synced (GPS/manual) |
| `ERROR` | `{ code, message }` |

## Topics

Wildcard subscriptions, role-gated:

| Topic | Content | Gate |
| --- | --- | --- |
| `radio:telemetry` | 1 Hz telemetry snapshots | user+ |
| `radio:spectrum` | Binary spectrum frames | user+ |
| `radio:command` | Command responses | operator+ |
| `conversation:*` | Conversation-scoped events | participant |
| `message:*` | Message lifecycle | participant |
| `typing:*` | Typing indicators | participant |
| `presence:*` | Presence changes | user+ |
| `system:*` | Notifications, clock | user+ |
| `webrtc.<sessionId>` | Voice signaling (gated `ENABLE_WEBRTC`) | participant |

## Heartbeat & limits

| Rule | Value |
| --- | --- |
| PING interval | 30 s |
| Heartbeat timeout | 60 s (close `4002`) |
| Auth timeout | 10 s (close `4001`) |
| Max connections | 20 (reject `4006`) |
| Max topics | 50 (reject `4007`) |
| RADIO_COMMAND rate | 10 / min |

## Error codes

| Code | Name |
| --- | --- |
| `4001` | AUTH_TIMEOUT |
| `4002` | HEARTBEAT_TIMEOUT |
| `4003` | INVALID_TOKEN |
| `4004` | TOKEN_EXPIRED |
| `4005` | INSUFFICIENT_PERMISSIONS |
| `4006` | CONNECTION_LIMIT_REACHED |
| `4007` | SUBSCRIPTION_LIMIT_REACHED |
| `4008` | UNKNOWN_MESSAGE_TYPE |
| `4009` | RATE_LIMITED |
| `4010` | SLOW_CLIENT |

## Backpressure & reconnect

- Send buffer > 64 KB → server sends `STALE_CONNECTION` and closes `4010`.
  The client must reconnect and fetch state via REST.
- State-changing events (`MESSAGE_*`, delivery) are never dropped.
- Informational events (`RADIO_TELEMETRY`, `TYPING_*`) may be dropped; the next
  snapshot replaces the lost one.
- On reconnect the client authenticates, then issues `SYNC_REQUEST`; the server
  replies `SYNC_DELTA` batches or a `SYNC_SUMMARY` when missed events > 500.

## References

- `hermes-backend/architecture/websocket.md` — full gateway design
- `hermes-backend/adr/adr-002-in-process-event-bus.md` — event bus
- `openapi.yaml` — REST contract (authoritative state on reconnection)
