# ADR-005: Conflict Resolution Strategy — Single Source of Truth Model

## Status

**Accepted** (July 2026)

**Go port note (September 2026):** [ADR-006](adr-006-go-rewrite-and-station-consolidation.md) re-expresses this decision for a Go implementation. The serialization assumption this ADR depends on ("the event loop serializes writes") is no longer automatic; it becomes an explicit single-writer-connection guarantee. Without it, "last writer wins" is nondeterministic — see [go-migration.md §R-1](../development/go-migration.md).

## Context

The hermes-backend runs on a **Raspberry Pi 4** accessed via local WiFi hotspot. Clients (browser on phone/laptop) connect to the Pi directly. All data lives in SQLite on the Pi — the server is the **single source of truth**. There is no offline sync protocol or multi-device replication.

Despite this, concurrent operations can still occur:
- Two browser tabs editing the same message simultaneously
- One user deleting a message while another edits it
- Two users adding reactions to the same message at the same time
- A client sending a message while the server is processing a deletion of the conversation

These conflicts occur within the same process (Node.js event loop serializes writes), but the **logical conflict** still needs a defined resolution strategy.

## Decision

**Last-writer-wins with explicit priority rules.** Since all writes are serialized by the Node.js event loop and SQLite's single-writer, we can use `updated_at` as a deterministic tiebreaker. Higher-priority operations (deletion) always win regardless of timing.

### Core Rules

| Operation | Priority | Resolution |
|-----------|:---:|------------|
| **Deletion** (soft delete) | Highest | Always wins over edits. If message A is soft-deleted at T2 and edited at T1, the deletion stands. `deleted_at` is set, `content` is NULLed. |
| **Edit** (content update) | Medium | Last `updated_at` wins. Earlier edits are silently discarded. The client that lost the race receives the current server state (not an error). |
| **Reaction** (add/remove) | Lowest | Union semantics — no conflict possible. Multiple users adding different reactions to the same message is additive. Same user+emoji combination is idempotent (UNIQUE constraint). |
| **Message creation** | N/A | Idempotent via `client_message_id`. Duplicate submissions return the existing message. No conflict with other operations — creation is append-only. |
| **Conversation archival** | N/A | Additive — once archived, stays archived. Unarchiving is a separate explicit endpoint (`POST /conversations/:id/unarchive`). |

### Detailed Scenarios

#### 1. Two clients edit the same message

```
Timeline:
  T1: Client A edits message M → sets content="Hello World", updated_at=2026-07-17T12:00:01Z
  T2: Client B edits message M → sets content="Goodbye World", updated_at=2026-07-17T12:00:02Z
  T3: Client A refreshes → sees content="Goodbye World"
```

**Resolution**: Client B's edit wins (later `updated_at`). Client A's edit is silently discarded. Client A receives the latest state via their next REST fetch or WebSocket `MESSAGE_EDITED` event.

#### 2. Client A deletes while Client B edits

```
Timeline:
  T1: Client A soft-deletes message M → sets deleted_at=2026-07-17T12:00:01Z, content=NULL
  T2: Client B edits message M → request arrives after deletion
```

**Resolution**: The server checks `deleted_at IS NOT NULL` before applying edits. If the message is deleted, the edit is rejected with `409 CONFLICT { code: "MESSAGE_DELETED" }`. The client that attempted the edit is notified and their UI updates to show the deletion.

#### 3. Simultaneous reactions

```
Timeline:
  T1: Client A reacts with 👍 on message M
  T2: Client B reacts with ❤️ on message M
  T3: Client A tries to react with 👍 again
```

**Resolution**: Both reactions coexist (different emoji). The duplicate 👍 attempt is a no-op (UNIQUE constraint on `message_id, user_id, emoji` prevents duplicates — no error, returns 200 with existing reaction).

#### 4. Client sends message to deleted conversation

```
Timeline:
  T1: Admin archives conversation C (sets archived_at)
  T2: Client sends message to conversation C
```

**Resolution**: Archived conversations accept no new messages. The server returns `422 UNPROCESSABLE_ENTITY { code: "CONVERSATION_ARCHIVED" }`.

### What We Don't Handle

- **Concurrent conversation creation with same participants**: Two users creating a `direct` conversation with the same participant pair. The second request returns `409 CONFLICT { code: "CONVERSATION_EXISTS", existingId: "uuid" }` — the server checks for existing direct conversations before creating a new one.
- **Participant removal during message send**: If a participant is removed from a group conversation while someone is typing, the message send will fail with `403 FORBIDDEN { code: "NOT_PARTICIPANT" }`. The sender must be re-added before sending.

## Consequences

### Positive

- **Simple to implement**: No CRDT library, no operational transform, no vector clocks needed.
- **Deterministic**: Every developer can predict the outcome of any concurrent operation without analyzing complex merge logic.
- **Consistent with deployment model**: Single source of truth means there's always one authoritative state.
- **User-friendly**: Failed operations return clear error codes so the UI can display appropriate messages ("This message was deleted", "Conversation was archived").

### Negative

- **Last-writer-wins data loss**: If Client A makes a meaningful edit and Client B makes a trivial edit 1 second later, Client A's edit is lost without notification. Mitigation: the UI shows "edited" timestamp, so Client A can see their edit was superseded.
- **Not suitable for multi-station federation**: In Phase 10+ (federation), a conflict-free replicated data type (CRDT) approach will be needed. This ADR explicitly limits its scope to single-station deployments.
- **No merge**: Edits are wholesale replacements, not merges. If two users add different paragraphs to the same message, one wins entirely. Acceptable for HF radio messaging (short text, not collaborative document editing).

## Implementation Notes

### Database-Level Enforcement

```sql
-- Edit operation (in repository layer):
UPDATE messages 
SET content = :newContent, 
    edited_at = :now,
    updated_at = :now
WHERE id = :messageId 
  AND deleted_at IS NULL;          -- Don't edit deleted messages
  -- Note: No updated_at check needed — SQLite serializes writes.
  -- The "last" write in event loop order is the winner.

-- Delete operation:
UPDATE messages
SET content = NULL,
    deleted_at = :now,
    updated_at = :now
WHERE id = :messageId;
  -- Deletion always succeeds regardless of concurrent edits.
  -- The content NULL and deleted_at are set atomically.
```

### API-Level Responses

| Scenario | HTTP Status | Response Body |
|----------|:---:|---------------|
| Edit succeeds | 200 | `{ id, content, editedAt }` |
| Edit on deleted message | 409 | `{ code: "MESSAGE_DELETED" }` |
| Delete succeeds | 200 | `{ id, deletedAt }` |
| Send to archived conversation | 422 | `{ code: "CONVERSATION_ARCHIVED" }` |
| Send as non-participant | 403 | `{ code: "NOT_PARTICIPANT" }` |
| Duplicate reaction | 200 | Existing reaction object (idempotent) |
| Duplicate conversation | 409 | `{ code: "CONVERSATION_EXISTS", existingId }` |

### Client Responsibilities

1. After receiving `409 MESSAGE_DELETED`, the client fetches the conversation messages to update its UI state.
2. After receiving a `MESSAGE_EDITED` WebSocket event, the client replaces its local copy with the server's version.
3. The client should debounce rapid edits — the server processes writes in order, but a user typing fast doesn't need to send an edit on every keystroke.

## Future: Multi-Station Federation (Phase 10+)

When the system evolves to support multiple stations synchronizing over HF radio, the conflict resolution strategy must be revisited:

- **Last-writer-wins is insufficient** when two stations have been operating independently for hours/days and need to merge message histories.
- **CRDT-based approach** (e.g., Y.js or Automerge for text, Observed-Remove Set for reactions) should be evaluated.
- **Lamport timestamps or hybrid logical clocks** replace `updated_at` as tiebreakers when clocks may be unsynchronized across stations.

This ADR explicitly limits its scope to the single-station deployment model. An ADR-007 should supersede it when federation begins (ADR-006 covers the Go rewrite and single-process station consolidation).

## Alternatives Considered

### Operational Transform (OT)
Rejected: Over-engineered for single-station deployments with serialized writes. OT requires maintaining operation histories and transformation functions — complexity not justified for 2-3 browser clients.

### CRDT (Conflict-Free Replicated Data Types)
Rejected for Phase 1–9: Requires additional libraries (Y.js, Automerge) and changes the data model. CRDTs are designed for peer-to-peer and offline-first scenarios — the hermes-backend single-station model has neither.

### Pessimistic Locking (SELECT FOR UPDATE)
Rejected: SQLite's single-writer already serializes all writes. Adding explicit row-level locking would provide no benefit and increase code complexity.

## References

- [ADR-003: Conversation-Based Messaging Model](adr-003-conversation-messaging-model.md)
- [docs/architecture/database.md](../architecture/database.md) §4.2 — `messages` table with `edited_at` and `deleted_at`
- [docs/architecture/api.md](../architecture/api.md) §4.4 — Message CRUD endpoints
- [docs/architecture/websocket.md](../architecture/websocket.md) — `MESSAGE_EDITED` and `MESSAGE_DELETED` events
- [docs/audits/comprehensive.md](../audits/comprehensive.md) §H-4 — Original audit finding