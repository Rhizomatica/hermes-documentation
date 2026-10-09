This is an excellent architectural insight. You're absolutely right to question this — the sync protocol is over-engineered for your actual deployment model. Let me break down why.

## Your Actual Deployment Model

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

**Key observations:**

1. The browser is **always connected to the same machine** (the Pi). There's no "offline" in the traditional sense — when you close the browser tab, the app state still lives on the Pi.

2. Radio transmission is handled by **hermes-radio-daemon**, not by the browser client. The browser just tells the backend "send this message" and the backend queues it for radio transmission.

3. There's **no multi-device sync problem** — the Pi is the single source of truth. A phone and a laptop are just two windows into the same database.

## What the Sync Protocol Was Designed For (deleted scenario)

The current `sync_cursors`, `sync_queue`, `SYNC_DELTA`, and cursor-based catchup was designed for a model where:
- A mobile device **accumulates messages locally while truly offline** (no connection to any server)
- Later reconnects and must **merge** local state with server state
- **Multiple devices** independently create messages while disconnected from each other
- Conflict resolution is needed (two devices edit the same message)

**None of this applies to your deployment.** The browser is either connected to the Pi (and gets real-time WebSocket pushes) or it's not connected at all. When it reconnects, it can just **fetch the current state via REST** — the same way it loaded the page initially.

## Recommendation: Remove the Sync Engine Entirely

**Delete these components:**

| Component | Reason |
|-----------|--------|
| `sync_cursors` table | No cursor-based sync needed |
| `sync_queue` table | No offline queuing needed — radio daemon handles TX |
| `SYNC_REQUEST` / `SYNC_DELTA` / `SYNC_SUMMARY` / `SYNC_COMPLETE` protocol messages | No delta sync protocol needed |
| `event_sequence` column on entities | Not needed without sync cursors |
| Entire sync engine module | Component eliminated |
| ~30% of Phase 5 tasks (D5.10–D5.13) | No sync to implement |

**Keep (simplified):**

| Component | Purpose |
|-----------|---------|
| WebSocket gateway | Real-time push: new messages, radio telemetry, typing indicators, presence |
| `AUTHENTICATE` flow | Connect, subscribe to topics, receive events |
| REST API for messages/conversations | Full state fetch on page load or reconnection |
| `message_deliveries` table | Still useful — tracks which recipients got the message via which channel (WebSocket vs radio) |

**Reconnection flow becomes dead simple:**

```
Client reconnects WebSocket:
  1. AUTHENTICATE
  2. SUBSCRIBE to conversation topics  
  3. GET /conversations (REST) — fetch current state
  4. GET /conversations/:id/messages — fetch messages for active conversation
  5. Server pushes new events as they happen
```

No cursors, no deltas, no catchup protocol. The REST API already has pagination — the client requests what it needs.

## What This Simplifies

| Area | Before | After |
|------|--------|-------|
| Database tables | 17+ tables including sync_cursors, sync_queue | ~15 tables |
| WebSocket protocol messages | 15 message types | ~11 message types |
| Phase 5 implementation | 15 tasks, ~2 weeks | ~11 tasks, ~1.5 weeks |
| Audit findings resolved | C-4 (critical sync gap) eliminated | No sync to break |
| Code complexity | Sync engine, cursor management, delta batching | Just push events on the event bus |

## What Stays the Same

- **Delivery tracking** (`message_deliveries` per-recipient per-channel) — still valuable
- **Conversation model** — still the right abstraction
- **WebSocket for realtime** — radio telemetry, new message notifications, presence
- **REST API** — unchanged, the authoritative data access layer
- **Radio daemon integration** — unchanged, it handles the actual HF transmission

## Question to Confirm

Before I draft the changes, one clarification: when a user sends a message via the browser UI, the flow is:

1. Browser → `POST /conversations/:id/messages` → hermes-backend
2. hermes-backend stores the message in SQLite
3. hermes-backend tells hermes-radio-daemon to transmit it over HF

Is that correct? Or does the browser interact with the radio daemon directly for message transmission?

Confirmed. The flow is: Browser → REST API → hermes-backend → SQLite + radio-daemon. The Pi is the single source of truth and clients are always-on when connected via WiFi.

## Final Plan: Remove Sync Engine — Simplify to REST + Real-time Push

Here's what I'll change and why. This eliminates **4 of the 5 most complex architectural components** and resolves **2 of the 4 critical audit findings** (C-4, C-1 partially):

### Files to Modify (7 files)

| File | Changes |
|------|---------|
| **`docs/architecture/websocket.md`** | Remove sync protocol entirely (SYNC_REQUEST, SYNC_DELTA, SYNC_SUMMARY, SYNC_COMPLETE, sync_cursors). Document simplified reconnection: client reconnects → AUTHENTICATE → SUBSCRIBE → fetches current state via REST |
| **`docs/architecture/database.md`** | Remove `sync_cursors` table, `sync_queue` table. Remove `event_sequence` column from entity tables. Remove related indexes, retention policies, ER diagram relationships. |
| **`docs/architecture/api.md`** | Remove sync-related endpoints. Simplify WebSocket section to match new protocol. |
| **`docs/adr/adr-003-conversation-messaging-model.md`** | Remove references to `event_sequence`, `sync_cursors`, sync-based ordering. |
| **`docs/development/plan.md`** | Remove Phase 5 tasks D5.10–D5.13 (sync engine). Reduce Phase 5 from 15 to 11 tasks. Adjust timeline estimates. Remove `sync_cursors`/`sync_queue` from Phase 2 (D2.11). |
| **`docs/audits/comprehensive.md`** | Mark C-4 (sync cursor gap) as **Resolved — sync engine removed**. Mark C-1 as **Resolved — retroactive timestamp updates no longer affect sync cursors**. Update findings count. |
| **`README.md`** | Update architecture diagram, project structure, and documentation index to reflect removed components. |

### Files to Create (0)

No new files needed — this is a simplification, not an addition.

### What Gets Removed

- **Tables**: `sync_cursors`, `sync_queue` (~2 tables, ~6 indexes, ~2 retention policies)
- **WebSocket messages**: `SYNC_REQUEST`, `SYNC_DELTA`, `SYNC_SUMMARY`, `SYNC_COMPLETE` (4 protocol types)
- **Columns**: `event_sequence` on all entity tables
- **Phase 5 tasks**: D5.10–D5.13 (~4 of 15 tasks)
- **Phase 2 tasks**: D2.11 (sync tables)
- **Audit findings**: C-4 (Critical), C-1 (partially resolved)

### What Stays — Simplified

- **WebSocket gateway**: Real-time push for new messages, radio telemetry, typing, presence
- **Reconnection model**: Client reconnects → AUTHENTICATE → SUBSCRIBE → uses REST API to fetch current state (`GET /conversations`, `GET /conversations/:id/messages`)
- **`message_deliveries`**: Still tracks per-recipient, per-channel delivery status (WebSocket vs radio)
- **REST API**: Unchanged — the authoritative data access layer with pagination

### New Reconnection Flow

```
Client disconnects (WiFi drop, browser tab closed, phone screen off)
  ↓
Client reconnects:
  1. WebSocket: CONNECT → AUTHENTICATE → AUTHENTICATED
  2. WebSocket: SUBSCRIBE { topics: ["conversation:*", "radio:telemetry"] }
  3. REST: GET /conversations                ← fetch conversation list
  4. REST: GET /conversations/:id/messages   ← fetch messages for active conversation
  5. WebSocket: Server pushes new events as they happen
```

No cursors. No deltas. No catchup protocol. The REST API already has pagination — the client requests exactly what it needs.

---
