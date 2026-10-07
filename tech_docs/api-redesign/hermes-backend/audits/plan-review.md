# Development Plan Review — Senior Project Manager Assessment

**Reviewer**: Senior Project Manager Agent  
**Date**: July 2026  
**Document Reviewed**: `docs/development/plan.md`  
**Review Basis**: ADRs, architecture specs, comprehensive audit, project-manager agent quality standards

---

## Executive Summary

The development plan provides a **solid structural skeleton** — 10 phases with ~90 tasks across ~18 weeks, tracing to documented architecture specs. However, it has **three systemic gaps** that would cause mid-implementation friction:

1. **No audit finding traceability** — The comprehensive audit identifies 2 critical, 9 high, and 11 medium findings. Only 1 finding (H-5, silent event drops) is explicitly addressed in a task (D5.10). The plan must map every critical/high finding to a scheduled task before Phase 1 begins.

2. **Task granularity is too coarse** — Tasks like "Create conversations table + repository" (D2.1) are 2-4 hours of work, not 30-90 minutes. Without acceptance criteria, file paths, and dependency notation, a developer cannot pick up a task and implement it without follow-up questions.

3. **No phase quality gates** — Each phase has a milestone description but no objective go/no-go criteria (build passes, test coverage, performance thresholds). The reviewer cannot determine if a phase is truly complete or merely "looks done."

The plan is **structurally sound at the macro level** but needs **operational detail** to be executable. Consider this review a companion document — implement the recommendations below before Phase 1 task breakdown begins.

---

## 1. Audit Finding Traceability

The PM agent's core requirement: *"Every critical and high audit finding must have a corresponding scheduled task."* The table below maps all findings from `docs/audits/comprehensive.md` to existing or needed tasks.

### Critical Findings — Must Be Resolved Before Phase 1

| Finding | Description | Current Status | Required Task | Recommended Phase |
|---------|-------------|:---:|---------------|:---:|
| ~~C-1~~ | Idempotency broken by retroactive timestamps | ✅ Resolved (sync engine removed; `created_at` immutable) | N/A | — |
| **C-2** | Job queue persistence is "best-effort" | ❌ No task | `[AUDIT C-2]` Mandatory persistence: write job to DB with `status=queued` BEFORE acknowledging HTTP response. On recovery, re-queue all `queued` jobs. | **Phase 2** (D2.11 must enforce this) |
| **C-3** | Systemd restart loops on corrupted state | ❌ No task | `[AUDIT C-3]` Add `StartLimitIntervalSec=300` and `StartLimitBurst=5` to systemd unit. Add `ExecStartPre` with `PRAGMA integrity_check`. | **Phase 7** (D7.8–D7.9 context) |
| ~~C-4~~ | Sync cursor gap (no `event_sequence` on entities) | ✅ Resolved (sync engine removed) | N/A | — |

### High Findings — Must Be Resolved Before Phase 5

| Finding | Description | Current Status | Required Task | Recommended Phase |
|---------|-------------|:---:|---------------|:---:|
| **H-1** | No data integrity verification | ❌ No task | `[AUDIT H-1]` Add `content_checksum` column to `messages`. Implement weekly background integrity scan. Add `data_integrity` check to `/health/deep`. | **Phase 2** (schema column) + **Phase 7** (health check) |
| **H-2** | DatabaseAdapter false optionality | ⚠️ Partial (D2.12) | `[AUDIT H-2]` Explicit decision in ADR or D2.12: commit to SQLite-only OR implement both adapters now with integration tests against both. | **Phase 2** |
| **H-3** | SYNC_SUMMARY undefined | ✅ Resolved (sync engine removed) | N/A | — |
| **H-4** | No CRDT/conflict resolution strategy | ⚠️ Implicit (single source of truth) | `[AUDIT H-4]` Add ADR-005 documenting conflict resolution strategy: last-writer-wins, deletion trumps edit, union of reactions. | **Phase 4** (before D4.8 edit message) |
| **H-5** | Silent event drops on backpressure | ✅ Addressed (D5.10) | Already captured in D5.10 — backpressure handling with `STALE_CONNECTION`. Confirm implementation matches spec. | **Phase 5** |
| **H-6** | WebSocket connection limit too low | ✅ Addressed (D5.11) | Already captured — D5.11 sets max 20 connections. | **Phase 5** |
| **H-7** | Critical failures only logged at WARN | ❌ No task | `[AUDIT H-7]` Add `/health/stats` JSON endpoint with counters. Add `GET /system/alerts` endpoint (last 24h of warnings). Wrap event listeners in try/catch. | **Phase 7** (health endpoint) |
| **H-8** | Metrics disabled, no local dashboard | ❌ No task | `[AUDIT H-8]` Enable counter metrics by default. Add `/health/stats` JSON endpoint. (Overlaps with H-7 — combine into one task.) | **Phase 7** |
| **H-9** | Telemetry tables unbenchmarked | ❌ No task | `[AUDIT H-9]` Run benchmark on Pi 4: 7-day UNION ALL query with 604,800 rows. Document latency. If > 200ms, redesign to single table with composite index. | **Phase 3** (before D3.9 is marked complete) |

### Medium Findings — Should Be Addressed Before Phase 9

| Finding | Description | Required Task | Recommended Phase |
|---------|-------------|---------------|:---:|
| M-2 | No graceful degradation for WebSocket crash | Isolate WebSocket into worker thread or add circuit breaker | Phase 5 (optional, risk-acceptable) |
| M-6 | Conversation query speculative optimization | Benchmark denormalized vs subquery approach | Phase 4 (D4.15 extended) |
| M-8 | Telemetry stream reconnection | Exponential backoff in `SBitxCLIDriver` | Phase 3 (D3.2) |
| M-10 | No fault-injection tests | Test doubles for DB write failures, malformed telemetry JSON | Phase 9 (D9.2 extended) |
| M-13 | No go/no-go gates | Add explicit gates per phase (see §3 below) | Phase 0 (now) |

**Gap count**: 8 audit findings (C-2, C-3, H-1, H-2, H-4, H-7, H-8, H-9) have no corresponding task. **This must be resolved before Phase 1 begins.**

---

## 2. Per-Phase Gap Analysis

### Phase 0: Documentation & Tooling Setup

**Assessment**: ✅ Strong. Documentation complete. Tooling setup tasks are appropriately scoped as Phase 1 prerequisites.

**Issues**:
- D0.B.2 depends on `D0.3` — task ID doesn't exist (should be D0.B.1 or D0.A.3?).
- D0.B.3 should specify whether the `DatabaseAdapter` is SQLite-only or dual-implementation (maps to audit finding H-2). This decision gates Phase 2 schema design.

**Recommendation**: Add `[AUDIT H-2]` to D0.B.3: explicitly decide adapter strategy before creating the interface stub.

---

### Phase 1: Core Infrastructure & Auth (Week 1–2)

**Assessment**: ✅ Well-scoped. 17 tasks over 2 weeks is reasonable. Each task traces to a spec section.

**Issues**:
- Task descriptions mention "Integration" or "Unit" for test type but no acceptance criteria. Example: D1.7 "POST /auth/login — login with callsign + password" — what constitutes done? ACs needed: "200 with accessToken + refreshToken for valid credentials", "401 for invalid password", "429 after 5 failed attempts."
- No file paths. A developer doesn't know where `auth/login` handler lives: `src/api/v1/auth/login.ts`? `src/api/v1/auth/controller.ts`?
- D1.3 (Configuration loader) should reference `docs/operations/deployment.md` and `docs/architecture/database.md` §12 for SQLite PRAGMAs and env var list.

**Recommendation**: Break each task into ACs per the PM agent's format. Add file paths.

---

### Phase 2: Database Layer & Repository Pattern (Week 3)

**Assessment**: ⚠️ Risk: 16 tasks in 1 week is optimistic. Creating, testing, and indexing 15 tables + repositories + adapter interface + migration pipeline in 5 working days requires 3+ tasks/day.

**Issues**:
- D2.11 (jobs table): does not enforce the mandatory persistence requirement from audit C-2. The task description must explicitly state: "Rows written with `status=queued` BEFORE HTTP response. On recovery, `status=queued` → re-queue; `status=running` → mark failed."
- D2.12 (DatabaseAdapter): the PM agent requires this decision to be explicit. Is the plan committing to SQLite-only for now? If so, the adapter exists as future-proofing but the Postgres implementation is deferred to Phase 10.
- D2.16 says "15 tables" but the milestone text says "17+" and the deliverables summary says "17+". Stale references from before sync table removal.

**Recommendation**:
- Split Phase 2 into 2 weeks (Week 3: core messaging tables; Week 4: radio, schedules, jobs, adapter).
- Add `[AUDIT C-2]` annotation to D2.11.
- Add `[AUDIT H-1]` task for `content_checksum` column on messages.
- Add `[AUDIT H-2]` annotation to D2.12.
- Update all stale "17+" references to "15".

---

### Phase 3: HAL & Radio Integration (Week 4–5)

**Assessment**: ✅ Good scope. 16 tasks over 2 weeks. HAL and radio endpoints are well-separated.

**Issues**:
- D3.2 (SBitxCLIDriver): no mention of telemetry stream reconnection logic (audit M-8). Add AC: "On telemetry stream exit, attempts exponential backoff reconnection (1s, 2s, 4s, ... up to 60s). After 10 consecutive failures, emits permanent disconnect."
- D3.9 (telemetry query): no performance benchmark (audit H-9). Add AC: "UNION ALL query across 7 daily tables (604,800 rows) completes in < 200ms on Pi 4 SD card. If not, alternative design documented."
- D3.11 (SWR protection): no diagnostic logging (audit M-9). Add AC: "SWR events logged to `swr_events` table with frequency, power, SWR reading, and profile context."
- D3.12–D3.16 are i18n tasks mixed into HAL phase. These are cross-cutting — consider whether they belong in Phase 3 or should be extracted into a parallel i18n track.

**Recommendation**: Add `[AUDIT H-9]` and `[AUDIT M-8]` annotations to relevant tasks.

---

### Phase 4: Messaging & Conversations (Week 6–8)

**Assessment**: ✅ Well-structured. 16 tasks over 3 weeks. Covers the full messaging lifecycle.

**Issues**:
- D4.15 (conversation list query optimization): the "critical query" is performance-speculative (audit M-6). The task should include a benchmark AC: "Query completes in < 50ms with 100 conversations × 100 messages on Pi 4 SD card. If not, denormalize `last_message_id` and `last_message_preview` onto conversations table."
- D4.16 (message_envelopes): references "localized templates" but there's no i18n resource definition for email templates in Phase 1 tasks.
- No task for conflict resolution strategy (audit H-4). Add task: "ADR-005: Document conflict resolution — last-writer-wins for edits, deletion trumps edit, union of reactions."

**Recommendation**: Add `[AUDIT H-4]` task. Add `[AUDIT M-6]` annotation to D4.15.

---

### Phase 5: WebSocket Gateway (Week 9–10)

**Assessment**: ✅ Good after sync engine removal. 12 tasks over 2 weeks. Covers protocol, events, backpressure, limits.

**Issues**:
- D5.10 (backpressure): the spec says "never silently drop state-changing events." ACs should verify: state events cause `STALE_CONNECTION` + code 4010; informational events (telemetry, typing) may drop but emit `STALE_TELEMETRY` notification.
- D5.4 (EventEmitter topic routing): should reference ADR-002 for the typed event map.
- No explicit test that WebSocket + REST reconnection flow works end-to-end. Consider adding: "E2E test: disconnect WebSocket, send 5 messages via REST, reconnect, verify new messages received via REST, then WebSocket pushes subsequent messages."

**Recommendation**: Add reconnection flow E2E test to D5.12 or as D5.13.

---

### Phase 6: Attachments, Geolocation & Scheduling (Week 11–12)

**Assessment**: ✅ Appropriate scope. 12 tasks over 2 weeks.

**Issues**:
- D6.5 (file size limit): "streaming" enforcement is mentioned but the implementation approach isn't clear. Fastify's `@fastify/multipart` handles streaming natively — reference this.
- D6.11 (schedule runner): what triggers the schedule runner? A `setInterval`? A cron-like timer? The task should specify the scheduling mechanism.
- No task for attachment integrity verification (audit H-1). At minimum, periodic re-read of attachment files against stored checksum should be a D6.x task.

**Recommendation**: Clarify schedule runner mechanism. Add attachment integrity task referencing H-1.

---

### Phase 7: System Management, Clock Sync & Resilience (Week 13–14)

**Assessment**: ⚠️ Most issues here. 17 tasks for 2 weeks is aggressive. Several tasks are large (D7.1 setup wizard, D7.9 boot recovery, D7.13 audit logging).

**Issues**:
- D7.14 (retention cron): still references `sync_queue (30d)` — stale reference. Remove.
- D7.14 (retention cron): specifies batch deletes but doesn't enforce batching strategy (audit M-7). Add AC: "DELETE in batches of 100 rows with `await sleep(100)` between batches."
- D7.8 (graceful shutdown): should include `systemctl` restart rate-limiting (audit C-3). Add AC: "Systemd unit includes `StartLimitIntervalSec=300` and `StartLimitBurst=5`."
- D7.5 (clock initialization): the spec says `created_at` is never mutated. Add AC: "Verify no retroactive timestamp updates — `created_at` is immutable after insertion."
- Missing tasks for audit H-7 and H-8: add `/health/stats` endpoint and `GET /system/alerts`.
- D7.13 (audit logging): "all significant actions" is vague. Reference the audited actions table from the database spec and list which actions must be logged.

**Recommendation**: Split Phase 7 into 3 weeks or reduce scope. Add `[AUDIT C-3]`, `[AUDIT H-7]`, `[AUDIT H-8]` tasks.

---

### Phase 8: Security Hardening & Legacy Compatibility (Week 15–16)

**Assessment**: ✅ Good scope. 10 tasks over 2 weeks.

**Issues**:
- D8.1 (rate limiting): "all limits from §8 of API spec" — list the specific limits in the ACs: 5/min on login, 30/min on message send, etc.
- D8.5 (TLS): "Manual" test type is appropriate but should specify what verification is performed: `openssl s_client -connect localhost:3000` confirms TLS 1.2+.
- D8.7–D8.8 (legacy shim): what happens after Phase 9? Is the shim maintained indefinitely or deprecated? Add a deprecation timeline to the task description.
- No task for password complexity validation (audit M-4). Add task: "Validate password against callsign (case-insensitive substring check). Deny common passwords list."

**Recommendation**: Add `[AUDIT M-4]` task. Clarify shim lifecycle.

---

### Phase 9: Testing, Validation & Deployment (Week 17–18)

**Assessment**: ✅ Good final phase. 10 tasks over 2 weeks.

**Issues**:
- D9.5 (memory profiling): "verify i18n overhead < 100 KB" — this is a single data point. Expand to full memory budget verification: V8 heap < 384 MB, SQLite cache < 8 MB, total RSS < 500 MB.
- D9.6 (SD card endurance): 72-hour run is mentioned but what's the pass/fail criteria? "No database corruption detected. No writes exceed expected volume (telemetry 1 Hz × 86,400/day)."
- D9.7 (power-loss): how many cycles? The comprehensive audit recommends 100 cycles. Add AC: "100 power-loss cycles without database corruption. All jobs rehydrated correctly from `jobs` table."
- Missing: no fault-injection tests (audit M-10). Add task: "Fault-injection tests: DB write failure simulation, malformed telemetry JSON parsing, WebSocket backpressure flood."

**Recommendation**: Add `[AUDIT M-10]` task. Expand ACs for D9.5–D9.7.

---

### Phase 10: Optional / Future

**Assessment**: ✅ Appropriate as a backlog. No issues — these are correctly deferred.

---

## 3. Recommended Quality Gates Per Phase

The PM agent requires: *"Each phase must be independently deployable and testable before the next begins."* Add these gates to each phase's milestone:

| Phase | Quality Gates |
|-------|--------------|
| **0** | `npm test` passes (empty suite). Drizzle migrations run against `:memory:`. All docs cross-references valid. |
| **1** | `npm run build` passes with zero TS errors. `POST /auth/login` returns JWT. `GET /health` returns 200. All protected routes reject unauthenticated requests with 401. |
| **2** | All 15 tables created with indexes. All repository unit tests pass (>80% coverage on `src/db/`). Migration pipeline works: `db:generate` → `db:migrate` → `db:rollback`. |
| **3** | SimulatedRadioDriver responds to all commands. Telemetry query (< 200ms on Pi 4 — benchmark documented even if not Pi 4 CI). SWR protection triggers TX cut. |
| **4** | Full messaging lifecycle E2E: create conversation → send message → track delivery → edit → react → soft delete. Idempotency verified. Conversation list query < 50ms with seeded data. |
| **5** | WebSocket `AUTHENTICATE` → `SUBSCRIBE` → receive events. Backpressure triggers `STALE_CONNECTION` code 4010. Heartbeat PING/PONG works. Reconnection + REST fetch works E2E. |
| **6** | File upload (50 MB) accepted and checksum-verified. GPS positions queryable by time range. Schedule runner triggers at `next_run_at`. |
| **7** | Power-loss simulation: 100 cycles without DB corruption. Clock sync: GPS → manual → saved fallback verified. Graceful shutdown checkpointed WAL. `/health/stats` returns counters. |
| **8** | All rate limits enforced. Helmet headers present. TLS 1.2+ confirmed. Legacy inbox/outbox shim returns correct data. NPM audit: 0 high/critical. |
| **9** | Test coverage ≥ 80%. Memory < 384 MB V8 heap on Pi 4. SD card 72-hour endurance test passes. Deployment script works on fresh Pi 4. |

---

## 4. Task Format Upgrade Recommendations

The current task format (`\| D1.1 \| Fastify v5 server with health endpoint \| Integration \|`) is too sparse. Upgrade to the PM agent's required format:

**Current (insufficient):**
```
| D1.7 | `POST /auth/login` — login with callsign + password | Integration |
```

**Recommended (executable):**
```markdown
### [ ] D1.7: POST /auth/login endpoint
**Description**: Implement login route per `docs/architecture/api.md §4.1`. POST /api/v1/auth/login accepts `{ callsign, password }`. Lookup user by callsign, verify bcrypt hash, generate JWT RS256 access token (15 min) + opaque refresh token (7 day), store refresh token SHA-256 hash in user_sessions.
**Acceptance Criteria**:
- [ ] Valid credentials → 200 `{ accessToken, refreshToken, expiresIn: 900 }`
- [ ] Invalid password → 401 `{ code: "UNAUTHENTICATED" }`
- [ ] Unknown callsign → 401 (same response as invalid password — constant time)
- [ ] 5+ failed attempts from same IP → 429 `{ code: "RATE_LIMITED" }`
- [ ] Successful login writes audit_logs entry `auth.login`
- [ ] Refresh token hash stored in user_sessions, never plaintext
- [ ] Error messages use user's locale from Accept-Language header
**Files to Create/Edit**:
- `src/api/v1/auth/login.ts` — route handler
- `src/api/v1/auth/login.schema.ts` — JSON Schema (AJV)
- `src/auth/password.ts` — bcrypt verify wrapper
- `src/auth/token.ts` — JWT sign utility
- `tests/integration/auth/login.test.ts` — integration tests
**Doc Reference**: `docs/architecture/api.md §4.1`, `docs/adr/adr-004-jwt-rs256-token-rotation.md`
**Blocks**: D1.8 (refresh needs login), D1.10 (sessions table needed for this task)
**Stack Notes**: Use `@fastify/jwt` for RS256. Use `bcrypt` with cost ≥ 12. Use Drizzle `db.select().from(users).where(eq(...))` — no raw SQL.
```

This format ensures the developer can pick up the task and implement it without asking questions.

---

## 5. Stale References to Fix

The plan still contains references to the removed sync engine:

| Line | Stale Text | Fix |
|------|-----------|-----|
| L91 (milestone) | ~correct (says "no sync tables needed") | ✅ OK |
| L317 (deliverables) | "All 17+ DB tables" | Change to "All 15 DB tables" |
| L320 (deliverables) | "offline sync engine" | Change to "real-time events, locale-aware notifications" |
| D7.14 | "sync_queue (30d)" | Remove this retention entry |

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|:---:|:---:|------------|
| **Phase 2 underestimated** — 16 DB tasks in 1 week | High | Phase 2 slips → cascading delays | Split into 2 weeks. Prioritize messaging tables (conversations, messages, deliveries) over utility tables (frequencies, schedules). |
| **Pi 4 hardware not available for Phase 3** — tests pass on dev machine but fail on Pi 4 | Medium | Phase 3–9 validation invalidated | Phase 3 gate: at least one telemetry benchmark on actual Pi 4 before Phase 4. Procure hardware in Phase 1. |
| **i18n translation incomplete** — Spanish/Portuguese files not ready by Phase 1 milestone | Medium | Phase 3+ tests fail on locale assertions | Phase 1 gate: `npm run i18n:check` passes for all 3 locales. Engage translators during Phase 0. |
| **Conversation list query performance** — spec query doesn't meet < 50ms on Pi 4 SD card | Medium | Phase 4 blocked until query is optimized | Pre-benchmark in Phase 2 with seeded data. Design denormalization fallback before Phase 4. |
| **Audit findings unaddressed** — C-2, C-3, H-1, H-7, H-8, H-9 have no tasks | High | Production incidents within weeks of field deployment | Address all 8 unmapped findings in this review before Phase 1. |
| **Phase 7 over-scoped** — 17 tasks in 2 weeks including setup wizard, boot recovery, audit logging | Medium | Phase 7 slips → deployment delayed | Split into 3 weeks or move D7.11 (apps) to Phase 10. |

---

## 7. Summary Assessment

| Dimension | Rating | Notes |
|-----------|:------:|-------|
| Spec alignment | 🟢 Good | All tasks trace to documented API, database, or ADR sections |
| Audit finding coverage | 🔴 Poor | 8 of 12 active findings (67%) have no corresponding task |
| Task granularity | 🟡 Needs work | Coarse tasks without ACs, file paths, or dependency notation |
| Phase boundaries | 🟢 Good | Phases are independently testable and build on each other |
| Quality gates | 🟡 Needs work | Milestones described but no objective go/no-go criteria |
| Risk management | 🟡 Needs work | Implicit; no explicit risk register or mitigation strategies |
| Timeline feasibility | 🟡 Needs work | Phase 2 (16 tasks/1 week) and Phase 7 (17 tasks/2 weeks) are aggressive |
| Scope discipline | 🟢 Good | No premature complexity; Phase 10 correctly defers federation/WebRTC |

**Overall**: The plan is **conceptually correct but operationally incomplete**. It defines *what* to build but not *how to verify completion*. Adding acceptance criteria, audit finding traceability, quality gates, and a risk register will make this plan executable by a development team without constant PM intervention.

**Recommended next action**: Before Phase 1 task breakdown, resolve the 8 unmapped audit findings and add quality gates to each phase milestone. Then break Phase 1 into executable task cards per the format in §4.

---

*Review completed July 2026. This document is a companion to `docs/development/plan.md` — it does not replace it.*