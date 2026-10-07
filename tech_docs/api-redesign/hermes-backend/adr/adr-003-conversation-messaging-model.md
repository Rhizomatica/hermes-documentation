# ADR-003: Conversation-Based Messaging Model over Inbox/Outbox

## Status

**Accepted** (July 2026)

## Context

The legacy hermes-api (PHP/Lumen) used a traditional **inbox/outbox** messaging model: messages are sent to a recipient's "inbox" and appear in the sender's "outbox." This model is familiar from email but has significant limitations for real-time, multi-participant communication over HF radio:

- **No concept of groups**: An inbox is inherently 1-to-1. Supporting group messaging requires workarounds (duplicate messages to each recipient's inbox).
- **No message threading**: Inbox/outbox conflates all message types into flat lists.
- **No delivery tracking per recipient**: You know a message was sent, but not whether each individual recipient received it over HF vs email vs WebSocket.
- **Difficult offline sync**: Syncing an inbox requires fetching messages in insertion order; there's no natural cursor for "what changed in this conversation since my last sync."
- **No participant management**: Adding/removing participants from an ongoing discussion requires reconstructing context.

Modern messaging applications (WhatsApp, Signal, Telegram, Matrix) have converged on a **conversation-based model** for good reason — it's more intuitive for users and simpler to implement correctly.

## Decision

**Use conversations as the central messaging entity.** Messages belong to conversations, not to inboxes. Delivery is tracked per-recipient per-channel via a `message_deliveries` table.

### Core Data Model

```
┌──────────────────┐       ┌──────────────────────────┐
│  conversations   │       │  conversation_participants │
│──────────────────│       │──────────────────────────│
│ id (UUID)        │──┐    │ conversation_id (FK)      │
│ type             │  │    │ user_id (FK)               │
│ title            │  └───▶│ joined_at                  │
│ created_by (FK)  │       │ role                       │
│ created_at       │       │ last_read_event_sequence   │
│ updated_at       │       └──────────────────────────┘
└──────────────────┘
         │
         │ 1:N
         ▼
┌──────────────────┐       ┌──────────────────────────┐
│  messages        │       │  message_deliveries       │
│──────────────────│       │──────────────────────────│
│ id (UUID)        │──┐    │ message_id (FK)           │
│ conversation_id  │  │    │ user_id (FK)              │
│ sender_id (FK)   │  └───▶│ channel (HF/email/ws)     │
│ content          │       │ status                     │
│ client_message_id│       │ delivered_at               │
│ event_sequence   │       │ read_at                    │
│ created_at       │       └──────────────────────────┘
│ edited_at        │
│ deleted_at       │
└──────────────────┘
```

### Conversation Types

| Type | Max Participants | Example |
|------|:---:|---------|
| `direct` | 2 | Person-to-person chat |
| `group` | 50 | Team coordination channel |
| `broadcast` | 200 | Station-wide announcements |

### Delivery Tracking

Each message generates a `message_deliveries` row for each participant, per channel:

```
Message "Meet at 14:00" sent in conversation #conv-1 (3 participants: A, B, C)
  ├── delivery: user=A, channel=ws     → delivered (WebSocket, online)
  ├── delivery: user=B, channel=hf     → pending  (HF radio, awaiting next schedule)
  ├── delivery: user=B, channel=ws     → pending  (WebSocket, offline)
  └── delivery: user=C, channel=ws     → delivered (WebSocket, online)
```

This enables:
- Per-recipient read receipts
- Per-channel delivery status (HF might succeed while WebSocket is pending)
- Offline queuing: when user B reconnects via WebSocket, undelivered messages are pushed
- Audit trail: who received what, when, and via which channel

## Consequences

### Positive

- **Intuitive UX**: Conversations match user expectations from modern messaging apps
- **Natural group support**: Adding participants to a conversation is a single operation
- **Fine-grained delivery tracking**: Know exactly which recipients got the message and via which channel
- **Simple reconnection**: Clients that disconnect simply fetch current state via the REST API on reconnect — no cursor-based sync needed
- **Thread-ready**: Future support for message threading (reply chains) maps naturally to the conversation model
- **Reactions**: Reactions are per-message within a conversation — no inbox fragmentation

### Negative

- **Breaking change from legacy API**: The legacy `GET /messages/inbox` and `GET /messages/outbox` endpoints must be shimmed (see Phase 8, tasks D8.7–D8.8)
- **More complex queries**: "List all my conversations with last message and unread count" is the critical query that must be optimized (see `docs/database.md` for the optimized query design)
- **Higher storage**: `message_deliveries` rows grow as `participants × channels` per message. At 10 messages/day, 3 participants, 2 channels = 60 rows/day — negligible for SQLite

### Legacy Compatibility Shim

Phase 8 includes backward compatibility for legacy clients:

```typescript
// GET /messages/inbox → maps to conversation list query
// GET /messages/outbox → maps to sent messages query
// GET /messages/:id   → direct message lookup (message may belong to any conversation)
```

These endpoints are read-only shims. New messages are always created via the conversation API.

## Alternatives Considered

### Inbox/Outbox Model (legacy)
Rejected: Insufficient for group messaging, poor offline sync semantics, no natural delivery tracking per recipient.

### ActivityPub / Fediverse Model
Rejected: Over-engineered for single-station deployments. The federation protocol (Phase 10) will use a station-to-station sync protocol over HF, not ActivityPub.

### Matrix Protocol
Rejected: Requires a homeserver process (Synapse, ~200–500 MB RAM). Too heavy for Raspberry Pi 4. The conversation model is Matrix-inspired but implemented directly in the application layer.

## References

- [docs/api.md](../architecture/api.md) §4 — Conversation and messaging endpoints
- [docs/database.md](../architecture/database.md) §4–7 — Conversation, message, and delivery tables
- Signal Protocol Design — Inspiration for conversation-based messaging with per-recipient delivery tracking