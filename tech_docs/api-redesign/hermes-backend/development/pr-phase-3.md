# Pull Request — feat/phase-3-hal-radio → main

## Title

**feat(phase-3): HAL radio drivers + radio profiles CRUD (D3.1–D3.4)**

## Summary

Implements Phase 3 (HAL & Radio Integration) of the Hermes backend: the radio Hardware Abstraction Layer with two driver implementations, the first radio REST endpoints (profiles CRUD), and a standardization of the database migration workflow onto `drizzle-kit`.

## ✨ What's new

### Radio Hardware Abstraction Layer (`src/hal/`)

- **`IRadioDriver` interface** (`src/hal/driver.ts`) — extends `EventEmitter` with typed events (`telemetry`, `connected`, `disconnected`, `swr-protection`) and status types (`RadioStatus`, `TelemetrySnapshot`, `RadioMode`). All radio ops flow through `connect/disconnect/getStatus/setFrequency/setMode/setPower/pttOn/pttOff/getSwr`.
- **`SBitxCLIDriver`** (`src/hal/sbitx-cli-driver.ts`) — production driver wrapping `/usr/local/bin/sbitx` via `child_process.execFile` (arg arrays, no shell injection). Includes exponential backoff telemetry reconnection (1s → 2s → … → 60s cap), permanent disconnect after 10 consecutive failures, and SWR protection (cuts TX when SWR > 3.0).
- **`SimulatedRadioDriver`** (`src/hal/simulated-driver.ts`) — fake driver with plausible synthetic data, 1 Hz telemetry via `setInterval`, and a 5% SWR-spike probability to exercise SWR protection in tests.

### Radio Profiles CRUD (`src/api/v1/radio/`)

| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/v1/radio/profiles` | authenticated |
| POST | `/api/v1/radio/profiles` | admin, operator |
| GET | `/api/v1/radio/profiles/:id` | authenticated |
| PATCH | `/api/v1/radio/profiles/:id` | admin, operator |
| DELETE | `/api/v1/radio/profiles/:id` | admin, operator |

JSON Schema validation (`profiles.schema.ts`), duplicate `profileIndex` detection per station, auto-`updatedAt` on PATCH, and RBAC via `requireRole`.

## 🗄️ Database changes (`src/db/migrations/`)

Standardized on a pure `drizzle-kit migrate` workflow (removed `scripts/migrate.ts` and `scripts/seed-test-user.ts`):

- `0001` — fixed to `CREATE TABLE user_sessions` (adds `refresh_replaced_by`)
- `0002` — rewrote phase-2 tables with proper `--> statement-breakpoint` separators for better-sqlite3
- `0003` — new seed migration: `INSERT OR IGNORE` admin user (`root` / `amazonia`, precomputed bcrypt cost-12 hash)
- `_journal.json` updated to track all 4 migrations

## 🛠️ Config / tooling

- Target **Node.js 20.19** (Debian 13 Trixie) — updated `package.json` `engines` + `@types/node`, `.nvmrc`, `.node-version`
- `src/app.ts` — registered `profileRoutes`

## ✅ Testing

- **SBitxCLIDriver** — 20 unit tests (backoff, SWR protection, 10-failure disconnect)
- **SimulatedRadioDriver** — 24 unit tests (telemetry shape/rate, idempotent connect/disconnect, SWR protection)
- **Radio profiles** — 24 integration tests (401/403 auth checks, CRUD, validation, duplicate index, admin access)
- Full suite: **340 tests passing**, `npm run build` clean, ESLint clean

## 📝 Notes

- Next task: **D3.5 — `GET /radio/status`** (real-time snapshot endpoint)
- GitHub push failed (no credentials) — PR must be created manually.
