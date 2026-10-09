# Hermes Backend — Development Plan

Based on the current documentation structure and the sBitx v2 constraints, here's a phased development plan moving from architecture docs → working code.

> **Audit traceability**: Tasks marked with `[AUDIT X-N]` address findings from `docs/audits/comprehensive.md`. See `docs/development/plan-review.md` for the full mapping.

> **Go migration**: [ADR-006](../adr/adr-006-go-rewrite-and-station-consolidation.md) proposes rewriting the backend in Go and consolidating the backend, Mercury, and the radio daemon into a single linked process. The spike and port task list is in [`go-migration.md`](go-migration.md). The phase plan below describes the **Node.js/TypeScript** implementation and remains the behavioral specification the Go port must satisfy.

---

## Phase 0: Documentation & Tooling Setup (Current)

**Goal**: Solidify the specification before any code is written.

### D0.A — Documentation (Complete ✅)

| Task | Deliverable | Status |
|------|-------------|:---:|
| D0.A.1 | Core specs: `docs/architecture/api.md`, `docs/architecture/database.md` | ✅ Done |
| D0.A.2 | Architecture audit: `docs/audits/sbitx-v2.md` | ✅ Done |
| D0.A.3 | ADRs: 001 (SQLite), 002 (Event Bus), 003 (Messaging), 004 (JWT), 005 (Conflict Resolution) | ✅ Done |
| D0.A.4 | Root files: `README.md`, `LICENSE` (GPLv3), `CONTRIBUTING.md`, `CHANGELOG.md`, `.gitignore`, `.env.example` | ✅ Done |
| D0.A.5 | Dev docs: setup, CI/CD, testing, security | ✅ Done |
| D0.A.6 | Ops docs: deployment, WebSocket, hardware, observability | ✅ Done |
| D0.A.7 | Deprecated `docs/rest_api.md` (superseded by `docs/architecture/api.md`) | ✅ Done |
| D0.A.8 | i18n strategy: 3 languages (en, es, pt-BR) | ✅ Done |
| D0.A.9 | API docs updated with Accept-Language and localized errors | ✅ Done |
| D0.A.10 | Database docs updated with locale columns | ✅ Done |
| D0.A.11 | Plan review: `docs/development/plan-review.md` (PM audit) | ✅ Done |

### D0.B — Tooling Setup (Pending — Phase 1 Prerequisite)

| Task | Deliverable | Depends On |
|------|-------------|------------|
| D0.B.1 | Initialize repo: `package.json`, `tsconfig.json`, ESLint, Prettier, Vitest config | — |
| D0.B.2 | Set up Drizzle ORM with SQLite adapter, initial migration | D0.B.1 |
| **[AUDIT H-2]** D0.B.3 | Create `DatabaseAdapter` interface with SQLite implementation. **Decision**: commit to SQLite-only for sBitx v2. The adapter exists for future PostgreSQL migration (Phase 10+), but only the SQLite adapter is implemented and tested in Phases 1–9. | D0.B.2 |

**Milestone**: `npm test` passes with an empty test suite. Drizzle migrations run against an in-memory SQLite database. DatabaseAdapter strategy documented.

**Quality Gate**: `npm test` passes (empty suite). Drizzle migrations run against `:memory:`. All docs cross-references valid.

---

## Phase 1: Core Infrastructure & Auth (Week 1–2)

**Goal**: Fastify server boots, connects to SQLite, users can authenticate.

| Task | Deliverable | Tests |
|------|-------------|-------|
| D1.1 | Fastify v5 server with health endpoint (`GET /health`, `GET /health/deep`) | Integration |
| D1.2 | SQLite connection with WAL PRAGMAs (`busy_timeout=5000`, `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`) per `docs/architecture/database.md §12.2` | Unit |
| D1.3 | Configuration loader: env vars (`DATABASE_PATH`, `JWT_PRIVATE_KEY_PATH`, `CORS_ORIGINS`, `LOG_LEVEL`, `RADIO_DRIVER`, `DB_ADAPTER`) via `src/shared/config.ts` — no `process.env` in modules | Unit |
| D1.4 | `users` table + repository (Drizzle) | Unit |
| D1.5 | Password hashing (bcrypt, cost ≥ 12) | Unit |
| D1.6 | JWT RS256 key pair generation + sign/verify utilities | Unit |
| D1.7 | `POST /auth/login` — login with callsign + password. ACs: 200 `{ accessToken, refreshToken, expiresIn: 900 }` for valid creds; 401 for invalid; 429 after 5 failed attempts from same IP; audit_logs entry on success; refresh token stored as SHA-256 hash, never plaintext. **Files**: `src/api/v1/auth/login.ts`, `src/api/v1/auth/login.schema.ts`, `src/auth/password.ts`, `src/auth/token.ts`, `tests/integration/auth/login.test.ts`. **Doc Ref**: `docs/architecture/api.md §4.1`, ADR-004. **Stack**: `@fastify/jwt` for RS256, `bcrypt` cost ≥ 12, Drizzle parameterized queries. | Integration |
| D1.8 | `POST /auth/refresh` — token rotation with reuse detection per ADR-004. ACs: valid refresh → new access+refresh pair; reused token → revoke ALL sessions + audit log `auth.token_reuse_detected`; expired token → 401. **Blocks**: D1.7 (needs login), D1.10 (needs sessions table). | Integration |
| D1.9 | `POST /auth/logout` — session revocation | Integration |
| D1.10 | `user_sessions` table + repository | Unit |
| D1.11 | Auth middleware chain: CORS → Helmet → Rate Limiter → JWT Verifier → RBAC Guard. ACs: unauthenticated → 401; wrong role → 403; expired token → 401. | Unit + Integration |
| D1.12 | `GET /users/me`, `POST /users`, `GET /users` (admin) | Integration |
| D1.13 | i18n: `src/i18n/` structure — locale detector, resource loader, `t()` function. **Fallback chain**: user preference → `Accept-Language` header → `en`. | Unit |
| D1.14 | i18n: resource files `en/` — extract existing strings from codebase | Unit |
| D1.15 | i18n: resource files `es/` — complete Spanish translation | Unit |
| D1.16 | i18n: resource files `pt-BR/` — complete Portuguese (Brazil) translation | Unit |
| D1.17 | i18n: `locale` field in JWT payload + `users.locale` column | Unit + Integration |

**Milestone**: API boots. `POST /auth/login` returns JWT tokens with locale. Protected routes reject unauthenticated requests. Error messages rendered in user's preferred language (en/es/pt-BR).

**Quality Gate**: `npm run build` passes with zero TS errors. `POST /auth/login` returns JWT. `GET /health` returns 200. All protected routes reject unauthenticated requests with 401. `npm run i18n:check` passes for all 3 locales.

---

## Phase 2: Database Layer & Repository Pattern (Week 3–4)

**Goal**: Complete database layer with all tables, migrations, and the adapter interface. **Split into 2 weeks** — Week 3: core messaging tables; Week 4: radio, schedules, jobs, adapter.

### Week 3: Core Messaging Tables

| Task | Deliverable | Tests |
|------|-------------|-------|
| D2.1 | `conversations` table + repository | Unit |
| D2.2 | `conversation_participants` table + repository | Unit |
| D2.3 | `messages` table + repository (with idempotency via `client_message_id`) | Unit |
| **[AUDIT H-1]** D2.3a | `content_checksum` column on `messages` (SHA-256 of `content` at write time). Enables future integrity verification per `docs/audits/comprehensive.md H-1`. | Unit |
| D2.4 | `message_deliveries` table + repository | Unit |
| D2.5 | `message_reactions` table + repository | Unit |
| D2.6 | `attachments` table + repository | Unit |
| D2.7 | `message_envelopes` table + repository | Unit |

### Week 4: Radio, Schedules, Jobs & Adapter

| Task | Deliverable | Tests |
|------|-------------|-------|
| D2.8 | `radio_profiles` + `radio_sessions` tables + repositories | Unit |
| D2.9 | `frequencies` + `connection_schedules` tables + repositories | Unit |
| D2.10 | `audit_logs` table + repository (immutable, append-only) | Unit |
| **[AUDIT C-2]** D2.11 | `jobs` table + repository (SQLite-backed queue). **Mandatory persistence**: write job to DB with `status=queued` BEFORE acknowledging HTTP response. On recovery, re-queue all `queued` jobs; mark `running` as `failed`. No best-effort fallback — `queued` must be durable. | Unit |
| **[AUDIT H-2]** D2.12 | `DatabaseAdapter` interface implemented for all repositories. SQLite-only implementation (PostgreSQL deferred to Phase 10). | Unit |
| D2.13 | Migration pipeline: `npm run db:generate`, `db:migrate`, `db:rollback` | Manual |
| D2.14 | Migration: add `locale` column to `users` table (DEFAULT 'en', CHECK IN) | Unit |
| D2.15 | Migration: add `locale` column to `audit_logs` table (DEFAULT 'en') | Unit |
| D2.16 | Migration: add `locale` column to `message_envelopes` table (DEFAULT 'en') | Unit |

**Milestone**: All 15 tables created, indexed, and queryable. All repository unit tests pass against in-memory SQLite. Locale columns present on all i18n-relevant tables. Job queue persistence is mandatory, not best-effort. DatabaseAdapter strategy: SQLite-only.

**Quality Gate**: All 15 tables created with indexes. All repository unit tests pass (>80% coverage on `src/db/`). Migration pipeline works: `db:generate` → `db:migrate` → `db:rollback`.

---

## Phase 3: HAL & Radio Integration (Week 5–6)

**Goal**: Hardware Abstraction Layer talks to sBitx CLI. Radio status and telemetry endpoints work.

| Task | Deliverable | Tests |
|------|-------------|-------|
| D3.1 | `IRadioDriver` interface definition | — |
| **[AUDIT M-8]** D3.2 | `SBitxCLIDriver` — wraps `execFile` calls to sBitx CLI. **Telemetry reconnection**: exponential backoff (1s, 2s, 4s, ... up to 60s). After 10 consecutive failures, emit permanent disconnect. | Unit (mocked) |
| D3.3 | `SimulatedRadioDriver` — fake radio for testing/development | Unit |
| D3.4 | Radio profiles CRUD endpoints (`/radio/profiles`) | Integration |
| D3.5 | `GET /radio/status` — real-time radio snapshot | Integration |
| D3.6 | `POST /radio/ptt` — push-to-talk | Integration |
| D3.7 | `POST /radio/profiles/:idx/frequency` — set frequency | Integration |
| D3.8 | Radio telemetry recording: 1 Hz snapshots → `telemetry_YYYYMMDD` tables | Integration |
| **[AUDIT H-9]** D3.9 | `GET /radio/telemetry` — time-range query with UNION ALL across daily tables. **Performance gate**: benchmark 7-day query (604,800 rows) on Pi 4 SD card. Must complete < 200ms. If not, document alternative design (single table with composite index). | Integration |
| D3.10 | `GET /radio/sessions` — radio session history | Integration |
| **[AUDIT M-9]** D3.11 | SWR protection handling + `POST /radio/protection/reset`. **Diagnostic logging**: SWR events logged to `swr_events` table with frequency, power, SWR reading, and profile context. | Integration |
| D3.12 | i18n: locale detection middleware (AsyncLocalStorage per request) | Unit |
| D3.13 | i18n: localized error responses across all endpoints (RFC 7807 `message` + `details`) | Integration |
| D3.14 | i18n: translated AJV validation error messages (JSON Schema) | Integration |
| D3.15 | i18n: WebSocket `AUTHENTICATED` frame includes `locale` field | Integration |
| D3.16 | i18n: WebSocket system events localized (`SYSTEM_NOTIFICATION`, `CLOCK_SYNCED`) | Integration |

**Milestone**: Simulated radio responds to commands. Telemetry is recorded and queryable by time range (< 200ms on Pi 4). SWR events have diagnostic context. All API errors and WebSocket system messages are localized.

**Quality Gate**: SimulatedRadioDriver responds to all commands. Telemetry query < 200ms on Pi 4 (benchmark documented). SWR protection triggers TX cut with diagnostic logging.

---

## Phase 4: Messaging & Conversations (Week 7–9)

**Goal**: Full conversation-based messaging with delivery tracking.

| Task | Deliverable | Tests |
|------|-------------|-------|
| **[AUDIT H-4]** D4.0 | ADR-005: Conflict Resolution Strategy. Document last-writer-wins for edits (tiebreaker: `updated_at`), deletion trumps edit, union of reactions. Client messages created offline are unchanged on reconnect (single source of truth model). | — |
| D4.1 | `POST /conversations` — create direct/group/broadcast | Integration |
| D4.2 | `GET /conversations` — paginated list with `contentPreview` and unread counts | Integration |
| D4.3 | `GET /conversations/:id` — conversation detail | Integration |
| D4.4 | `PATCH /conversations/:id` — update title/metadata | Integration |
| D4.5 | Participant management: add, remove, list | Integration |
| D4.6 | `POST /conversations/:id/messages` — send message with idempotency | Integration |
| D4.7 | `GET /conversations/:id/messages` — cursor-based pagination | Integration |
| D4.8 | `PATCH /conversations/:id/messages/:msgId` — edit message. Per ADR-005: last-writer-wins; earlier edits silently discarded. | Integration |
| D4.9 | `DELETE /conversations/:id/messages/:msgId` — soft delete. Per ADR-005: deletion always wins over concurrent edits. | Integration |
| D4.10 | Message reactions: add/remove. Per ADR-005: union of reactions (no conflict). | Integration |
| D4.11 | `POST /conversations/:id/read` — mark read | Integration |
| D4.12 | Delivery tracking: per-recipient, per-channel (`message_deliveries`) | Integration |
| D4.13 | Message content validation: 64 KB max, reject oversized payloads | Unit |
| D4.14 | Participant limit enforcement: direct=2, group=50, broadcast=200 | Unit |
| **[AUDIT M-6]** D4.15 | Conversation list query optimization (the critical query). **Performance gate**: query completes in < 50ms with 100 conversations × 100 messages on Pi 4 SD card. If not, denormalize `last_message_id` and `last_message_preview` onto conversations table. | Performance test |
| D4.16 | `message_envelopes` — email/SMTP transport envelope creation with localized templates | Integration |

**Milestone**: Full messaging lifecycle works: create conversation → send message → track delivery → edit/delete/react. Idempotency prevents duplicates. ADR-005 defines conflict resolution. Conversation list query < 50ms. Email envelopes include locale for template selection.

**Quality Gate**: Full messaging lifecycle E2E: create conversation → send message → track delivery → edit → react → soft delete. Idempotency verified (duplicate `client_message_id` returns same message). Conversation list query < 50ms with seeded data (100 convos × 100 messages).

---

## Phase 5: WebSocket Gateway (Week 10–11)

**Goal**: Real-time event streaming via WebSocket. No sync protocol needed — clients fetch current state via REST on reconnect.

| Task | Deliverable | Tests |
|------|-------------|-------|
| D5.1 | WebSocket upgrade handler (subprotocol `hermes-v1`) | Integration |
| D5.2 | `AUTHENTICATE` / `AUTHENTICATED` flow with `serverTime` and `locale` | Integration |
| D5.3 | `SUBSCRIBE` / `SUBSCRIBED` topic management | Integration |
| D5.4 | In-process EventEmitter topic routing (reference ADR-002 for typed event map) | Unit |
| D5.5 | `RADIO_TELEMETRY` event push (1 Hz) | Integration |
| D5.6 | `MESSAGE_NEW`, `MESSAGE_DELIVERED`, `MESSAGE_READ` events | Integration |
| D5.7 | `TYPING_START` / `TYPING_STOP` (rate-limited: 1 per 2 sec) | Integration |
| D5.8 | `PRESENCE_UPDATE` — online/offline/away | Integration |
| D5.9 | Heartbeat: PING/PONG every 30 seconds | Integration |
| D5.10 | WebSocket backpressure handling: state-changing events → `STALE_CONNECTION` + code `4010` (never silently dropped); informational events (telemetry, typing) may drop but emit `STALE_TELEMETRY` notification | Integration |
| D5.11 | WebSocket connection limits (max 20 concurrent) | Integration |
| D5.12 | Auth timeout: drop unauthenticated connections after 10s | Integration |
| D5.13 | E2E reconnection flow: disconnect WebSocket → send 5 messages via REST → reconnect WebSocket → verify new messages received via `GET /conversations/:id/messages` (REST) → subsequent messages pushed via WebSocket | E2E |

**Milestone**: WebSocket clients receive real-time radio telemetry and message events. Reconnection is handled purely via REST API. No sync engine, no cursor management, no delta batching. System notifications are locale-aware per connection.

**Quality Gate**: WebSocket `AUTHENTICATE` → `SUBSCRIBE` → receive events. Backpressure triggers `STALE_CONNECTION` code 4010 (state events never silently dropped). Heartbeat PING/PONG works. Reconnection + REST fetch works E2E.

---

## Phase 6: Attachments, Geolocation & Scheduling (Week 12–13)

**Goal**: File uploads, GPS tracking, and connection schedules work.

| Task | Deliverable | Tests |
|------|-------------|-------|
| D6.1 | `POST /attachments` — multipart upload with MIME validation (use `@fastify/multipart` for streaming) | Integration |
| D6.2 | SHA-256 checksum deduplication | Unit |
| D6.3 | `GET /attachments/:id/download` — signed time-limited URLs | Integration |
| D6.4 | Attachment token for HF radio store-and-forward (30-day expiry) | Unit |
| D6.5 | File size limit enforcement (50 MB, streaming via `@fastify/multipart`) | Integration |
| D6.6 | `POST /geolocation` — report GPS position | Integration |
| D6.7 | `GET /geolocation/current` — latest position | Integration |
| D6.8 | `GET /geolocation/history` — time-range query across daily tables | Integration |
| D6.9 | `POST /frequencies` — create frequency preset | Integration |
| D6.10 | `POST /schedules` — create connection schedule with recurrence | Integration |
| D6.11 | Schedule runner: `setInterval`-based timer checks `next_run_at` every 30 seconds, triggers radio connection via HAL when due | Unit |
| D6.12 | `POST /schedules/:id/cancel` — cancel scheduled connection | Integration |
| **[AUDIT H-1]** D6.13 | Attachment integrity verification: background job (weekly) re-reads random sample of attachment files, verifies against stored `checksum`. Logs mismatches at ERROR. | Unit |

**Milestone**: Files can be uploaded, downloaded, and linked to messages. GPS positions are recorded and queryable by time range. Connection schedules are created and executed. Attachment integrity verified weekly.

**Quality Gate**: File upload (50 MB) accepted and checksum-verified. GPS positions queryable by time range. Schedule runner triggers at `next_run_at`.

---

## Phase 7: System Management, Clock Sync & Resilience (Week 14–16)

**Goal**: Station management, clock synchronization, and power-loss resilience. **Split into 3 weeks** — Week 14: setup wizard + config; Week 15: clock sync + recovery; Week 16: audit logging + observability.

### Week 14: Setup & Configuration

| Task | Deliverable | Tests |
|------|-------------|-------|
| D7.1 | `POST /setup` — first-time setup wizard with locale detection & selection | Integration |
| D7.2 | `GET /system/config`, `PATCH /system/config` | Integration |
| D7.15 | i18n: setup wizard locale detection via `Accept-Language` header | Integration |
| D7.16 | i18n: `PATCH /users/me` accepts `locale` field (token invalidation on change) | Integration |
| D7.17 | i18n: `npm run i18n:check` script — validates all locales have the same keys | Unit |

### Week 15: Clock Sync & Recovery

| Task | Deliverable | Tests |
|------|-------------|-------|
| D7.3 | `GET /system/clock` — clock sync status endpoint | Integration |
| D7.4 | `POST /system/clock/sync` — manual clock set | Integration |
| D7.5 | Clock initialization sequence: saved timestamp → GPS → manual. **AC**: `created_at` is NEVER mutated after insertion. When clock syncs, only new messages get correct timestamps. | Unit |
| D7.6 | GPS NMEA sentence parser for UTC time extraction | Unit |
| D7.7 | `last_known_time` file write on graceful shutdown | Unit |
| **[AUDIT C-3]** D7.8 | Graceful shutdown handler (GPIO signal / systemd stop). **Systemd hardening**: unit file includes `StartLimitIntervalSec=300` and `StartLimitBurst=5` to prevent SD card destruction loops. `ExecStartPre` runs `PRAGMA integrity_check`. | Integration |
| D7.9 | Boot-time recovery: rehydrate job queue, WAL auto-recovery. **AC**: `jobs` with `status=queued` → re-queued; `status=running` → marked `failed`. | Integration |
| D7.10 | `POST /system/reboot`, `POST /system/shutdown` | Integration |

### Week 16: Observability & Retention

| Task | Deliverable | Tests |
|------|-------------|-------|
| D7.11 | `GET /apps`, `POST /apps/install` | Integration |
| D7.12 | `GET /metrics` — Prometheus endpoint (disabled by default) | Integration |
| D7.13 | Audit logging: all significant actions written to `audit_logs` with `locale` context. Reference audited actions table in `docs/architecture/database.md §4.9` for complete list (auth.*, user.*, message.*, conversation.*, radio.*, system.*, attachment.*). | Integration |
| D7.14 | Retention cleanup cron: telemetry (90d), GPS (365d), audit (2y), deleted messages (90d), sessions (7d expired), jobs (30d completed). **AC**: DELETE in batches of 100 rows with `await sleep(100)` between batches to yield write lock. | Unit |
| **[AUDIT H-7/H-8]** D7.18 | `/health/stats` JSON endpoint: returns key counters (`http_requests_total`, `messages_sent_total`, `ws_connections_active`, `ws_events_dropped_total`, `db_slow_queries_total`, `memory_heap_mb`, `memory_rss_mb`, `uptime_seconds`). No Prometheus required. | Integration |
| **[AUDIT H-7]** D7.19 | `GET /system/alerts` endpoint: returns last 100 warning events (24h window) from in-memory ring buffer. Wraps all event bus listeners in try/catch to prevent cascading failures. | Integration |

**Milestone**: Station can be set up from scratch in any supported language. Clock syncs from GPS or manual input. Power loss is handled gracefully with < 10 second recovery. Systemd restart rate-limiting prevents SD card destruction. `/health/stats` provides operational visibility without Prometheus.

**Quality Gate**: Power-loss simulation: 100 cycles without DB corruption. Clock sync: GPS → manual → saved fallback verified. Graceful shutdown checkpointed WAL. `/health/stats` returns counters. `GET /system/alerts` returns recent warnings.

---

## Phase 8: Security Hardening & Legacy Compatibility (Week 17–18)

**Goal**: Production-ready security and backward compatibility.

| Task | Deliverable | Tests |
|------|-------------|-------|
| D8.1 | Rate limiting: all limits from `docs/architecture/api.md §8` enforced. **ACs**: login 5/15min/IP, refresh 20/hr/user, general REST 300/min/user, radio commands 60/min/user, file upload 20/hr/user, WebSocket messages 60/min/connection, typing 1/2sec/conversation. | Integration |
| **[AUDIT M-4]** D8.1a | Password complexity validation: must not contain user's callsign (case-insensitive substring). Deny common passwords list ("password", "hamradio", "sbitx", "hermes"). Recommend (not enforce) mixed case + digits + symbols. | Unit |
| D8.2 | Content validation: `maxLength` on all string fields | Unit |
| D8.3 | Helmet security headers configured | Integration |
| D8.4 | CORS allowlist | Integration |
| D8.5 | TLS 1.2+ configuration. **Verification**: `openssl s_client -connect localhost:3000` confirms TLS 1.2+. HSTS enabled in production. | Manual |
| D8.6 | JWT key rotation support (invalidates tokens, clients re-auth with new locale) | Unit |
| D8.7 | Legacy compatibility shim: `GET /messages/inbox`, `GET /messages/outbox`, `GET /messages/:id`. Read-only shim — maintained through Phase 9, deprecated thereafter (removal timeline: Phase 10+). | Integration |
| D8.8 | Legacy write endpoints redirected to new conversation API. `POST /messages/send` → 308 redirect to `POST /conversations/:id/messages`. | Integration |
| D8.9 | Input sanitization: CLI args via `execFile` arrays (no shell). **AC**: verify no `child_process.exec` with string interpolation exists in HAL code. | Unit |
| D8.10 | SQL injection: verify all queries use Drizzle parameterized queries. Raw SQL only in migration files. | Review |

**Milestone**: All security controls active. Legacy endpoints work with documented deprecation timeline. System is production-ready for field deployment.

**Quality Gate**: All rate limits enforced (verify each tier). Helmet headers present. TLS 1.2+ confirmed via `openssl s_client`. Legacy inbox/outbox shim returns correct data. NPM audit: 0 high/critical.

---

## Phase 9: Testing, Validation & Deployment (Week 19–20)

**Goal**: Test suite complete. Deployable to Raspberry Pi 4.

| Task | Deliverable | Tests |
|------|-------------|-------|
| D9.1 | Unit test coverage ≥ 80% across all modules (including i18n) | — |
| D9.2 | Integration tests for all API endpoints (with `Accept-Language` variants) | — |
| **[AUDIT M-10]** D9.2a | Fault-injection tests: DB write failure simulation (test double for adapter), malformed telemetry JSON parsing (mixed valid/invalid lines), WebSocket backpressure flood (trigger `STALE_CONNECTION` code 4010) | Unit + Integration |
| D9.3 | E2E tests: simulated radio + WebSocket client + message flow + locale switching | — |
| D9.4 | Load test: 3 concurrent WebSocket clients + 1 Hz telemetry + message send/receive | Performance |
| D9.5 | Memory profiling on actual Pi 4 hardware. **ACs**: V8 heap < 384 MB, SQLite cache < 8 MB, total RSS < 500 MB, i18n overhead < 100 KB. | Manual |
| D9.6 | SD card write endurance test (72-hour run). **ACs**: no database corruption detected, no writes exceed expected volume (telemetry 1 Hz × 86,400/day). | Manual |
| D9.7 | Power-loss simulation: 100 cycles. **ACs**: no database corruption, all jobs rehydrated correctly from `jobs` table, WAL auto-recovery < 1 second. | Manual |
| D9.8 | Systemd service unit file (with `StartLimitIntervalSec=300`, `StartLimitBurst=5`, `MemoryMax=500M`) | — |
| D9.9 | Deployment script for sBitx v2 | — |
| D9.10 | `README.md` updated with install/run instructions and language configuration | — |

**Milestone**: All tests pass (≥ 80% coverage). Memory usage stays under 384 MB V8 heap. Pi 4 deployment tested with real sBitx hardware. All 3 languages verified in E2E tests. Fault-injection confirms error paths handled gracefully.

**Quality Gate**: Test coverage ≥ 80%. Memory < 384 MB V8 heap on Pi 4. SD card 72-hour endurance test passes (no corruption). Power-loss: 100 cycles without corruption. Deployment script works on fresh Pi 4.

---

## Phase 10: Optional / Future (Beyond Week 20)

| Task | Notes |
|------|-------|
| WebRTC audio (peer-to-peer) | Gated behind `ENABLE_WEBRTC=true`; only if LAN audio is needed |
| PostgreSQL adapter | For multi-station server deployments (Phase 10+ federation) |
| Redis adapter | For multi-process deployments (swap in-process event bus to Redis Pub/Sub) |
| GraphQL gateway | Alternative to REST for complex queries |
| Multi-radio support | Multiple sBitx devices on one station |
| Federation protocol | Station-to-station sync over HF |
| Machine translation of messages | `message_translations` table; automatic translation via offline model or external API |
| Additional languages | Extend to French (fr), Quechua (qu), Guarani (gn) — community-driven translations |
| RTL language support | Arabic (ar), Hebrew (he) — requires CSS/bidirectional text support in Web UI |
| Legacy shim removal | Remove D8.7/D8.8 compatibility shim after sufficient migration window |

---

## i18n Summary

Internationalization is integrated across all phases, not bolted on at the end:

| Phase | i18n Tasks |
|-------|------------|
| Phase 0 | Documentation: `docs/development/i18n.md`, updates to api.md, database.md |
| Phase 1 | Core infrastructure: `src/i18n/` module, locale detector, resource files (en/es/pt-BR), JWT locale field |
| Phase 2 | Database: `locale` columns on `users`, `audit_logs`, `message_envelopes` tables |
| Phase 3 | API & WebSocket: locale middleware, localized errors, localized WebSocket events |
| Phase 7 | Setup wizard locale detection, `PATCH /users/me` locale field, `i18n:check` script |
| Phase 9 | Test coverage for i18n, E2E with locale switching, memory profiling |

### Supported Languages

| Code | Language | Coverage | Priority |
|------|----------|----------|:---:|
| `en` | English | 100% (fallback) | P0 |
| `es` | Español | 100% | P0 |
| `pt-BR` | Português (Brasil) | 100% | P1 |

### Design Decisions

- **No runtime translation libraries**: Plain JSON files loaded at startup — no `i18next` or similar heavy dependency. Total overhead ~60 KB for all 3 languages.
- **Locale in JWT**: Avoids database query on every request to determine user language preference.
- **Fallback chain**: User preference → `Accept-Language` header → `en`.
- **Terminology**: Radio technical terms (frequency, mode, PTT, SWR, SNR) kept in English per international ham radio convention.
- **User messages NOT translated**: Message content is stored and transmitted as-is. Machine translation is a future optional feature (Phase 10+).

---

## Deliverables by Phase

```
Phase 0:  docs/ clean, package.json, tsconfig, Drizzle init, ADR-005 (conflict resolution)
Phase 1:  Fastify server, auth (login/refresh/logout), RBAC middleware, i18n core module + translations
Phase 2:  All 15 DB tables (with content_checksum), repositories, DatabaseAdapter, migrations, locale columns
Phase 3:  HAL, sBitx CLI driver (with telemetry reconnection), radio status, telemetry recording, localized errors & WebSocket
Phase 4:  Conversations, messages, delivery tracking, reactions, conflict resolution (ADR-005), localized email templates
Phase 5:  WebSocket gateway, real-time events, backpressure handling, E2E reconnection flow
Phase 6:  File uploads, GPS tracking, frequency presets, schedules, attachment integrity verification
Phase 7:  Setup wizard with locale, clock sync, graceful shutdown (systemd hardening), boot recovery, retention, /health/stats, /system/alerts
Phase 8:  Rate limiting, password complexity, security headers, TLS, legacy shim (with deprecation timeline)
Phase 9:  80%+ test coverage (incl. fault injection), Pi 4 profiling, SD card endurance, power-loss simulation, deployment scripts
```

---

## Audit Finding Traceability Summary

| Finding | Severity | Phase | Task |
|---------|:---:|:---:|------|
| C-1 | 🔴 | — | ✅ Resolved (sync engine removed) |
| C-2 | 🔴 | 2 | D2.11 — Mandatory job persistence |
| C-3 | 🔴 | 7 | D7.8 — Systemd restart rate-limiting |
| C-4 | 🔴 | — | ✅ Resolved (sync engine removed) |
| H-1 | 🟠 | 2, 6, 7 | D2.3a — content_checksum; D6.13 — attachment integrity; D7.18 — health/deep check |
| H-2 | 🟠 | 0, 2 | D0.B.3, D2.12 — SQLite-only decision documented |
| H-3 | 🟠 | — | ✅ Resolved (sync engine removed) |
| H-4 | 🟠 | 4 | D4.0 — ADR-005 conflict resolution |
| H-5 | 🟠 | 5 | D5.10 — Backpressure handling (already captured) |
| H-6 | 🟠 | 5 | D5.11 — Connection limits (already captured) |
| H-7 | 🟠 | 7 | D7.18, D7.19 — /health/stats, /system/alerts, event listener hardening |
| H-8 | 🟠 | 7 | D7.18 — Combined with H-7 (/health/stats) |
| H-9 | 🟠 | 3 | D3.9 — Telemetry benchmark on Pi 4 |
| M-4 | 🟡 | 8 | D8.1a — Password complexity validation |
| M-6 | 🟡 | 4 | D4.15 — Conversation query benchmark |
| M-8 | 🟡 | 3 | D3.2 — Telemetry stream reconnection |
| M-9 | 🟡 | 3 | D3.11 — SWR event diagnostic logging |
| M-10 | 🟡 | 9 | D9.2a — Fault-injection tests |
| M-13 | 🟡 | 0 | Quality gates added to all phase milestones |