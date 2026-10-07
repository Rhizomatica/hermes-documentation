# Comprehensive Architecture Audit — Hermes Backend

**Auditor**: Architecture Auditor (Senior Systems Reviewer)  
**Date**: July 2026  
**Scope**: Full architecture review of hermes-backend — REST API, database schema, WebSocket gateway, event bus, HAL, auth, deployment, observability, and development plan  
**Target**: sBitx v2 (Raspberry Pi 4, 4 GB RAM, SD card storage, single-station field deployment)

---

## Executive Summary

The hermes-backend architecture is **well-reasoned and thoughtfully adapted** from a server-grade design to a resource-constrained single-station field device. The decision to collapse PostgreSQL + Redis + mediasoup into SQLite + in-process EventEmitter is correct for this target. The documentation is thorough and the ADRs are well-structured.

However, this audit identifies **4 critical, 9 high, 11 medium, and 6 low-severity findings** that must be addressed before production deployment. The most concerning patterns cluster around three themes:

1. **Operational resilience gaps** — The system assumes rare process restarts despite being deployed on hardware with unreliable power. Rate limiters, job queues, and WebSocket state are volatile across restarts in ways that create exploitable attack surfaces and data loss vectors.

2. **Data integrity and correctness** — Clock sync strategy creates a fundamental tension between idempotency and retroactive timestamp updates. The sync engine's cursor model has an unvalidated assumption (sequence numbers on messages) that could break the entire offline sync protocol.

3. **Observability blind spots** — Metrics are disabled by default, yet several failure modes (WebSocket backpressure drops, event bus saturation, telemetry stream death) produce no observable signal beyond a WARN-level log line that may never be read in a field deployment.

Below is the full audit by architectural domain.

---

## Findings Summary

| Severity | Count | Key Themes |
|----------|:-----:|------------|
| 🔴 Critical | 2 | Data loss vectors, restart amplification |
| 🔴 ~~Critical~~ ✅ Resolved | 2 | ~~Idempotency breakage~~ (resolved: sync engine removed), ~~Sync cursor gap~~ (resolved: sync engine removed) |
| 🟠 High | 9 | Silent event drops, token invalidation race, no integrity checks, systemd restart loops, SD card wear unverified |
| 🟡 Medium | 11 | Adapter interface viability, legacy shim scope, Drizzle migration risks, no CRDT strategy, conversation query complexity, attachment token replay |
| 🟢 Low | 6 | Documentation inconsistencies, naming, missing config validation, test gaps |

> **Update (July 2026)**: The sync engine has been removed entirely. The hermes-backend runs on a Raspberry Pi 4 accessed via local WiFi hotspot — clients are browser windows into the Pi's state. On reconnect, clients fetch current state via the REST API. This eliminates the need for cursor-based sync, delta batching, conflict resolution, `sync_cursors`, `sync_queue`, and `event_sequence` columns. Findings **C-1** (idempotency breakage from retroactive timestamps) and **C-4** (sync cursor gap) are resolved by this simplification.

---

## 1. Data Persistence & Integrity

### 🔴 C-1: Idempotency Broken by Retroactive Timestamp Updates

**Source**: `docs/database.md` §13.2, step 4:
> "created_at timestamps will be updated retroactively when clock syncs"

**Problem**: The message creation endpoint uses `client_message_id` for idempotency (see `docs/api.md` §4.4). The server returns the already-created message on duplicate `client_message_id`. However, if the server retroactively updates `created_at` on messages after clock sync, any client that received the pre-sync version now holds a different timestamp than the server. This creates:

- **Duplicate detection corruption**: A client that stored `(clientMessageId, createdAt)` as a local dedup key will see the server's updated timestamp as a different message.
- **Cursor-based sync breakage**: If sync cursors use `created_at` (implicitly or as a tiebreaker), retroactive updates invalidate cursor positions.
- **Conversation ordering**: Messages inserted during the "unknown time" window will cluster at epoch (1970-01-01). After clock sync, they'll be retroactively spread across the correct time range — but the `last_event_sequence` monotonic counter won't match the new chronological order.

**Recommendation**: Never mutate `created_at` after insertion. If the clock is unknown at message creation time, store two timestamps:
- `created_at` (immutable, monotonic: use `last_event_sequence` as fallback when clock is unsynced)
- `wall_clock_adjusted_at` (nullable, set once when clock syncs, informational only)

The `created_at` value should use a monotonic counter when `clock_synced=false` and switch to wall-clock time once the clock syncs — but with a continuity guarantee: `created_at[post-sync] > max(all previous created_at values)`.

**Severity**: 🔴 Critical — breaks idempotency and sync correctness for messages created before clock sync.

---

### 🔴 C-2: Job Queue Persistence is "Best-Effort" — Defeats the Purpose

**Source**: `docs/database.md` §4.9:
> "If the jobs table write fails (database locked), the job still executes from the in-memory queue. Database persistence is best-effort — this is acceptable for a single Pi 4 where process restarts are rare."

**Problem**: The primary failure mode this system faces is **power loss**, not clean process restarts. Power loss kills the in-memory queue AND may interrupt the database write. The "rare restarts" assumption is contradicted by the deployment environment (unreliable power in remote/field conditions, documented in the README).

The result: critical jobs (radio commands, message sends, attachment processing) can be acknowledged to the caller as accepted, executed, but **lost on the next power cycle** with no record they ever existed. The caller thinks the command was processed; the system after recovery has no trace of it.

**Recommendation**: Make job persistence **mandatory, not best-effort**. Write the job to the `jobs` table with `status=queued` BEFORE acknowledging the HTTP response. Only mark the job as `running` after the database write is confirmed. On recovery, re-queue all jobs with `status=queued` — these were accepted but never executed. Mark jobs with `status=running` as `failed` (interrupted mid-execution) and re-queue or flag for operator review.

**Severity**: 🔴 Critical — acknowledged commands lost on power cycle.

---

### 🔴 C-3: Systemd Restart Loops on Corrupted State

**Source**: `docs/deployment.md` §systemd-service:
```ini
Restart=always
RestartSec=5
```

**Problem**: If a corrupted SQLite file, misconfiguration, or uncaught exception causes the process to crash at startup, systemd will restart every 5 seconds indefinitely. On a Pi 4 with an SD card, this means:

1. **SD card thrashing**: Every restart writes logs, opens database files, executes WAL recovery — on flash storage with limited write endurance.
2. **Operator has no visibility**: If the station is remote and air-gapped, the crash-loop could run for days/weeks before anyone notices, silently destroying the SD card.
3. **No backoff**: `RestartSec=5` with no rate limiting means 720 restarts/hour, 17,280/day.

**Recommendation**: Use systemd's restart rate-limiting:
```ini
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=300
StartLimitBurst=5
```
After 5 failures in 5 minutes, systemd stops restarting. This prevents SD card destruction while still auto-recovering from transient failures.

Additionally, add a health check to the `ExecStartPre` directive that validates SQLite integrity (`PRAGMA integrity_check`) before starting the application, and logs the result.

**Severity**: 🔴 Critical — SD card destruction vector in field-deployed stations.

---

### 🟠 H-1: No Data Integrity Verification on Stored Messages

**Problem**: Messages, attachments, and all user data are stored on an SD card with no checksum verification at rest. SD cards experience silent data corruption (bit rot) over time, especially in field conditions (temperature extremes, power fluctuations). The attachment table has a `checksum` column for dedup but it's computed at upload time and never verified on read.

For a system deployed in regions where corruption might go undetected for months, this means:
- A message's content could silently corrupt
- An attachment could serve corrupted bytes with a valid SHA-256 from upload time
- There's no periodic integrity scan

**Recommendation**:
1. Store a `content_checksum` column on `messages` (SHA-256 of `content` at write time).
2. Implement a background integrity checker that runs weekly (low priority, throttled I/O) and verifies a random sample of messages against their checksums.
3. For attachments, periodically re-read `storage_path` and verify against the stored `checksum`. Log any mismatches at ERROR level.
4. Add a `GET /health/deep` check for `data_integrity: { last_scan, corruption_detected }`.

**Severity**: 🟠 High — silent data corruption in field-deployed systems with no detection mechanism.

---

### 🟠 H-2: DatabaseAdapter Dual-Implementation Risk

**Source**: `docs/database.md` §10 — `DatabaseAdapter` interface with `SQLiteAdapter` and `PostgresAdapter`.

**Problem**: The `DatabaseAdapter` interface abstracts the database backend, but the current schema has SQLite-specific features that don't map cleanly to PostgreSQL:

| Feature | SQLite Adapter | PostgreSQL Adapter |
|---------|---------------|-------------------|
| UUID generation | Application layer (`crypto.randomUUID()`) | Could use `gen_random_uuid()` on server |
| Timestamps | ISO 8601 `TEXT` | `TIMESTAMPTZ` |
| Booleans | `INTEGER` 0/1 | `BOOLEAN` |
| JSON | `TEXT` columns with JSON functions | `JSONB` with GIN indexes |
| Daily sharded tables | Application-level partition management | Native partitioning + TimescaleDB |
| WAL PRAGMAs | SQLite-specific | N/A (PostgreSQL has own WAL) |

The claim that "migration to PostgreSQL is a configuration switch, not a code rewrite" is **optimistic**. The `DatabaseAdapter` interface would need to handle:
1. Different query syntax (partial indexes, `SUBSTR` vs `LEFT`, `LIMIT` vs `FETCH`)
2. Different concurrency models (MVCC vs single-writer)
3. Different migration tooling (Drizzle SQLite vs Drizzle PostgreSQL)
4. Different JSON query patterns (SQLite `json_extract()` vs PostgreSQL `->`/`->>`/`@>`)

**Recommendation**: Either:
- **Accept the dual-implementation cost** and write both adapters now, with integration tests against both backends from Phase 2, OR
- **Commit to SQLite-only** and remove the PostgreSQL abstraction. Add a `DatabaseAdapter` only when the need for PostgreSQL is proven (e.g., first multi-station server deployment).

A half-implemented abstraction that's never tested against the second backend is **technical debt masquerading as architecture**.

**Severity**: 🟠 High — untested abstraction promises false optionality.

---

## 2. Synchronization & Offline Behavior

### 🔴 C-4: Sync Cursor Model Lacks `event_sequence` Column on Messages

**Source**: `docs/database.md` §4.8 — `sync_cursors` uses `last_event_sequence`, and `sync_queue` has a `sequence` column. But the `messages` table (and `conversations`, `reactions`, etc.) have **no `event_sequence` column**.

**Problem**: When a client reconnects and sends `SYNC_REQUEST` with a cursor, the server must find all events with `sequence > cursor`. The only table with sequences is `sync_queue` — but `sync_queue` stores *entity references*, not event data. To build `SYNC_DELTA` batches, the server must:

1. Query `sync_queue WHERE sequence > cursor`
2. For each row, JOIN to the actual entity table (messages, conversations, reactions, etc.) by `entity_type` + `entity_id`
3. Reconstruct the full event payload

This works, but:

- The `sync_queue` is a **delivery queue**, not an **event store**. It's purged after 30 days. If a device is offline longer than 30 days, its sync cursors won't find the events in `sync_queue`, and the sync breaks.
- Events not pushed to `sync_queue` (e.g., if the queue insertion fails silently, per the "best-effort" design) are invisible to the sync protocol.
- There's no `event_sequence` column on primary entity tables, making it impossible to answer "what happened in this conversation between sequence 142 and now?" without `sync_queue`.

**Recommendation**: Add an `event_sequence` column (monotonically increasing integer, global across all entity types) to the `messages`, `conversations`, `message_reactions`, and `attachments` tables. The sync engine can then query directly:

```sql
SELECT * FROM messages
WHERE conversation_id = :convId
  AND event_sequence > :cursor
ORDER BY event_sequence ASC
LIMIT 100;
```

The `sync_queue` remains as the delivery mechanism, but the **source of truth for event ordering** lives on the entities themselves. This also fixes the 30-day retention gap.

**Severity**: 🔴 Critical — sync protocol breaks for devices offline > 30 days; no entity-level event ordering.

---

### 🟠 H-3: SYNC_SUMMARY Lazy-Load Strategy is Undefined

**Source**: `docs/websocket.md` §Sync Protocol:
> "If missed events exceed 500, the server sends SYNC_SUMMARY instead... The client lazy-loads conversations individually."

**Problem**: The `SYNC_SUMMARY` response tells the client "you missed 1,250 events in conversation abc-123." But the protocol does not specify:

1. **How the client lazy-loads**: Does it call `GET /conversations/:id/messages?since=last_sync_time`? Does it use a REST endpoint with cursor pagination? The WebSocket and REST APIs need an explicit sync reconciliation protocol.
2. **How the client detects new conversations**: If a conversation was created while offline, the `SYNC_SUMMARY` only covers conversations the client already knows about. The client has no way to discover new conversations via the sync protocol.
3. **Conflict resolution**: What happens if the client sent messages while offline that have since been superseded by server-side state? The sync protocol is purely server→client; there's no client→server conflict resolution.

**Recommendation**:
1. Define the lazy-load protocol explicitly: `GET /sync/conversation/:id?after_sequence=N` returns events in batches.
2. Add a `SYNC_CONVERSATIONS_LIST` event in `SYNC_SUMMARY` that returns the list of active conversation IDs and their latest sequences, so the client can discover new conversations.
3. Document the conflict resolution strategy for Phase 5 (WebSocket sync engine). For now, explicitly state: last-writer-wins, client messages created while offline are unchanged on reconnect.

**Severity**: 🟠 High — undefined lazy-load protocol will block Phase 5 implementation.

---

### 🟠 H-4: No CRDT or Conflict-Free Merge Strategy

**Problem**: The system is described as "offline-first" but has no conflict-free replicated data type (CRDT) strategy or operational transform (OT) model. The sync engine pushes server→client deltas. What happens when:

1. Client A and Client B both edit the same message while offline?
2. Client A deletes a message while Client B edits it?
3. Two clients add reactions to the same message simultaneously?

The current docs say nothing about conflict resolution. The implicit assumption is **last-writer-wins**, which is acceptable for a single-station deployment with 2-3 clients, but must be **explicitly documented** as the chosen strategy with its limitations.

**Recommendation**: Add an ADR-005 documenting the conflict resolution strategy. For Phase 1-9, use **last-writer-wins with `updated_at` timestamp as tiebreaker**. Document that:
- Message edits: last `updated_at` wins; earlier edits are silently discarded
- Reactions: union of all reactions (no conflict possible)
- Deletions: deletion always wins over edits (delete has higher priority)
- Client message status: client-created messages with `status=sending` that conflict with server state are resolved in favor of server state

For Phase 10 (multi-station federation), a CRDT approach (e.g., Y.js or Automerge) should be evaluated.

**Severity**: 🟠 High — undefined conflict resolution leads to data inconsistency.

---

## 3. WebSocket & Real-Time Infrastructure

### 🟠 H-5: Silent Event Drops on Backpressure

**Source**: `docs/websocket.md` §Implementation Notes:
> "Backpressure: if a client's send buffer exceeds 16 KB, events are dropped (logged at WARN)"

**Problem**: Silent event drops are an anti-pattern in realtime systems. When the send buffer exceeds 16 KB:
- Events are **silently discarded** — the client has no way to know events were dropped
- The dropped events are **lost forever** — they won't be replayed on next sync because the sync cursor already advanced past them
- The WARN log is likely never observed in a field-deployed, air-gapped station
- The client's state diverges from the server state without detection

This is particularly dangerous for `MESSAGE_NEW` and `MESSAGE_DELIVERED` events — the UI will show a conversation with no new messages, but messages were sent.

**Recommendation**:
1. **Never silently drop state-changing events** (`MESSAGE_NEW`, `MESSAGE_DELETED`, `MESSAGE_DELIVERED`, `MESSAGE_READ`, `REACTION_*`). Instead, disconnect the slow client with code `4010 SLOW_CLIENT` and force a full sync on reconnect.
2. For informational events (`RADIO_TELEMETRY`, `TYPING_*`), dropping is acceptable but must be signaled to the client via a `STALE_TELEMETRY` message so the UI can indicate stale data.
3. Increase the backpressure threshold from 16 KB to 64 KB (matching the `--max-old-space-size=384` constraint; 16 KB is overly conservative) and make it configurable.
4. Add a `hermes_ws_events_dropped_total` counter metric (enabled even when full metrics are disabled — this is a critical signal).

**Severity**: 🟠 High — silent state divergence between server and client.

---

### 🟠 H-6: WebSocket Connection Limit (10) Too Low for Typing + Telemetry

**Source**: `docs/websocket.md` §Connection Limits — max 10 concurrent connections.

**Problem**: Ten connections sounds generous for "2-3 clients," but each client may open multiple tabs/browser windows. Additionally:
- The browser UI opens 1 WebSocket (or more if multiple tabs)
- A mobile client opens 1 WebSocket
- A CLI monitoring tool opens 1 WebSocket
- The radio daemon bridge potentially uses 1 WebSocket connection (the `sbitx_websocket.c` C daemon bridge mentioned in api.md §10)

At 3 users × 2 tabs each + 1 mobile + 1 CLI + 1 daemon bridge = 9 connections. The 10-connection ceiling has no headroom for debugging tools, admin panels, or unexpected reconnection windows where old connections haven't timed out yet.

**Recommendation**: Raise to 20 concurrent connections. The per-connection memory overhead of `ws` is ~10 KB (idle) — 20 connections = 200 KB, negligible on a 4 GB Pi. Add a `hermes_ws_connections_rejected_total` counter to detect when the limit is hit.

**Severity**: 🟠 High — connection starvation in normal usage scenarios.

---

### 🟡 M-1: WebSocket Auth Token Invalidation Race Condition

**Source**: `docs/security.md` §Authentication and `docs/api.md` §4.1:
> "Changing the user's locale via PATCH /users/me invalidates all existing tokens"

**Problem**: When a user changes their locale:
1. All existing JWT access tokens become invalid (they carry the old `locale` claim)
2. WebSocket connections opened before the locale change still hold the old access token
3. The WebSocket auth was done at connection time — the gateway doesn't re-validate tokens on each message

Until the WebSocket reconnects (heartbeat timeout after 60 seconds, or explicit reconnection), the stale connection continues operating with the old locale. This means:
- WebSocket system messages continue in the old language
- The connection is technically using an invalidated token
- If the token was revoked for security reasons (not locale change), the WebSocket remains authenticated

**Recommendation**: 
1. Add a `token_version` claim to JWTs. Increment on security-relevant changes (password change, session revocation). Don't increment on locale changes — store locale in the WebSocket connection context instead.
2. For forced re-authentication, the server sends an `AUTH_REQUIRED` WebSocket message with code `4011` and closes the connection. The client reconnects with the new token.
3. Document the distinction: locale changes → soft transition (old connections keep working until heartbeat expiry); security changes → hard disconnect.

**Severity**: 🟡 Medium — security edge case; low probability of exploitation on single-station deployment.

---

## 4. Observability & Operations

### 🟠 H-7: Critical Failure Modes Are Only Logged at WARN Level

**Problem**: Several failure modes produce only WARN-level logs:
- SWR protection triggered (WARN)
- Database query slow > 100ms (WARN)
- Rate limit hits (WARN)
- Event bus listener errors (swallowed entirely — ADR-002 mentions no error handling)
- Telemetry stream death (WARN, but the disconnected event is emitted)
- WebSocket event drops (WARN — see H-5)

In a field-deployed, air-gapped station, logs are consumed by journald and rotated. There's no log aggregation, no alerting pipeline, and no operator actively watching logs. WARN-level logs are effectively invisible.

**Recommendation**:
1. Add a `/health/deep` check for `warning_conditions` — a count of recent WARN events that should trigger attention (e.g., "3 SWR events in the last hour"). This surfaces issues via a pull-based health endpoint that the UI can display.
2. Increment Prometheus counters for all WARN-level conditions (even when full metrics are disabled, the counters should be available at `/metrics` for local scraping).
3. Add a `GET /system/alerts` endpoint that returns recent warnings (last 24 hours) from an in-memory ring buffer (last 100 warning events).
4. For event bus errors, emit an `ERROR` event that the audit logger captures.

**Severity**: 🟠 High — invisible failure modes in air-gapped deployments.

---

### 🟠 H-8: Metrics Disabled by Default, No Local Dashboard

**Source**: `docs/observability.md` and `docs/deployment.md`:
> "Metrics (Prometheus) — Disabled by default to save resources"

**Problem**: If metrics are disabled, the only operational visibility is:
- `GET /health` (binary ok/not-ok)
- `GET /health/deep` (database + radio connectivity)
- `systemctl status` (process alive/dead)
- `ps aux | grep node` (memory)
- `ls -lh data/hermes.sqlite` (database size)

There's no way to observe:
- Message throughput trends
- WebSocket connection churn
- Event loop lag
- Query performance degradation
- Memory leak progression

The argument that "metrics save RAM" is valid, but **counters are nearly free** (~8 bytes each in Prometheus client libraries). The cost is in the histogram buckets and the HTTP exposition endpoint. An intermediate solution is needed.

**Recommendation**: Enable counter metrics by default (~2-5 MB overhead). Keep histograms disabled. Provide a local `/health/stats` JSON endpoint that exposes key counters without requiring Prometheus:

```json
{
  "http_requests_total": 12345,
  "messages_sent_total": 678,
  "ws_connections_active": 2,
  "ws_events_dropped_total": 0,
  "db_slow_queries_total": 3,
  "memory_heap_mb": 142,
  "memory_rss_mb": 210,
  "uptime_seconds": 86400
}
```

This gives operators a single endpoint to curl for a health snapshot without the Prometheus infrastructure overhead.

**Severity**: 🟠 High — no operational visibility beyond process alive/dead.

---

### 🟡 M-2: No Graceful Degradation for WebSocket Gateway Failure

**Problem**: If the WebSocket gateway crashes (e.g., uncaught exception in a connection handler), what happens? The gateway is part of the Fastify server — a crash takes down HTTP and WebSocket. Systemd restarts the process, but:
- All 2-3 clients disconnect simultaneously
- Reconnection storm: all clients reconnect at once, requesting full sync
- The sync engine processes 3 full sync requests while the system is already under load from the restart

**Recommendation**: Isolate the WebSocket gateway into a separate worker thread (Node.js `worker_threads`). If the gateway worker crashes:
- The Fastify HTTP server continues serving REST requests
- The main thread restarts the gateway worker
- Connected clients are notified via REST polling (the UI can fall back to polling `GET /conversations` every 5 seconds)

Alternatively, implement a **circuit breaker** in the event bus → WebSocket bridge. If the WebSocket gateway accumulates errors, stop pushing events to it and log at ERROR for operator investigation.

**Severity**: 🟡 Medium — full process restart on WebSocket crash; single-station impact is limited (2-3 users affected).

---

## 5. Security & Auth

### 🟡 M-3: Refresh Token Rotation Relies on Atomic Transaction — SQLite Limitation

**Source**: `docs/adr/adr-004-jwt-rs256-token-rotation.md` §reuse-detection:
```typescript
await db.transaction(async (tx) => {
  await tx.updateSession(session.id, { refresh_replaced_by: newRefreshHash });
  await tx.insertSession({ ... });
});
```

**Problem**: SQLite's `busy_timeout=5000` handles write contention, but there's a subtle gap in the rotation logic. Between reading `session.refresh_replaced_by` and executing the transaction, another request could have already rotated the token. The transaction ensures the update+insert is atomic, but the **check** happened outside the transaction.

Race condition timeline:
1. Attacker steals refresh token R1
2. Legitimate user refreshes with R1 → R1 marked as `refresh_replaced_by=R2`, new token R2 issued
3. Attacker also refreshes with R1 → check `refresh_replaced_by` → sees R2 → revokes ALL sessions (reuse detected)
4. Legitimate user's R2 is now revoked → forced to re-login

This is **correct behavior** (reuse detection works), but the legitimate user experiences a disruptive logout. The docs should document this as expected behavior with a clear UX message: "Your session was revoked because your refresh token may have been compromised. Please log in again."

**Recommendation**: The implementation is correct. Add a user-facing alert in the spec: "If you are unexpectedly logged out, your credentials may have been compromised. Change your password immediately."

**Severity**: 🟡 Medium — correct security behavior but disruptive UX; needs documentation.

---

### 🟡 M-4: Password Policy Lacks Minimum Complexity

**Source**: `docs/security.md` §Password Policy: minimum length 8 characters, no complexity requirements.

**Problem**: In field-deployed stations, operators may choose weak passwords ("hamradio", "sbitx123", the station callsign). The 5-attempts/minute rate limit helps against online brute force, but:
- A determined attacker on the local Wi-Fi hotspot (open or WPA2 with weak password) can sustain 5 attempts/minute = 7,200 attempts/day
- An 8-character lowercase-only password has ~208 billion combinations — 7,200/day = ~79,000 years to exhaust. Acceptable.
- But an attacker who guesses the callsign (public information!) as the password succeeds in 1 attempt.

**Recommendation**: Add password complexity validation:
- Must not contain the user's callsign (case-insensitive substring check)
- Must not be in a deny-list of common passwords (e.g., "password", "hamradio", "sbitx", "hermes")
- Recommend (not enforce) mixed case, digits, and symbols

**Severity**: 🟡 Medium — rate limiting protects against online attacks; weak password choice is mitigated by the closed LAN environment.

---

### 🟡 M-5: No Certificate Pinning or TOFU for LAN Deployments

**Problem**: The deployment guide generates a self-signed TLS certificate. The first connection from a browser will show a certificate warning. Users on a LAN Wi-Fi hotspot have no way to verify the certificate is legitimate — a MITM attacker on the same hotspot could present their own self-signed cert.

**Recommendation**: Implement Trust-On-First-Use (TOFU) certificate pinning in the Web UI:
1. On first connection, display the certificate's SHA-256 fingerprint
2. The operator verifies this fingerprint against a printed card shipped with the sBitx hardware
3. The browser stores the fingerprint in localStorage
4. Subsequent connections verify the cert matches the stored fingerprint; alert if it changed

This is a Phase 7-8 hardening item but should be documented as a known limitation.

**Severity**: 🟡 Medium — LAN-only attack surface; requires attacker on the same Wi-Fi hotspot.

---

## 6. Database & Schema Design

### 🟠 H-9: Daily-Sharded Telemetry Tables — No Benchmark Data

**Source**: `docs/database.md` §4.5 and §4.7:
> "At ~1 row/second, a single day's table holds ~86,400 rows — trivially small for SQLite"

**Problem**: The architecture claims the daily-sharded tables and separate `telemetry.db`/`gps.db` files are efficient, but there's no benchmarking data. The concerns are:

1. **UNION ALL across multiple daily tables**: A 7-day telemetry query does `SELECT * FROM telemetry_20260717 UNION ALL SELECT * FROM telemetry_20260718 ...` across 7 tables. SQLite must open each table, scan indexes, merge results. At 86,400 rows/day × 7 days = 604,800 rows — this is non-trivial for SQLite on an SD card.
2. **Separate database files don't reduce I/O contention**: `telemetry.db`, `gps.db`, and `hermes.db` are all on the same SD card. Writes to `telemetry.db` still consume the SD card's I/O bus while `hermes.db` is being read. There's no I/O isolation benefit — only organizational separation.
3. **Table creation at startup**: "The application creates daily tables on startup" — a startup that happens after power loss must create today's table, checkpoint WAL for the main DB, and initialize the clock. This increases recovery time.

**Recommendation**:
1. Run a benchmark on actual Pi 4 hardware: 1 Hz telemetry inserts for 7 days (simulated), then run the UNION ALL query. Measure latency.
2. If performance is acceptable (< 200ms for 7-day range), document the benchmark.
3. If performance is poor, consider a single telemetry table with a `created_at_date` column and a composite index: `(station_id, created_at_date, time)`. This avoids UNION ALL overhead at the cost of larger single-table scans. SQLite handles 10M+ row tables on Pi 4 if properly indexed.
4. Move `telemetry.db` to tmpfs (RAM disk) with periodic checkpointing to SD card. Telemetry data is non-critical (90-day retention) and losing the last hour on power loss is acceptable.

**Severity**: 🟠 High — unvalidated performance assumption that could cause API timeouts.

---

### 🟡 M-6: Conversation List Query Optimization is Speculative

**Source**: `docs/database.md` §6 — Critical Query.

**Problem**: The conversation list query uses:
- A correlated subquery for the last message (`LEFT JOIN messages lm ON lm.id = (SELECT id FROM messages m2 WHERE ... LIMIT 1)`)
- A correlated subquery for unread counts
- `SUBSTR(lm.content, 1, 200)` for content preview

SQLite's correlated subquery performance is **highly variable**. On tables with thousands of messages per conversation, the unread count subquery (which scans `messages WHERE msgs.conversation_id = c.id AND msgs.created_at > COALESCE(...)`) could trigger a full scan for every conversation in the list.

**Recommendation**: 
1. Denormalize `last_message_id` and `last_message_preview` onto the `conversations` table. Update them synchronously on message creation via a trigger or application code. This eliminates the correlated subquery entirely.
2. Cache `unread_count` per participant. Increment on message creation, decrement on `mark_read`. Store in `conversation_participants.unread_count` or compute from `last_read_event_sequence` — the sequence-based approach is more robust (avoids counter drift).
3. Benchmark the denormalized approach against the subquery approach with 100 conversations, 100 messages each.

**Severity**: 🟡 Medium — the critical query may perform poorly at scale; the architecture acknowledges the need for optimization but hasn't validated the proposed approach.

---

### 🟡 M-7: Retention Policy Runs as Synchronous DELETE — Could Block Writes

**Source**: `docs/database.md` §8 — retention policies executed via `DELETE` statements.

**Problem**: SQLite's single-writer means a large `DELETE` on `audit_logs` (2 years of data) will hold the write lock for the duration. During that time:
- No messages can be inserted
- No telemetry can be recorded
- No HTTP requests that write to the database can be processed

For `audit_logs` with 2 years of data at ~100 events/day, that's ~73,000 rows — manageable. But the `DELETE` must still scan and lock the table.

**Recommendation**: Batch deletes in small chunks (100 rows at a time with `LIMIT`) in a loop with `await sleep(100)` between batches. This yields the write lock to other operations. SQLite's `busy_timeout` will handle the brief contention.

**Severity**: 🟡 Medium — manageable with batching; the docs acknowledge the need to "avoid long locks" but don't specify the batching strategy.

---

## 7. Hardware Integration & Resilience

### 🟡 M-8: Telemetry Stream Death — No Reconnection Logic

**Source**: `docs/hardware-integration.md` §SBitxCLIDriver:
> "Telemetry stream dies: disconnected event emitted; API serves last-known state with stale: true"

**Problem**: When the sBitx CLI telemetry stream dies (process exit), the driver emits `disconnected` but **does not attempt to reconnect**. The operator must manually intervene (or the systemd restart cycle triggers). For a field-deployed station, the telemetry stream could die due to:
- USB glitch (common on Pi 4)
- sBitx CLI crash
- Temporary hardware fault

In many cases, simply re-launching the telemetry process would resolve the issue.

**Recommendation**: Implement exponential backoff reconnection in the `SBitxCLIDriver`:
```
Attempt 1: immediate reconnect
Attempt 2: 1 second delay
Attempt 3: 2 seconds
Attempt 4: 4 seconds
...
Max: 60 seconds between attempts
After 10 consecutive failures: emit 'disconnected' permanently, log ERROR
```

This handles transient failures without operator intervention while surfacing persistent failures.

**Severity**: 🟡 Medium — operator intervention required for a common transient failure.

---

### 🟡 M-9: SWR Protection Cuts TX but Doesn't Log Frequency/Power Context

**Source**: `docs/hardware-integration.md` §SWR Protection:
> "If SWR > 3.0 and PTT is active → immediately cuts TX"

**Problem**: The SWR protection emits the `swr-protection` event and cuts TX, but doesn't log or store:
- What frequency was being used
- What power level was set
- What antenna was connected
- Whether this is a recurring issue

Without this context, an operator investigating "why did my transmission fail?" has no diagnostic information.

**Recommendation**: Create an `swr_events` audit entry with a structured schema:
```sql
CREATE TABLE swr_events (
  id TEXT PRIMARY KEY,
  frequency_hz INTEGER NOT NULL,
  power_watts INTEGER NOT NULL,
  swr_reading REAL NOT NULL,
  profile_id TEXT REFERENCES radio_profiles(id),
  created_at TEXT NOT NULL
);
```

This enables diagnostics: "Have we triggered SWR protection on this frequency before?" → yes → antenna problem on that band.

**Severity**: 🟡 Medium — missing diagnostic data for a critical safety feature.

---

## 8. Testing Strategy

### 🟡 M-10: No Test for the "Best-Effort" Queue Path

**Problem**: The testing strategy documents unit, integration, and E2E tests, but no test validates:
- What happens when the jobs table write fails (best-effort persistence path)
- What happens when telemetry stream chunks contain malformed JSON (the `catch` block in `SBitxCLIDriver.startTelemetryStream`)
- What happens when WebSocket events are dropped due to backpressure (the WARN log path)

These are exactly the failure modes that are hardest to test and most likely to cause production issues.

**Recommendation**: Add fault-injection tests:
- A test double for the database adapter that simulates write failures
- A test for the telemetry parser with mixed valid/invalid JSON lines
- A test that floods the WebSocket client with events to trigger the backpressure drop path

**Severity**: 🟡 Medium — untested error paths in critical failure modes.

---

### 🟡 M-11: No Performance Regression Test Suite

**Problem**: The development plan includes "Performance test" tasks (D4.15, D9.4, D9.5, D9.6) but these are manual, one-time verifications. There's no automated performance regression suite that runs in CI.

The critical query (conversation list), telemetry UNION ALL scan, and WebSocket event delivery latency can degrade with schema changes or increased data volume. Without automated performance tests, regressions are discovered only when a field operator reports "the UI is slow."

**Recommendation**: Add a `tests/performance/` directory with benchmarks:
1. Conversation list query with seeded data (100 conversations × 100 messages)
2. Telemetry query across 7 daily tables with 604,800 rows
3. WebSocket event throughput (100 events/second sustained)

Run these not as CI gates (too slow) but as a weekly scheduled job or a manual `npm run test:perf` command. Record results in a `PERFORMANCE.md` file for trend analysis.

**Severity**: 🟡 Medium — regressions caught in production, not CI.

---

## 9. Architecture & Abstraction Design

### 🟡 M-12: Event Bus Has No Delivery Guarantees — Could Lose Critical Events

**Source**: `docs/adr/adr-002-in-process-event-bus.md` §Negative:
> "No persistence: Events are fire-and-forget. If a listener is not registered when an event fires, it misses the event."

**Problem**: The ADR argues that "critical events (messages, audit logs) are persisted to SQLite by their respective modules independently of the event bus." This is true for the **source of truth**, but there are consumers that **only** receive events through the bus:

1. **WebSocket Gateway**: Receives `message:new` to push to connected clients. If a race condition causes the listener to miss an event, the client doesn't receive a realtime notification. The sync on reconnect compensates, but the realtime UX is degraded.
2. **Sync Queue Populator**: If the sync listener misses a `message:new` event, the `sync_queue` row is never created → offline devices never receive the message → data loss.

The in-process EventEmitter is reliable within the same tick (synchronous delivery), but there's no mechanism to verify that all registered listeners actually processed the event. If a listener throws, the error propagates to the emitter (unhandled 'error' event on EventEmitter can crash the process).

**Recommendation**:
1. Wrap all event listeners in try/catch to prevent cascading failures.
2. For the sync queue populator, don't rely solely on the event bus. The message creation service should directly enqueue to `sync_queue` as part of the same database transaction. The event bus is a **notification**, not the **mechanism**.
3. Add a periodic reconciliation job (every 5 minutes) that compares `messages.created_at > 5 min ago` against `sync_queue` entries and backfills any missing sync queue rows.

**Severity**: 🟡 Medium — depends on listener correctness; mitigated by sync-on-reconnect for WebSocket but risk remains for sync queue population.

---

## 10. Development Plan & Implementation Risks

### 🟡 M-13: 10-Phase Plan Has No "Go/No-Go" Decision Points

**Problem**: The development plan (docs/development/plan.md) defines 10 phases with 90+ tasks across ~18 weeks, but has no explicit go/no-go gates. Each phase has a "Milestone" description but no criteria for:
- Are we ready to proceed to the next phase?
- What must be validated on actual Pi 4 hardware before proceeding?
- What are the performance/SLO targets that must be met?

Without these gates, the team could reach Phase 9 (deployment) and discover that Phase 2's database design doesn't meet performance targets on actual SD card hardware.

**Recommendation**: Add explicit gates to each phase milestone:
- **Phase 2 gate**: Conversation list query < 100ms with 100 convos × 100 messages on Pi 4 SD card
- **Phase 3 gate**: Telemetry stream reconnection works after simulated USB disconnect
- **Phase 5 gate**: WebSocket sync delivers 500 missed events in < 5 seconds
- **Phase 7 gate**: Power-loss simulation: 100 cycles without database corruption
- **Phase 8 gate**: All rate limits verified under 3 concurrent users

**Severity**: 🟡 Medium — plan execution risk; caught in review, not in implementation.

---

## 11. Documentation & Consistency

### 🟢 L-1: Inconsistent Memory Budget Numbers

**Sources**:
- `README.md` §Memory Budget: `PRAGMA cache_size = -8000` (8 MB)
- `docs/adr/adr-001-sqlite-for-pi4.md`: `PRAGMA cache_size = -64000` (64 MB)
- `docs/database.md` §12.2: `PRAGMA cache_size = -8000` (8 MB)

The ADR says 64 MB cache; the README and database docs say 8 MB. This is a significant difference for a system with a tight memory budget.

**Severity**: 🟢 Low — documentation inconsistency; reconcile to 8 MB (64 MB SQLite cache is excessive on a 4 GB Pi with 384 MB V8 heap).

---

### 🟢 L-2: JWT Expiry Inconsistency

**Sources**:
- `docs/api.md` §3: "Refresh Token: 30-day expiry"
- `docs/security.md` §Authentication: "Refresh token lifetime: 7 days"
- `docs/adr/adr-004-jwt-rs256-token-rotation.md` §Token Architecture: "Sign refresh token (RS256, 7d)"

**Severity**: 🟢 Low — reconcile to 7 days (the more secure option; ADR and security doc agree).

---

### 🟢 L-3: Missing Environment Variable Documentation

The code references several environment variables (`RADIO_DRIVER`, `ENABLE_WEBRTC`, `DB_ADAPTER`, `METRICS_ENABLED`, `METRICS_PORT`, `CORS_ORIGINS`, `JWT_PRIVATE_KEY_PATH`) but `.env.example` has not been reviewed for completeness.

**Severity**: 🟢 Low — should be verified against all env vars used across documentation.

---

### 🟢 L-4: Naming Inconsistency for Attachment Token Expiry

**Sources**:
- `docs/api.md` §4.8: "30-day `attachment_token`"
- `docs/api.md` §4.8: "signed time-limited URLs (1-hour expiry)"

The attachment download has two mechanisms (signed URL for direct access, attachment token for radio store-and-forward). The naming and expiry durations should be clearly distinguished to avoid implementation confusion.

**Severity**: 🟢 Low — documentation clarity.

---

### 🟢 L-5: RBAC Role Naming Mismatch

**Sources**:
- `docs/api.md` §3 and `docs/security.md` §RBAC: Roles are `admin`, `operator`, `user`, `readonly`
- `docs/security.md` §RBAC: Roles are `admin`, `operator`, `viewer`

The security doc uses "viewer" in the RBAC table but "readonly" everywhere else.

**Severity**: 🟢 Low — reconcile to "readonly" (the more descriptive name).

---

### 🟢 L-6: No Explicit "What This System Does NOT Do" Section

**Problem**: While individual docs mention limitations (no HF encryption, no malware scanning, no full-disk encryption), there's no centralized list of anti-goals. This leads to scope creep and mismatched expectations.

**Recommendation**: Add a "Non-Goals" section to the README or architecture overview listing:
- No end-to-end encryption of message content
- No full-disk encryption of the SD card
- No multi-station federation (Phase 10 only)
- No WebRTC audio streaming (gated, off by default)
- No malware scanning of attachments
- No real-time machine translation of messages

**Severity**: 🟢 Low — scope clarity improvement.

---

## 12. What Will Break First in Production

Based on this audit, the predicted failure order in a field deployment:

| Rank | Failure Mode | Time to Surface | Impact |
|:----:|-------------|:---:|---|
| 1 | **SD card corruption from systemd restart loop** (C-3) | Days to weeks | Station becomes unresponsive; SD card physically damaged |
| 2 | **Clock sync timestamp paradox** (C-1) | First power cycle without GPS | Message ordering breaks; idempotency lost; UI confusion |
| 3 | **WebSocket event drops during high load** (H-5) | First message burst (3+ messages in rapid succession) | Silent message loss in UI; operator thinks messages weren't sent |
| 4 | **Sync breaks for devices offline > 30 days** (C-4) | After station returns from field repair | Device cannot sync; manual database intervention needed |
| 5 | **Job queue data loss on power cycle** (C-2) | First power loss after command submission | Accepted radio commands never executed; operator retries manually |
| 6 | **Correlated subquery performance degradation** (M-6) | After 1,000+ conversations accumulate | UI latency grows linearly; Pi 4 CPU bound on conversation list |

---

## 13. Hidden Costs & Assumption Risks

| Assumption | Risk if Wrong | Likelihood |
|------------|---------------|:---:|
| "Power loss is rare on Pi 4" (H-2, §DB) | Job queue data loss, corrupted state | **High** — sBitx v2 is deployed in field conditions with unreliable power |
| "2-3 concurrent clients max" (multiple refs) | Scalability ceiling hit early; no graceful handling | **Medium** — 3 users × 2 devices each = 6 clients with 10-connection WebSocket limit |
| "SD card has sufficient write endurance" (H-1) | Silent data corruption over months | **Medium** — SD cards in temperature extremes degrade faster than rated |
| "DatabaseAdapter works for PostgreSQL" (H-2) | Major refactor when PostgreSQL is needed | **Low immediately, High if claimed as feature** — the abstraction is untested |
| "1 Hz telemetry is sufficient" (docs/hardware) | Missed transient events (SWR spike between samples) | **Low** — 1 Hz is standard for HF telemetry |
| "Clock will be synced within minutes of boot" (docs/database §13) | Extended operations with unknown clock cause timestamp paradox | **Medium** — GPS may take minutes to acquire fix; manual sync may be delayed |

---

## 14. Recommendations Prioritized

### Must Fix Before Phase 1 Implementation (Critical)

1. **C-1**: Redesign clock-sync timestamp strategy — never mutate `created_at` retroactively
2. **C-2**: Make job queue persistence mandatory, not best-effort
3. **C-3**: Add systemd restart rate-limiting to prevent SD card destruction
4. **C-4**: Add `event_sequence` column to entity tables; don't rely solely on `sync_queue`

### Should Fix Before Phase 5 (WebSocket/Sync) — High

5. **H-1**: Add data integrity checksums and periodic verification
6. **H-2**: Resolve DatabaseAdapter strategy — commit to SQLite-only or implement PostgreSQL adapter now
7. **H-4**: Document conflict resolution strategy (ADR-005)
8. **H-5**: Replace silent event drops with client disconnect + force sync
9. **H-7**: Add `/health/stats` endpoint for operational visibility without Prometheus
10. **H-9**: Benchmark telemetry query performance on actual Pi 4 hardware

### Should Fix Before Phase 9 (Deployment) — Medium

11. **M-2**: Isolate WebSocket gateway into worker thread or add circuit breaker
12. **M-6**: Validate conversation list query performance; consider denormalization
13. **M-8**: Add telemetry stream reconnection logic
14. **M-10**: Add fault-injection tests for error paths
15. **M-13**: Add go/no-go gates to development plan milestones

### Documentation Cleanup — Low

16. **L-1**: Reconcile SQLite cache_size values
17. **L-2**: Reconcile JWT refresh token expiry
18. **L-5**: Reconcile RBAC role naming ("viewer" → "readonly")

---

## 15. Architectural Strengths

Despite the findings above, the architecture has several well-executed design decisions:

1. **WAL mode + synchronous=NORMAL**: The correct SQLite configuration for crash resilience on SD cards. Good attention to SD card wear management (noatime, disabled swap, separate telemetry DB).

2. **Typed EventEmitter**: A clean, minimal abstraction. The ADR correctly identifies that Redis adds no value for in-process communication. The typed event map prevents event name typos at compile time.

3. **Conversation-based messaging**: The migration from inbox/outbox to conversations is the right architectural evolution. The `message_deliveries` table (per-recipient, per-channel) is well-designed.

4. **Monotonic sequence numbers for sync ordering**: Correctly identifies that wall-clock timestamps are unreliable in air-gapped stations. The `last_event_sequence` ordering is architecturally sound (but needs the `event_sequence` column on entity tables — see C-4).

5. **HAL with IRadioDriver interface**: Clean separation between hardware control and business logic. The `SimulatedRadioDriver` enables full development without physical hardware.

6. **Immutable audit logs**: Append-only, never deleted. Good for compliance and debugging in field conditions.

7. **i18n strategy**: Embedding locale in JWT to avoid database queries is clever. The fallback chain (user preference → Accept-Language → en) is correctly specified.

8. **Attachment token for HF store-and-forward**: Recognizing that radio delivery may take days and designing a separate 30-day download token shows good domain understanding.

---

## 16. Conclusion

The hermes-backend architecture is a **well-adapted design** for a resource-constrained single-station deployment. The decisions to collapse PostgreSQL, Redis, and mediasoup into SQLite + in-process equivalents are correct for the target hardware. The documentation is thorough and the ADRs follow a clear decision-making process.

However, the architecture makes **optimistic assumptions about operational reliability** that are inconsistent with the deployment environment. The "rare restart" assumption contradicts the documented threat of unreliable power. The "best-effort" persistence for job queues creates a data-loss vector in the system's primary failure mode. The clock sync strategy introduces a subtle correctness bug in the idempotency guarantee.

The 4 critical findings (C-1 through C-4) should be resolved before any code is written, as they affect fundamental correctness properties of the system. The 9 high-severity findings should be addressed before Phase 5 (WebSocket/sync), as they affect the realtime and offline behavior that differentiates this system from a simple CRUD API.

**Overall assessment**: The architecture is sound at the conceptual level but has operational gaps that would surface within weeks of field deployment. Addressing the identified issues will produce a robust, field-ready system for HF radio communication in remote and disaster-affected areas.

---

*Audit completed July 2026. This document should be reviewed and findings tracked as GitHub issues linked to the relevant development phases.*