# Development Progress — Hermes Backend

**Purpose**: Single source of truth for AI agent session handoff. Updated after every completed task.

---

## Current State

| Field | Value |
|-------|-------|
| **Phase** | 3 — HAL & Radio Integration |
| **Branch** | `feat/phase-3-hal-radio` |
| **Last Commit** | `eedcf1c` — chore(node): target Node.js 20.19 (Debian 13 Trixie) |
| **PR** | Not yet opened |
| **PR URL** | — |

---

## Task Status

### Phase 0.B — Tooling Setup

| Task | Status | Commit |
|------|:------:|--------|
| D0.B.1 — Initialize repo (`package.json`, `tsconfig.json`, ESLint, Prettier, Vitest) | ✅ | `91452aa` |
| D0.B.2 — Set up Drizzle ORM with SQLite adapter, initial migration | ✅ | `8363247` |
| D0.B.3 — Create `DatabaseAdapter` interface + `SQLiteAdapter` implementation | ✅ | `3163eb0` |
| Quality Gate — `npm test`, `npm run build`, migration against `:memory:` | ✅ | `3163eb0` |
| Review fixes — prune deps, drop baseUrl, vite-tsconfig-paths, meaningful test | ✅ | `02651b1` |

### Phase 1 — Core Infrastructure & Auth

| Task | Status | Commit |
|------|:------:|--------|
| D1.1 — Fastify v5 server with health endpoint (`GET /health`, `GET /health/deep`) | ✅ | `e8cdc2d` |
| D1.2 — SQLite connection with WAL PRAGMAs | ✅ | `e8cdc2d` |
| D1.3 — Configuration loader (`src/shared/config.ts`) | ✅ | `e8cdc2d` |
| D1.4 — `users` table + repository (Drizzle) | ✅ | `aba6762` |
| D1.5 — Password hashing (bcrypt, cost ≥ 12) + unit tests | ✅ | `b333617` |
| D1.6 — JWT RS256 key pair generation + sign/verify utilities + unit tests | ✅ | `b333617` |
| D1.7 — `POST /auth/login` | ✅ | `aba6762` |
| D1.8 — `POST /auth/refresh` — token rotation with reuse detection | ✅ | `54d4183` |
| D1.9 — `POST /auth/logout` | ✅ | `5c67f75` |
| D1.10 — `user_sessions` table + repository | ✅ | `aba6762` |
| D1.11 — Auth middleware chain (CORS → Helmet → Rate Limiter → JWT Verifier → RBAC Guard) | ✅ | `79977fd` |
| D1.12 — `GET /users/me`, `POST /users`, `GET /users` (admin) | ✅ | `8ef638b` |
| D1.13 — i18n: `src/i18n/` structure — locale detector, resource loader, `t()` function | ✅ | `ca2b948` |
| D1.14 — i18n: resource files `en/` — extract existing strings from codebase | ✅ | `ca2b948` |
| D1.15 — i18n: resource files `es/` — complete Spanish translation | ✅ | `ca2b948` |
| D1.16 — i18n: resource files `pt-BR/` — complete Portuguese (Brazil) translation | ✅ | `ca2b948` |
| D1.17 — i18n: `locale` field in JWT payload + `users.locale` column | ✅ | `ca2b948` |
| Review fixes — pt prefix collision, TranslationKey union type, D3.12 comment | ✅ | `025b89c` |

### Phase 2 — Database Layer & Repository Pattern

| Task | Status | Commit |
|------|:------:|--------|
| D2.1 — conversations table + repository | ✅ | `7b59eea` |
| D2.2 — conversation_participants table + repository | ✅ | `e2e5c3a` |
| D2.3 — messages table + repository (idempotency) | ✅ | `f581104` |
| D2.3a — content_checksum column (AUDIT H-1) | ✅ | `f581104` |
| D2.4 — message_deliveries table + repository | ✅ | `1a4f373` |
| D2.5 — message_reactions table + repository | ✅ | `1a4f373` |
| D2.6 — attachments table + repository | ✅ | `1a4f373` |
| D2.7 — message_envelopes table + repository | ✅ | `1a4f373` |
| D2.8 — radio_profiles + radio_sessions tables + repos | ✅ | `aa6b9f6` |
| D2.9 — frequencies + connection_schedules tables + repos | ✅ | `aa6b9f6` |
| D2.10 — audit_logs table + repository (immutable, append-only) | ✅ | `aa6b9f6` |
| D2.11 — jobs table + repository (SQLite-backed queue) | ✅ | `aa6b9f6` |
| user_devices table + repository | ✅ | `aa6b9f6` |
| D2.12 — DatabaseAdapter interface for all repositories | ✅ | (inherent — all repos inject adapter) |
| D2.13 — Migration pipeline (0002_add_phase2_tables.sql) | ✅ | `e3f0ed8` |
| D2.14 — locale column on users (already exists from Phase 1) | ✅ | N/A (Phase 1) |
| D2.15 — locale column on audit_logs | ✅ | `aa6b9f6` |
| D2.16 — locale column on message_envelopes | ✅ | `aa6b9f6` |

### Phase 3 — HAL & Radio Integration

| Task | Status | Commit |
|------|:------:|--------|
| D3.1 — IRadioDriver interface definition | ✅ | `81172d1` |
| D3.2 — SBitxCLIDriver (exponential backoff, telemetry reconnection) [AUDIT M-8] | ✅ | `cb3ed42` |
| D3.3 — SimulatedRadioDriver (fake radio for testing) | ✅ | `e767f27` |
| D3.4 — Radio profiles CRUD endpoints (`/radio/profiles`) | ✅ | `1e3adec` |
| D3.5 — `GET /radio/status` — real-time radio snapshot | ⬜ | — |
| D3.6 — `POST /radio/ptt` — push-to-talk | ⬜ | — |
| D3.7 — `POST /radio/profiles/:idx/frequency` — set frequency | ⬜ | — |
| D3.8 — Radio telemetry recording: 1 Hz snapshots → `telemetry_YYYYMMDD` tables | ⬜ | — |
| D3.9 — `GET /radio/telemetry` — time-range query with UNION ALL [AUDIT H-9] | ⬜ | — |
| D3.10 — `GET /radio/sessions` — radio session history | ⬜ | — |
| D3.11 — SWR protection handling + `POST /radio/protection/reset` [AUDIT M-9] | ⬜ | — |
| D3.12 — i18n: locale detection middleware (AsyncLocalStorage per request) | ⬜ | — |
| D3.13 — i18n: localized error responses across all endpoints (RFC 7807) | ⬜ | — |
| D3.14 — i18n: translated AJV validation error messages (JSON Schema) | ⬜ | — |
| D3.15 — i18n: WebSocket `AUTHENTICATED` frame includes `locale` field | ⬜ | — |
| D3.16 — i18n: WebSocket system events localized (`SYSTEM_NOTIFICATION`, `CLOCK_SYNCED`) | ⬜ | — |

### Phase 4 — Messaging & Conversations

| Task | Status | Commit |
|------|:------:|--------|
| All tasks (D4.0–D4.16) | ⬜ BLOCKED (Phase 3 not complete) | — |

### Phase 5 — WebSocket Gateway

| Task | Status | Commit |
|------|:------:|--------|
| All tasks (D5.1–D5.13) | ⬜ BLOCKED (Phase 4 not complete) | — |

### Phase 6 — Attachments, Geolocation & Scheduling

| Task | Status | Commit |
|------|:------:|--------|
| All tasks (D6.1–D6.13) | ⬜ BLOCKED (Phase 5 not complete) | — |

### Phase 7 — System Management, Clock Sync & Resilience

| Task | Status | Commit |
|------|:------:|--------|
| All tasks (D7.1–D7.19) | ⬜ BLOCKED (Phase 6 not complete) | — |

### Phase 8 — Security Hardening & Legacy Compatibility

| Task | Status | Commit |
|------|:------:|--------|
| All tasks (D8.1–D8.10) | ⬜ BLOCKED (Phase 7 not complete) | — |

### Phase 9 — Testing, Validation & Deployment

| Task | Status | Commit |
|------|:------:|--------|
| All tasks (D9.1–D9.10) | ⬜ BLOCKED (Phase 8 not complete) | — |

---

## Next Task

> **D3.5** — `GET /radio/status` — real-time radio snapshot endpoint. Requires D3.4 (profiles table available). See `docs/architecture/api.md §4.2` for spec.

---

## Notes & Blockers

- Phase 2 complete: 14 tables, 14 repositories, migration 0002, all CHECK/UNIQUE/FK constraints, indexes.
- 80 unit tests across 7 repository test files (all pass).
- 340 total tests pass (124 unit + 120 integration + 96 other).
- D3.2 complete: SBitxCLIDriver with exponential backoff (1s→2s→4s→...→60s cap), SWR protection (>3.0 cuts TX), 10 consecutive failure permanent disconnect, 20 unit tests.
- `npm run build` — zero TypeScript errors.
- Database setup uses `drizzle-kit migrate` exclusively. No custom migration or seed scripts — schema declared in `src/db/schema/*.ts`, migrations (schema + seed) in `src/db/migrations/*.sql`. `scripts/migrate.ts` and `scripts/seed-test-user.ts` removed.
- Migration files: 0000 (users), 0001 (user_sessions + refresh_replaced_by), 0002 (phase 2 tables + statement-breakpoint), 0003 (seed admin user root/amazonia).
- `npm run db:migrate` applies all 4 migrations successfully (4 fresh DB cycles verified). `npm run db:generate` still fails on ESM/CJS resolution for schema files.
- Seed user migrated from custom script to `0003_seed_admin_user.sql` migration file with precomputed bcrypt hash.
- GitHub push failed (no credentials). PR must be created manually.
- Node.js target changed from 22 → 20.19 (Debian 13 Trixie): `.nvmrc`, `.node-version`, and `package.json` `engines` + `@types/node` updated.
- D1.13–D1.17 complete: i18n core module with 18 resource files (3 locales × 6 domains).
- Architectural review completed (12 findings, 10 addressed, 2 deferred).
- Phase 0.B is complete with all review fixes applied.
- Phase 1 is fully complete. All tasks D1.1–D1.17 ✅.
- Phase 3 has started on branch `feat/phase-3-hal-radio`.

---

## Session Log

| Date | Session | Tasks Completed |
|------|---------|----------------|
| 2026-07-30 | Session 1 | D0.B.1, D0.B.2, D0.B.3, Quality Gate |
| 2026-07-30 | Session 1b | Review fixes: prune deps, drop baseUrl, vite-tsconfig-paths, meaningful test |
| 2026-08-03 | Session 2 | D1.1-D1.7, D1.10, review fixes, dotenv/config fix |
| 2026-08-03 | Session 3 | D1.8 — refresh token rotation with reuse detection |
| 2026-08-03 | Session 4 | D1.9 — logout endpoint with session revocation (6 tests) |
| 2026-08-03 | Session 5 | D1.11 — auth middleware chain (18 tests) |
| 2026-08-03 | Session 6 | D1.12 — user endpoints (13 tests) |
| 2026-08-04 | Session 7 | D1.13–D1.17 — i18n module (18 resource files, 42 tests) |
| 2026-08-04 | Session 7b | Review fixes — pt prefix, TranslationKey type, D3.12 comment |
| 2026-08-04 | Session 8 | Phase 2: D2.1–D2.16 — all 14 tables, 14 repositories, migration, 80 unit tests |
| 2026-08-05 | Session 9 | D3.1 — IRadioDriver interface with typed events and status types |
| 2026-08-05 | Session 10 | D3.2 — SBitxCLIDriver with exponential backoff, SWR protection, 20 unit tests |
| 2026-08-05 | Session 11 | D3.3 — SimulatedRadioDriver (24 unit tests, 3 files, 581 lines) |
| 2026-08-05 | Session 12 | D3.4 — Radio profiles CRUD (5 REST endpoints, 24 integration tests) |

---

## Legend

| Mark | Meaning |
|:----:|---------|
| ⬜ | Not started |
| 🔄 | In progress |
| ✅ | Complete |
| ⚠️ | Blocked / needs attention |