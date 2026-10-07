# Adversarial Architecture Audit — Hermes Backend on sBitx v2

**Reviewer**: Architecture Auditor 🔍  
**Date**: 2026-07-17  
**Documents Reviewed**: `api.md`, `database.md`, `README.md`  
**Target Hardware**: sBitx v2 (Raspberry Pi 4, 4 GB RAM, HF 3–30 MHz)  
**Environment**: Field-deployed, unreliable power, temperature stress, air-gapped or intermittent HF connectivity

---

## Verdict: ⚠️ CONDITIONAL GO — with 3 Blockers

The architecture is well-reasoned for a cloud/server deployment. However, **it was not designed for a Raspberry Pi 4 with 4 GB RAM in field conditions**. Three architectural mismatches must be resolved before Phase 1 implementation begins. The remaining issues are significant but resolvable with design adjustments and explicit documentation.

---

## 🔴 CRITICAL RISKS (Blockers — must resolve before Phase 1)

### CR-1: Stack Weight Exceeds Raspberry Pi 4 Memory Budget 🔴🔴🔴

**Severity**: CRITICAL — System will not run  
**Category**: Hardware Feasibility  
**Documents**: `api.md` §2, `database.md` §2, `README.md`

**Problem**: The documented stack requires all of these to run concurrently on 4 GB RAM:

| Service | Estimated Idle | Estimated Peak | Notes |
|---------|:---:|:---:|-------|
| PostgreSQL 17 + TimescaleDB | 300–500 MB | 800+ MB | Shared buffers alone will grab 128–256 MB; autovacuum workers, WAL writer, TimescaleDB background workers all consume independently |
| Redis 7 (AOF persistence) | 80–150 MB | 300 MB | AOF rewrite doubles memory temporarily; Pub/Sub buffers are unbounded by default |
| Node.js (Fastify + all workers in-process) | 150–300 MB | 500+ MB | V8 heap; BullMQ workers run in same process per the modular monolith design |
| mediasoup (2 workers) | 128–256 MB | 350 MB | Per the architecture, 2 workers minimum |
| coturn | 32 MB | 64 MB | |
| sBitx CLI + other system processes | 64 MB | 128 MB | |
| Linux OS + kernel | 200–300 MB | 384 MB | |
| **Total estimated** | **~1.0–1.7 GB idle** | **~2.5+ GB peak** | |

The projected peak of ~2.5+ GB under load is viable on 4 GB, but **only if every service behaves perfectly**. In practice:
- PostgreSQL's shared_buffers default to 25% of RAM on install — that's 1 GB immediately gone
- TimescaleDB compression jobs run on schedule and spike memory
- Redis AOF rewrite forks the process, temporarily doubling memory
- Node.js GC pauses can spike heap by 2x between collections
- mediasoup consumes memory per-transport, per-producer, per-consumer — not capped
- Linux OOM killer under memory pressure will kill **whichever process the kernel chooses**, including PostgreSQL mid-transaction (data corruption risk)

**The architecture does not define memory limits for any service. No cgroup, no Docker --memory, no systemd MemoryMax.** On a Raspberry Pi 4 in field conditions, this is a guaranteed OOM scenario within hours of operation.

**Recommendation**: 
1. Before any code is written, deploy the full stack on actual Pi 4 hardware and run `docker stats` under simulated load (telemetry ingest + message sync + 1 WebRTC session). Document actual memory usage.
2. Set explicit memory limits on every container/process:
   - PostgreSQL: `shared_buffers=128MB`, `effective_cache_size=256MB`
   - Redis: `maxmemory 128mb`, `maxmemory-policy allkeys-lru`
   - Node.js: `--max-old-space-size=384` (V8 heap limit)
   - mediasoup: cap workers at 1, cap per-worker transports
3. Add a memory budget section to the deployment documentation with failover behavior (which service to sacrifice first under OOM).
4. **Re-evaluate PostgreSQL on Pi 4**. The hermes-backend ADR-002 explicitly acknowledges SQLite was rejected for this architecture but the Pi 4 constraint was not factored in. A dual-stack approach (SQLite for single-station field deployments, PostgreSQL for server/multi-station) must be designed into the repository layer from day one — not as a future migration path.

**Go/No-Go**: **BLOCKER.** Do not write Phase 1 code until memory profiling is complete and architecture adjusts accordingly.

---

### CR-2: PostgreSQL on Raspberry Pi 4 Is Architectural Overreach 🔴🔴

**Severity**: CRITICAL — Wrong database for the hardware  
**Category**: Database Design / Hardware Feasibility  
**Documents**: `database.md` §1, §2, `database.md` §7

**Problem**: ADR-002 argues PostgreSQL over SQLite based on: concurrent writes, JSONB, full-text search, foreign keys, TimescaleDB, row-level security. These are all correct for a server deployment. But the target hardware is a Raspberry Pi 4 in a field station that:
- Has at most **2–3 concurrent clients** (1 browser UI + 1 mobile device + 0–1 remote station connection)
- Stores messages for a single station with a handful of users
- Has **no concurrent writers** in the conventional sense — the API, WebSocket gateway, and workers all run in the same Node.js process
- Has no row-level security needs (single-tenant)
- Has no multi-node replication needs

SQLite in WAL mode handles concurrent reads perfectly. The "single-writer limitation" in ADR-002 is irrelevant when the writer is a single Node.js process serializing through an event loop.

**What ADR-002 missed**: 
- PostgreSQL's MVCC generates dead tuples that require VACUUM. On a Pi 4 SD card, VACUUM is I/O-intensive and competes with the OS for the single SD card bus
- PostgreSQL writes WAL to disk on every transaction. On an SD card, this is slow and contributes to card wear
- TimescaleDB compression jobs run on schedule and are CPU + I/O heavy — on a Pi 4, they will contend with radio telemetry processing
- PostgreSQL crash recovery after unexpected power loss requires WAL replay — minutes of downtime on a Pi 4. SQLite with `PRAGMA synchronous=NORMAL` is nearly instant

**The repository layer abstraction already exists** — the documentation says "SQLite for in-memory test environments via Drizzle adapters." This needs to be a first-class production path, not a test-only escape hatch.

**Recommendation**:
1. **Design for SQLite as the primary production database** for single-station sBitx v2 deployments
2. Reserve PostgreSQL for multi-station server deployments only (Phase 4 federation)
3. The Drizzle ORM abstraction makes this feasible — define a `DatabaseAdapter` interface with SQLite and PostgreSQL implementations
4. For telemetry time-series: use SQLite's built-in features (separate database file with daily table partitioning via application-level sharding) OR accept that 90-day retention means ~8M rows at 1 row/sec — SQLite handles this trivially
5. Re-evaluate TimescaleDB — it's a PostgreSQL-only extension that locks you into PostgreSQL. Time-series on SQLite is simpler than the documentation assumes

**Go/No-Go**: **BLOCKER.** The database strategy must address Pi 4 constraints before Phase 1.

---

### CR-3: No Power-Loss Data Integrity Strategy 🔴

**Severity**: CRITICAL — Data corruption on power loss  
**Category**: Operational Resilience  
**Documents**: `database.md` §1, §7 — no power-loss section exists anywhere

**Problem**: The architecture assumes reliable power. sBitx v2 stations run in environments with unreliable electricity — generators, solar with battery, car batteries. Power loss is guaranteed. The documentation covers:
- Zero-downtime migrations (§7)
- Retention policies (§8)
- Soft deletes (`deleted_at`)

It does NOT cover:
- What happens when PostgreSQL is mid-WAL-write during power loss
- What happens when Redis AOF is mid-rewrite during power loss
- What happens to in-flight BullMQ jobs during power loss
- What happens to the SD card filesystem during power loss
- How long recovery takes after power restoration
- Whether the station can operate in a degraded mode without PostgreSQL/Redis

**On a Raspberry Pi 4 with an SD card, unexpected power loss will corrupt the filesystem eventually.** Ext4 with journaling helps, but the SD card controller may have its own write caching that bypasses filesystem guarantees. PostgreSQL WAL + SD card = high risk of needing manual `pg_resetwal` recovery, which can lose committed transactions.

**Recommendation**:
1. Add a **Power Loss & Recovery** section to the architecture documentation covering:
   - Filesystem choice: ext4 with `data=journal` or f2fs (flash-friendly)
   - PostgreSQL: `fsync=on`, `full_page_writes=on`, `wal_sync_method=fdatasync`
   - Redis: AOF `appendfsync always` (slower but durable) vs `everysec` (lose 1s of data on crash)
   - SD card wear leveling strategy
   - Graceful shutdown on low battery signal (GPIO trigger → systemd shutdown → stop services in order)
   - Boot-time recovery sequence: filesystem check → PostgreSQL recovery → Redis data load → application start
2. Document expected recovery time after power loss
3. Consider a read-only fallback mode: if PostgreSQL is unavailable after power loss, the API serves cached radio status and queues writes to a local SQLite until PostgreSQL recovers

**Go/No-Go**: **BLOCKER.** Deploying to field stations without a power-loss strategy is negligent.

---

## 🟠 HIGH RISKS (Must address before production, not blocking Phase 1 start)

### HR-1: mediasoup on Pi 4 Is Premature Optimization of the Wrong Feature 🟠

**Severity**: HIGH  
**Category**: Feature Prioritization / Hardware Feasibility  
**Documents**: `api.md` §5 (WebRTC events), `README.md` (architecture diagram includes mediasoup SFU)

**Problem**: mediasoup SFU + coturn adds ~200–400 MB of memory and significant CPU overhead. WebRTC audio on a single-station Pi 4 serves at most 1–2 LAN clients — SFU routing is overkill. A peer-to-peer WebRTC connection (or even simpler: direct ALSA audio streaming to the browser via WebSocket) would serve the same use case with 0 additional memory.

More critically, the hermes-backend project review audit (2026-06-11, §2.2) explicitly flagged this: WebRTC ships in Phase 2 (Week 7–12) while HMP/UUCP radio transport ships in Phase 3 (Week 17–18). The core value proposition of HERMES (HF radio messaging) arrives five weeks after the secondary feature (LAN audio).

**On sBitx v2, WebRTC audio is unlikely to be used at all.** The radio IS the audio channel. LAN audio is a nice-to-have for operator training scenarios, not a core field requirement.

**Recommendation**:
1. Remove mediasoup from Phase 1–2 scope entirely for sBitx v2 deployments
2. If LAN audio is needed, implement it as peer-to-peer WebRTC (no SFU) or browser-based audio capture → WebSocket → ALSA playback
3. Reserve mediasoup for multi-station server deployments only
4. This frees 200–400 MB RAM and eliminates the coturn dependency

---

### HR-2: Redis Is a Single Point of Failure with No Degraded Mode 🟠

**Severity**: HIGH  
**Category**: Operational Resilience  
**Documents**: `api.md` §2 (Redis in stack), `database.md` §2

**Problem**: Redis is used for:
- BullMQ job queues (HAL commands, attachment processing, message delivery)
- Pub/Sub event bus (all realtime events)
- Session store (refresh token hashes)
- Rate limiting counters
- Presence state
- WebSocket connection routing

If Redis dies on a Pi 4 (OOM kill, power loss corruption, AOF file corruption):
- Radio commands stop working (no BullMQ) — operators cannot change frequency or PTT
- WebSocket stops delivering events — clients appear frozen
- Rate limiting stops — no protection
- Sessions become invalid — all users logged out
- Presence shows everyone offline

The architecture has **no fallback**. There is no "Redis is down, operate in degraded mode" path. On a single Pi 4, a Redis crash takes down the entire communication stack.

**Recommendation**:
1. Define explicit degraded modes:
   - **Redis down**: Radio commands bypass BullMQ queue and execute synchronously (with timeout)
   - **Redis down**: WebSocket delivers events directly from in-process emitter (no cross-process fan-out needed on single Pi 4)
   - **Redis down**: Rate limiting falls back to in-memory counters
   - **Redis down**: Sessions fall back to database-only verification
2. Add a Redis health check with automatic fallback activation
3. Document that BullMQ job persistence is lost during Redis outage — radio commands execute synchronously but without retry guarantees
4. Consider: on a single Pi 4 with a single Node.js process, do you actually need Redis at all? In-process EventEmitter + in-memory job queue + SQLite session store could replace Redis entirely for single-station deployments

---

### HR-3: Schema Uses `TIMESTAMPTZ` Without Documenting Timezone Behavior in Air-Gapped Stations 🟠

**Severity**: HIGH  
**Category**: Database Design / Field Operations  
**Documents**: `database.md` §1 (Guiding Principles), §4.1–4.9 (all DDL uses `TIMESTAMPTZ`)

**Problem**: The schema uses `TIMESTAMPTZ` everywhere with `DEFAULT now()`. In air-gapped stations:
- There is no NTP server to sync the clock
- The Pi 4 has no RTC battery by default — clock resets to epoch on every power cycle
- `now()` returns the system clock, which may be **wildly wrong** (year 1970, or 2040)
- Messages will appear with nonsensical timestamps
- Sync cursors based on monotonic sequences will break when clock jumps backwards
- GPS can provide time, but there's no documented integration between GPS time and PostgreSQL clock

This is a well-known problem in disconnected embedded systems, and the architecture is completely silent on it.

**Recommendation**:
1. Add a clock initialization strategy:
   - On boot: read last known good timestamp from a file (written on graceful shutdown)
   - If GPS is available: set system clock from GPS NMEA sentences
   - If no GPS and no saved timestamp: prompt operator to set time manually via setup API
2. Use monotonic sequence numbers (`last_event_sequence BIGINT`) for sync ordering — already in the schema, but this should be the primary ordering, not timestamps
3. Document that `created_at` timestamps may be inaccurate until clock is synced
4. Add a `clock_synced` flag to the health endpoint
5. Consider adding a `server_time` field to the `AUTHENTICATED` WebSocket response for client clock sync — already documented in the WebSocket protocol, but add GPS as the time source

---

### HR-4: No Message Size Limits or Content Validation Depth 🟠

**Severity**: HIGH  
**Category**: Security / Resource Exhaustion  
**Documents**: `api.md` §4.4 (Messages), §4.8 (Attachments)

**Problem**: Message content is `TEXT` in PostgreSQL — unbounded. The API schema validation is mentioned as JSON Schema via AJV, but the documented request examples show no `maxLength` constraints. On a Pi 4 with 4 GB RAM:
- A 100 MB message body (malicious or accidental) loaded into Node.js memory will trigger GC thrashing or OOM
- The conversation list query with `LEFT JOIN LATERAL (SELECT content ... LIMIT 1)` loads message content — if content is unbounded, this query can return enormous rows
- The `sync_queue` stores entity references ("never serialized payload snapshots") — good, but the actual message content still needs to be pulled during sync, and large messages cause sync stalls

**Recommendation**:
1. Add `maxLength` to JSON Schema for `content` field (e.g., 64 KB — more than enough for HF radio text messaging)
2. Add server-side truncation in the API layer before persistence
3. The conversation list query should use `LEFT(content, 200)` or a separate `preview_content` column instead of pulling the full content
4. Add a message size limit to the sync delta batching — messages larger than N bytes are delivered via a separate `MESSAGE_CONTENT` sync event with streaming

---

### HR-5: WebRTC Signaling + WebRTC Itself Documented but Phase Misaligned on Pi 4 🟠

**Severity**: HIGH  
**Category**: Scope / Feature Prioritization  
**Documents**: `api.md` §5 (WebSocket topics include `webrtc.<sessionId>`), `README.md` architecture diagram

**Problem**: The API documentation and architecture diagram include WebRTC signaling (18 WebSocket message types, `webrtc.<sessionId>` topic) and mediasoup SFU. The hermes-backend project review already flagged that HMP/UUCP (the core radio transport) ships after WebRTC in the roadmap. On sBitx v2, this prioritization is even more wrong — the station's primary interface IS the radio. WebRTC is a LAN-only nice-to-have that consumes scarce Pi 4 resources.

**Recommendation**:
1. Strip WebRTC from the Phase 1 API surface and documentation for sBitx v2 deployments
2. Gate WebRTC features behind a configuration flag (`ENABLE_WEBRTC=false` by default on sBitx v2)
3. Reprioritize: HMP/UUCP ingest → messaging → sync → WebRTC (if at all)

---

## 🟡 MEDIUM RISKS (Address in Phase 1–2, not blocking start)

### MR-1: Sync Queue Can Grow Unbounded on Long-Disconnected Devices

**Documents**: `database.md` §4.8 (`sync_queue`)  
**Risk**: A device offline for 30 days with active conversations will accumulate thousands of sync queue rows. The `LIMIT 50` conversation query doesn't solve this — sync deltas batch in groups of 100 events by default. If 10,000 events accumulated, that's 100 SYNC_DELTA frames on reconnect. The WebSocket will be saturated with sync traffic while the user waits.

**Mitigation**: Add a "catch-up summary" mode — after N missed events (e.g., 500), send a `SYNC_SUMMARY` with conversation-level unread counts and let the client lazy-load conversations individually. Define a maximum sync batch count.

### MR-2: No Conversation Participant Limit

**Documents**: `database.md` §4.2 (`conversations`, `conversation_participants`)  
**Risk**: A `group` conversation with 500 participants creates 500 delivery records per message. No limit is documented. On a Pi 4, this is a self-inflicted DoS.

**Mitigation**: Enforce a maximum participant count per conversation type (e.g., `direct`: 2, `group`: 50, `broadcast`: 200).

### MR-3: Legacy Compatibility Shim Is Underspecified

**Documents**: `api.md` §10  
**Risk**: The legacy API compatibility shim is mentioned as "compatibility shim translates inbox/outbox queries to conversation queries internally" — this is massive scope. The old API had fundamentally different semantics (folders, not conversations; binary delivery, not per-channel). The shim may need its own set of tables to maintain legacy state. This could easily become a Phase 1–2 effort on its own.

**Mitigation**: Explicitly scope what the shim covers. Define whether legacy endpoints are read-only, read-write, or fully compatible. List exactly which endpoints are preserved.

### MR-4: Soft Delete Retention Conflicts with "Messages (deleted) 90 days" Policy

**Documents**: `database.md` §4.2 (`messages.deleted_at`), §8 (Retention)  
**Risk**: Soft-deleted messages have `content` replaced with NULL but the row remains. The conversation list query filters `WHERE deleted_at IS NULL`, so deleted messages don't appear. But the 90-day purge cron deletes entire rows. If a message is part of a reply chain (`reply_to_message_id` references it), deleting the original message breaks the reply thread silently. `ON DELETE SET NULL` handles the FK but the UX shows a broken reply.

**Mitigation**: Retain deleted message stubs (id, created_at, sender_id) beyond the 90-day purge to preserve reply chain integrity, or mark replies to deleted messages with a `reply_deleted` flag in the API response.

### MR-5: No Health Endpoint for Individual Services

**Documents**: `api.md` §4.15 (Health)  
**Risk**: The health endpoint returns `{ database: "ok", redis: "ok", radio: "connected" }`. On a Pi 4 where services may degrade independently, this is insufficient. If Redis is in fallback mode (see HR-2), the health check should report `redis: "degraded"` not `"ok"`.

**Mitigation**: Add degraded status levels. Add `/health/deep` endpoint that runs actual queries (not just connection checks).

---

## 🟢 LOW RISKS (Acceptable, document for awareness)

### LR-1: JWK Key Rotation Invalidates All Sessions
JWT RS256 private key rotation invalidates all access tokens. Acceptable tradeoff — users re-login. Document this behavior.

### LR-2: Signed URL Token Expiry for Attachments
1-hour signed URL expiry works for LAN. For HF radio store-and-forward, the attachment may arrive days after the URL expires. The download flow needs to accommodate this.

### LR-3: Rate Limiting Counters Are In-Memory (Redis)
If Redis is down and rate limiting falls back to in-process counters, a process restart resets all counters. Acceptable for single Pi 4 — low risk.

---

## Summary: Top 10 Risks Ranked

| Rank | ID | Risk | Severity | Blocks Phase 1? |
|:---:|-----|------|:---:|:---:|
| 1 | CR-1 | Stack exceeds Pi 4 memory; no service limits defined | 🔴 CRITICAL | ✅ Yes |
| 2 | CR-2 | PostgreSQL over SQLite on Pi 4 is wrong database choice | 🔴 CRITICAL | ✅ Yes |
| 3 | CR-3 | No power-loss data integrity strategy | 🔴 CRITICAL | ✅ Yes |
| 4 | HR-1 | mediasoup on Pi 4 wastes 200–400 MB for unused feature | 🟠 HIGH | No |
| 5 | HR-2 | Redis is single point of failure with no degraded mode | 🟠 HIGH | No |
| 6 | HR-3 | No clock sync strategy for air-gapped stations | 🟠 HIGH | No |
| 7 | HR-4 | Unbounded message content on memory-constrained Pi 4 | 🟠 HIGH | No |
| 8 | HR-5 | WebRTC prioritized over HMP/UUCP in roadmap | 🟠 HIGH | No |
| 9 | MR-1 | Sync queue unbounded growth on long-offline devices | 🟡 MEDIUM | No |
| 10 | MR-2 | No conversation participant limit | 🟡 MEDIUM | No |

---

## Go/No-Go Assessment

**NO-GO for Phase 1 implementation** until the three Critical blockers above are resolved:

1. **Memory profiling on actual Pi 4 hardware** with service limits documented
2. **Database strategy revised** to include SQLite as first-class production path for Pi 4
3. **Power-loss recovery strategy** designed and documented

The architecture is **correct for a server deployment**. It is **not yet correct for sBitx v2**. The gap is not in the API design, the database schema normalization, or the messaging model — those are well-designed. The gap is in the fundamental mismatch between infrastructure assumptions (server/cloud) and target hardware (embedded field station).

Once these three blockers are addressed, Phase 1 can proceed with the HIGH risks being resolved during implementation.

---

## What the Architecture Gets Right

To be clear: the following decisions are correct and should not be revisited:

- **Conversation-based messaging over inbox/outbox**: Correct model. The email abstraction via `message_envelopes` is clean.
- **Per-recipient, per-channel delivery tracking**: Correct for multi-transport HF radio.
- **`IRadioDriver` HAL with `execFile` array args**: Textbook secure CLI wrapping.
- **Drizzle ORM over Prisma**: Correct for constrained hardware — no Rust query engine.
- **JWT RS256 + refresh token rotation**: Correct auth model.
- **Typed WebSocket protocol with subscription model**: Vastly better than the legacy broadcast-all approach.
- **Sync cursors + sync queue for offline-first**: Correct pattern.
- **UUID PKs for future federation**: Correct forward-thinking choice.
- **Soft deletes on user-visible entities**: Correct UX pattern.
- **Named indexes with descriptive names**: Correct operational practice.