# ADR-002: In-Process EventEmitter over Redis Pub/Sub for Single-Station Deployments

## Status

**Accepted** (July 2026)

**Go port note (September 2026):** [ADR-006](adr-006-go-rewrite-and-station-consolidation.md) re-expresses this decision for a Go implementation. `EventEmitter`'s synchronous, exception-isolating delivery is not a property of Go channels; the delivery model must be specified explicitly — see [go-migration.md §R-2](../development/go-migration.md).

## Context

The original hermes-backend architecture used **Redis Pub/Sub** as the internal event bus for decoupling modules and powering the WebSocket realtime gateway. This pattern is well-established for multi-process, multi-node deployments.

However, the sBitx v2 deployment runs a **single Node.js process** on a Raspberry Pi 4 with 4 GB RAM. Redis adds:

- **80–300 MB memory overhead** (AOF persistence doubles this temporarily)
- **A daemon process** that must be monitored and managed
- **A single point of failure** (if Redis crashes, the event bus is lost)
- **Additional SD card writes** (AOF/RDB persistence)

When all publishers and subscribers reside in the same process, an external message broker provides no architectural benefit — it only adds operational complexity and memory pressure.

## Decision

**Use Node.js `EventEmitter` (or a thin typed wrapper) as the in-process event bus** for sBitx v2 single-station deployments. Redis Pub/Sub remains available as a swap-in adapter for multi-process server deployments.

### Architecture

```typescript
// src/events/bus.ts
import { EventEmitter } from "node:events";

// Typed event map
interface HermesEvents {
  "radio:telemetry": [telemetry: TelemetrySnapshot];
  "message:new": [message: Message, conversationId: string];
  "message:delivered": [delivery: MessageDelivery];
  "message:read": [conversationId: string, userId: string];
  "typing:start": [conversationId: string, userId: string];
  "typing:stop": [conversationId: string, userId: string];
  "presence:update": [userId: string, status: "online" | "offline" | "away"];
}

class TypedEventBus extends EventEmitter {
  emit<E extends keyof HermesEvents>(event: E, ...args: HermesEvents[E]): boolean {
    return super.emit(event, ...args);
  }

  on<E extends keyof HermesEvents>(event: E, listener: (...args: HermesEvents[E]) => void): this {
    return super.on(event, listener);
  }
}

export const bus = new TypedEventBus();
bus.setMaxListeners(50); // Reasonable limit for the number of module subscribers
```

### Event Flow (In-Process)

```
┌─────────────┐   emit("message:new", msg, convId)   ┌───────────────┐
│  Messaging   │────────────────────────────────────▶ │  Event Bus    │
│  Domain      │                                      │  (EventEmitter)│
└─────────────┘                                      └───────┬───────┘
                                                             │
                    ┌────────────────────────────────────────┼──────────────────────────┐
                    │                                        │                          │
                    ▼                                        ▼                          ▼
          ┌─────────────────┐                    ┌──────────────────┐      ┌──────────────────┐
          │ WebSocket       │                    │  Audit Logger    │      │  Sync Queue      │
          │ Gateway         │                    │  (writes to DB)  │      │  (enqueue for    │
          │ (push to client)│                    │                  │      │   offline devices)│
          └─────────────────┘                    └──────────────────┘      └──────────────────┘
```

## Consequences

### Positive

- **Zero memory overhead**: EventEmitter is a built-in Node.js primitive with negligible memory cost
- **Zero configuration**: No Redis installation, connection strings, or authentication
- **Zero operational complexity**: No daemon to monitor, restart, or troubleshoot
- **Synchronous delivery**: Events are delivered to all listeners within the same tick (no network serialization)
- **Type safety**: Typed events are enforced at compile time
- **Simplified debugging**: Stack traces include the emitter; no "which process published this?" confusion

### Negative

- **No multi-process scaling**: If the system is split into multiple Node.js processes (e.g., worker threads for CPU-intensive tasks), in-process events won't cross process boundaries. Migration path: swap to Redis via a `EventBusAdapter` interface.
- **No persistence**: Events are fire-and-forget. If a listener is not registered when an event fires, it misses the event. This is acceptable for realtime notifications; critical events (messages, audit logs) are persisted to SQLite by their respective modules independently of the event bus.
- **No retry/ack semantics**: Unnecessary — the WebSocket gateway is the only realtime consumer; if it misses an event, the client's next sync will catch up.

### Event Bus Adapter Interface

```typescript
// src/events/adapter.ts
interface EventBusAdapter {
  emit(event: string, ...args: unknown[]): Promise<void>;
  on(event: string, listener: (...args: unknown[]) => void): void;
  off(event: string, listener: (...args: unknown[]) => void): void;
}

class InProcessEventBus implements EventBusAdapter { /* EventEmitter */ }
class RedisEventBus implements EventBusAdapter { /* Redis Pub/Sub — future */ }
```

## Alternatives Considered

### Redis Pub/Sub
Rejected for single-station Pi 4 deployments: 80–300 MB RAM, daemon process, single point of failure, no benefit for in-process communication.

### RabbitMQ / NATS
Rejected: Requires an external broker daemon, excessive for a single-process application.

### EventEmitter with external persistence (e.g., event sourcing to SQLite)
Rejected: Over-engineering. Events that need persistence (messages, audit logs) are written directly to SQLite by their respective modules. The event bus is purely for realtime notification, not for durability.

### No event bus (direct function calls)
Rejected: Tight coupling between the messaging domain and the WebSocket gateway would make the WebSocket module impossible to test in isolation. The event bus provides a clean seam for testing and future replacement.

## References

- [Node.js EventEmitter Documentation](https://nodejs.org/api/events.html)
- [docs/websocket.md](../architecture/websocket.md) — WebSocket realtime gateway design
- [README.md](../../README.md) — Architecture diagram showing event bus integration