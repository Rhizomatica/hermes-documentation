# README redesign vs. hermes-backend docs — comparison and reconciliation

2026-10-07 · comparison for review

## Purpose

`README.md` (the redesign of the deployed hermes-api and its database) and the
`hermes-backend/` document set (a greenfield backend architecture) sit in the same
folder but were written independently, one day apart, by two authors, and neither
references the other. This document checks them against each other so that nobody
mistakes one for a description of the other.

**Verdict in one line:** they agree on *goals and principles* but diverge — and in
several places directly contradict — on *concrete decisions*. They are two branches
of the same decision tree, not two views of one plan.

## What the two documents are

| | `README.md` | `hermes-backend/` |
| --- | --- | --- |
| Author | Rafael Diniz | Matheus Thibau |
| Commit / date | "design for the UI ↔ backend API and the hermes-api database", 2026-10-06 | "add hermes-backend docs (NODEJS to Go)", 2026-10-07 |
| Nature | In-place redesign of the **deployed** hermes-api and DB | **Greenfield** service architecture |
| Target station | 1 GB Raspberry Pi | 4 GB Pi (sBitx v2) |
| Stack | Lumen 11 (PHP 8.2) + nginx + MariaDB | Node.js 20 + Fastify + SQLite, with a proposed Go rewrite (ADR-006) |
| Messaging model | inbox/outbox/drafts + per-recipient delivery | chat-native conversations |
| Scope of change | Refactor the running system | Build a new backend, then port |

## Where they agree

Both documents start from the same complaints about today's system and reach the
same set of principles.

| Theme | `README.md` | `hermes-backend/` |
| --- | --- | --- |
| Diagnosis of today's API | No auth, GETs with side effects, shell injection, inconsistent shapes, polling | Same findings (`audits/*`, security model) |
| One front door / one API surface for the UI | nginx → hermes-api + daemons | Fastify serves REST + WS in one process |
| Versioned WebSocket subprotocol with subscribe/publish, heartbeat, backpressure, role gating | `hermes.v1` | `hermes-v1` |
| Security fixed before features | Step 1 locks down `/api` | Security phase + audit |
| RBAC roles `admin` / `operator` / `user` | 3 roles | 4 (adds `readonly`); overlaps on the other 3 |
| Daemons off `0.0.0.0` (localhost only) | Yes | Assumed |
| Old `/api` frozen while clients migrate | v1 frozen until step 5 | Legacy `/api/v1` shim (ADR-003 / §10) |
| Store only token/session **hashes**, never plaintext | Yes | Yes (`user_sessions`) |
| Move off unsalted SHA-256 passwords | argon2id | bcrypt |
| Attachments modeled as rows (`storage_name`, size, mime, encryption) | Yes | Yes |
| Fewer process hops for RAM / reliability on a Pi | Explicit | ADR-006 consolidation |
| Consider **Go** as the future runtime | Open question | ADR-006 (Proposed) |
| `.hmp` / UUCP compatibility | First-class | Preserved via the sync engine (later removed) |

## Where they diverge

Rows marked ⚠️ are direct contradictions. Rows marked • are differences that are
compatible in principle but not interchangeable in implementation.

| Aspect | `README.md` | `hermes-backend/` | |
| --- | --- | --- | :--: |
| Database engine | MariaDB / InnoDB (kept; SQLite only an open question) | SQLite WAL (ADR-001, decided) | ⚠️ |
| Runtime / language | Stay PHP/Lumen, refactor only | Node.js → Go rewrite (ADR-006) | ⚠️ |
| Front-door topology | nginx + PHP-FPM + separate daemons (radiod, Mercury keep their own release cycles) | Single process; ADR-006 fuses backend + radio + Mercury | ⚠️ |
| REST version | `/api/v2` | `/api/v1` | ⚠️ |
| JSON casing | `snake_case` | `camelCase` | • |
| Error body | RFC 7807 `{type, title, status, detail, errors:{field:[]}}` | RFC 7807 `{type, title, status, code, message, details[], requestId}` | • |
| Identity / login | `username` = mailbox name (UUCP) | `callsign` = login id | ⚠️ |
| Messaging model | inbox/outbox/drafts; `messages` + `message_recipients` (row per recipient + `uucp_job_id`) | `conversations` + `participants` + `message_deliveries` + reactions + envelopes | ⚠️ |
| Radio command path | Straight to the radio daemon over WS (not REST) | REST → backend HAL → `sbitx` CLI (`execFile`) | ⚠️ |
| Modem state in the UI | First-class `/ws/modem` (link, SNR, bitrate, ARQ) | Not surfaced in the gateway at all | • |
| Auth mechanism | Session **cookie** + nginx `auth_request`; argon2id | **JWT RS256** access + refresh rotation; bcrypt | ⚠️ |
| Roles | 3 (`admin` / `operator` / `user`) | 4 (adds `readonly`) | • |
| Stations | `stations` table synced from `/etc/uucp/sys`; UUCP queue endpoint | No stations table (frequencies + `schedules.target_callsign`) | • |
| Settings | `settings` key/value table | Not modeled (env / config) | • |
| Table count | 10 | ~16 (+ time-series DBs) | • |
| WS frame shape | `{type, id, cmd/reply/event, seq, ts}` + **binary** audio/spectrum | `{type, timestamp, payload}` **JSON only** | • |
| WS heartbeat | 5 s | 30 s PING / 60 s timeout | • |
| WS error codes | strings (`bad_request`, `unknown_cmd`) | numeric `4001`–`4010` | • |
| WS auth | nginx `auth_request` → `X-Hermes-User` / `X-Hermes-Role` | `AUTHENTICATE` message with JWT, 10 s timeout | ⚠️ |
| Hardware target | 1 GB Raspberry Pi | 4 GB Pi (sBitx v2) | ⚠️ |
| UUCP / Postfix / Dovecot | First-class compatibility constraint | Barely addressed; the sync engine that carried it was removed | • |
| i18n | Not mentioned | Full `en` / `es` / `pt-BR`; locale in the JWT | • |
| Extra features | — | `user_devices` push (FCM/APNs), WebRTC signaling, app install/remove | • |

## The telling detail

Four of these conflicts are the README's **own open questions**, which the
hermes-backend docs have already settled — usually the opposite way:

| README open question | hermes-backend answer |
| --- | --- |
| "**Stay on PHP/Lumen?** … A rewrite (for example Go, one binary with built-in WebSockets)…" | ADR-006: **Go rewrite**. |
| "**MariaDB or SQLite?** … MariaDB is already installed everywhere…" | ADR-001: **SQLite**. |
| "Why direct sockets to each daemon, rather than relaying them through hermes-api? PHP-FPM cannot hold WebSockets." | ADR-006 **consolidates** everything into one process — i.e. the rewrite the README defers. |
| "**Which UI is the future?**" | The hermes-backend docs assume `hermes-gui` as the client. |

## Decisions to reconcile

Before either document can be called "the plan", these seven need a single answer.
Each is a hard fork, not a wording difference.

1. **Database engine** — MariaDB (README) vs SQLite (ADR-001).
2. **Runtime** — stay PHP/Lumen (README) vs Node→Go rewrite (ADR-006).
3. **Messaging model** — inbox/outbox + per-recipient rows (README) vs conversations (ADR-003).
4. **Radio command path** — daemon WebSocket (README) vs backend HAL wrapping the `sbitx` CLI.
5. **Auth** — session cookie + nginx `auth_request` (README) vs JWT RS256 + refresh rotation (ADR-004).
6. **HTTP/WS contract** — `/api/v2`, `snake_case`, string error codes, binary frames (README) vs `/api/v1`, `camelCase`, numeric codes, JSON-only (hermes-backend).
7. **Hardware assumption** — 1 GB Pi (README) vs 4 GB Pi (hermes-backend). The whole RAM budget of both designs depends on which is true.

## Decision register

The seven hard forks above are the headline. This register expands them — plus every
other open point the two documents raise — into one working table, so the team can
close decisions one at a time. Nothing here is settled yet: the `Decision` cell stays
`TBD` until it is agreed, then the row is closed.

Rows **D-00–D-29** are product and contract decisions (what the station does and how
it talks). Rows **D-30–D-48** are engineering and Go-port decisions (how it is built),
drawn from ADR-002…006 and the audits. Rows **D-49–D-82** are backend feature and
delivery decisions raised by the `hermes-backend/` docs alone — GPS, telemetry, chat
UX, security, CI/CD and the rest of the functional spec the port must reproduce; these
are being decided fresh rather than reconciled, because the README is silent on them.
Rows **R-01–R-07** are items the backend docs already assert as settled and that the
team should ratify or reverse. All four groups are up for team review.

Column meanings:

- **Decision to take** — the concrete question, with both candidate answers inline.
- **Decision** — the agreed answer. `TBD` until then.
- **Reason** — why the choice matters (the cost of guessing wrong).
- **Data** — where the evidence lives (source heading or ADR).
- **Members** — suggested owner(s) who drive the row to closed. *(Placeholders — replace with real names.)*
- **Status** — `Open` (default) · `In review` · `Decided`.
- **Blocks** — the work that cannot start until this is decided.

| ID | Decision to take | Decision | Reason | Data | Members | Status | Blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-00 | Plan of record: the README refactor, the hermes-backend design, or a merge of both? | TBD | Every row below hangs off this; without it the two docs keep drifting | This document; README §Summary; `hermes-backend/` | Maintainer + whole team | Open | Every row below |
| D-01 | Database engine: MariaDB (README) or SQLite (ADR-001)? | TBD | Sets migration, backup model, RAM budget and the query layer | README "Open questions"; `adr-001-sqlite-for-pi4.md` | Backend + Ops | Open | Schema, ORM, migrations, backups |
| D-02 | Runtime: keep PHP/Lumen (README) or rewrite in Node/Go (ADR-006)? | TBD | Decides whether this is a refactor or a rebuild, and the whole timeline | README "Open questions"; `adr-006-go-rewrite-and-station-consolidation.md` | Maintainer + Backend | Open | Every later row |
| D-03 | Topology: separate daemons behind nginx (README) or one consolidated process (ADR-006)? | TBD | Drives RAM, ops surface and whether nginx `auth_request` is needed at all | README "Why direct sockets…"; `adr-006` | Backend + Radio/HAL | Open | WS auth design (D-15), deployment |
| D-04 | Messaging model: inbox/outbox + per-recipient rows (README) or conversations (ADR-003)? | TBD | Defines message schema, UI shape and the UUCP/`.hmp` mapping | README schema; `adr-003-conversation-messaging-model.md` | Backend + UI | Open | Message schema and endpoints |
| D-05 | Radio command path: daemon WebSocket (README) or backend HAL wrapping the `sbitx` CLI? | TBD | Sets control latency, the single source of truth and the attack surface | README "One path per job"; `architecture/hardware-integration.md` | Radio/HAL + Backend | Open | Radio REST/WS endpoints |
| D-06 | Auth: session cookie + nginx `auth_request` (README) or JWT RS256 + refresh (ADR-004)? | TBD | Decides WS handshake, revocation and browser vs CLI/mobile support | README auth section; `adr-004-jwt-rs256-token-rotation.md` | Backend + Security | Open | WS auth (D-15), all protected routes |
| D-07 | Hardware target: 1 GB Pi (README) or 4 GB Pi sBitx v2 (hermes-backend)? | TBD | The RAM budget that every other choice above is measured against | README "1 GB Raspberry Pi"; `audits/sbitx-v2.md` | Maintainer + Ops | Open | D-01, D-02, D-03 |
| D-08 | REST version prefix: `/api/v2` (README) or `/api/v1` (hermes-backend)? | TBD | Client migration path and the freeze policy for the old routes | README conventions; `architecture/api.md` | Backend + UI | Open | Routing, UI migration |
| D-09 | JSON casing: `snake_case` (README) or `camelCase` (hermes-backend)? | TBD | One convention across REST and WS; client code generation | README conventions; `architecture/api.md` | Backend + UI | Open | DTOs, WS payloads, clients |
| D-10 | Error body: README `errors{field:[]}` map or `code`/`message`/`details`/`requestId`? | TBD | RFC 7807 needs one shape for every client to parse | README error format; `architecture/api.md` §errors | Backend + UI | Open | Shared error schema, clients |
| D-11 | Identity/login: `username` = mailbox name (README) or `callsign` (hermes-backend)? | TBD | Primary key choice, UUCP mapping and user migration | README schema; `architecture/users-and-permissions.md` | Backend | Open | Users table, auth (D-06) |
| D-12 | WS protocol: `hermes.v1` command/reply model (README) or `hermes-v1` typed events (hermes-backend)? | TBD | One wire contract for both daemons and the gateway | README WS section; `architecture/websocket.md` | Backend + Radio/HAL + UI | Open | WS clients, daemon protocol |
| D-13 | WS heartbeat: 5 s (README) or 30 s ping / 60 s timeout (hermes-backend)? | TBD | Battery/network cost vs how fast dead connections are dropped | README WS section; `architecture/websocket.md` | Backend + UI | Open | WS client tuning |
| D-14 | WS error codes: strings (README) or numeric `4001`–`4010` (hermes-backend)? | TBD | Client error handling; trivial once D-12 is settled | README WS section; `architecture/websocket.md` | Backend | Open | WS error handling |
| D-15 | WS auth: nginx `auth_request` headers (README) or in-band `AUTHENTICATE` JWT (hermes-backend)? | TBD | Depends on D-03 and D-06; changes the connection flow | README auth section; `architecture/websocket.md` | Backend + Ops | Open | WS connection flow, nginx config |
| D-16 | Binary frames: audio/spectrum over WS (README) or JSON only (hermes-backend)? | TBD | Enables browser audio and waterfall; costs bandwidth/testing | README binary frames; `architecture/websocket.md` | Radio/HAL + UI | Open | Spectrum/audio features (D-27) |
| D-17 | Modem state to UI: expose `/ws/modem` (README) or not (gap in hermes-backend)? | TBD | Whether the UI ever shows link, SNR, bitrate, ARQ | README current-state table; — | Backend + Radio/HAL | Open | Modem UI |
| D-18 | Roles: 3 `admin`/`operator`/`user` (README) or 4 with `readonly` (hermes-backend)? | TBD | RBAC matrix, route guards and UI gating | README auth section; `architecture/users-and-permissions.md` | Backend + Security | Open | Route guards, UI gating |
| D-19 | Stations model: `stations` table from `/etc/uucp/sys` (README) or none (hermes-backend)? | TBD | Scheduled connections and the UUCP queue UI | README schema; `architecture/api.md` schedules | Backend | Open | Schedules, queue endpoints |
| D-20 | Settings storage: `settings` key/value table (README) or env/config (hermes-backend)? | TBD | Whether settings stay runtime-editable from the UI | README schema; — | Backend + Ops | Open | Settings endpoints |
| D-21 | Password hashing: argon2id (README) or bcrypt (hermes-backend)? | TBD | Only one migration off the legacy unsalted SHA-256 | README auth section; `architecture/users-and-permissions.md` | Backend + Security | Open | Auth migration |
| D-22 | Extra features: push devices / WebRTC / app install in scope? | TBD | Scope, dependencies and extra RAM | `architecture/api.md` §4.13/4.14; `architecture/websocket.md` WebRTC | Product + Backend | Open | Schema, endpoints |
| D-23 | UUCP / Postfix / Dovecot compatibility: who owns it and how? | TBD | Un-upgraded stations must keep mailing over UUCP | README "must keep working"; — | Ops + Backend | Open | Migration step 2, transport layer |
| D-24 | i18n: build now (hermes-backend) or later (README silent)? | TBD | Touches every API message, error body and JWT claim | README (absent); `development/i18n.md` | UI + Backend | Open | Error messages, client locales |
| D-25 | Which UI is the future: `hermes-gui` or `hermes-frontend`? | TBD | Decides who ports first and how many times step 5 runs | README "Open questions" | Product + Maintainer | Open | Rollout step 5 |
| D-26 | Radio profiles ownership: radiod `user.ini` or the database? | TBD | Where profiles are read and written from | README "Open questions" | Radio/HAL + Backend | Open | `/radio/profiles` endpoint |
| D-27 | Does the UI need audio in the browser? | TBD | Whether WS audio must be built and tested over Wi-Fi | README "Open questions" | Product + UI | Open | Audio features (D-16) |
| D-28 | `nncp-transport` branch: merge into `main` or retire? | TBD | Must resolve before the database migration | README "Risks" | Maintainer | Open | Migration step 2 |
| D-29 | Roles for existing users at upgrade (everyone starts as `user`)? | TBD | Promotion policy for stations with known operators | README "Open questions" | Ops + Backend | Open | Migration step 2 |

### Engineering & Go-port decisions

These come from ADR-002…006 and the audit recommendations — the "how it is built"
half. Several are gated on the Go-migration spikes S1–S3.

| ID | Decision to take | Decision | Reason | Data | Members | Status | Blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-30 | Event bus: in-process `EventEmitter` (ADR-002) or Redis Pub/Sub? | TBD | Redis adds 80–300 MB and a daemon; only pays off if multi-process is coming | `adr-002-in-process-event-bus.md` | Backend | Open | WS gateway fan-out, ops |
| D-31 | Conflict resolution: last-writer-wins now (ADR-005) or CRDT/OT? | TBD | Defines concurrent edit/delete semantics; CRDT is deferred to Phase 10 federation | `adr-005-conflict-resolution-strategy.md`; `audits/comprehensive.md` H-4 | Backend | Open | Message edit/delete, sync |
| D-32 | Go port delivery model (R-2): ordering scope, drop policy, subscriber cap, panic semantics | TBD | ADR-002's synchronous, exception-isolating delivery is not a Go-channel property | `development/go-migration.md` §R-2 | Backend | Open | WS gateway, event bus |
| D-33 | Go port write-queue bound and overflow policy (R-1) | TBD | SQLite is single-writer; overflow policy decides dropped writes vs backpressure | `development/go-migration.md` §R-1 | Backend | Open | Radio/message writes |
| D-34 | TypeScript feature-freeze / cut-over point (where TS stops and Go starts) | TBD | Prevents two drifting implementations during the port | `adr-006` *Freeze/cut-over requirement*; `go-migration.md` | Maintainer + Backend | Open | Go waves 1–6 |
| D-35 | Repository/artifact boundary: stay in `hermes-backend` (Shape A) or new repo (Shape B)? | TBD | Where Debian/systemd and the GPL offer live; gated on Spikes S1/S2, decide before Wave 5 | `adr-006` open q5; `go-migration.md` §Repository topology | Maintainer | Open | Waves 5–6 packaging |
| D-36 | `radiod` fate: standalone systemd unit or absorbed into the consolidated backend? | TBD | Third-party consumers (Fyne GUI, CAT 4534, rigctld, loggers) must not break | `adr-006` open q7 | Radio/HAL + Backend | Open | Consolidation, packaging |
| D-37 | CPU isolation: `isolcpus` or cpuset v2 partitions? | TBD | Needed for the R1 audio-stability guarantee on the shipped kernel | `adr-006` open q3 | Radio/HAL + Ops | Open | ADR-006 exit criteria |
| D-38 | Transmitter-safety mechanism: watchdog + hardware deadman, PTT supervisor, or engine-side deadman? | TBD | Safety-critical; must pass the S3.8 abnormal-exit test | `adr-006` open q4 | Radio/HAL | Open | ADR-006 exit criteria |
| D-39 | C-dependency build: vendored, built in CI, or distro-provided? + aarch64 cgo pipeline + GPL §6 offer | TBD | Build reproducibility and the license obligation of the shipped binary | `adr-006` open q6 | Backend + Ops + Legal | Open | CI, release |
| D-40 | Upstream buy-in to extract `libradio_daemon_core.a` and accept RT-thread self-pinning | TBD | Gating spike S2; the fallback changes the whole artifact back to a WS client | `adr-006` open q2; `go-migration.md` S2 | Maintainer + Radio/HAL | Open | D-03, D-35 |
| D-41 | Record the RAM/thermal baseline (S0.6) and set the consolidated-process budget | TBD | Without a recorded baseline, ADR-006 exit criterion 4 cannot be measured | `adr-006` open q8; `audits/sbitx-v2.md` CR-1 | Ops + Maintainer | Open | ADR-006 exit criteria |
| D-42 | Adopt "remove the sync engine entirely" — and how is UUCP/`.hmp` then carried? | TBD | The removed sync engine was the UUCP/HMP bridge, so this reopens the D-23 gap | `audits/sync-protocol.md` | Backend + Ops | Open | Schema (drop sync tables), UUCP story |
| D-43 | Database adapter: commit to SQLite-only now, Postgres deferred to Phase 10? | TBD | Future-proofing vs YAGNI; shapes every repository interface | `audits/plan-review.md` D2.12 / H-2; `development/plan.md` | Backend | Open | Repository layer |
| D-44 | Telemetry time-series storage: separate DB with daily sharding on SD, or tmpfs RAM disk with checkpointing? | TBD | SD wear vs the durability of non-critical telemetry | `audits/sbitx-v2.md` §MR; `audits/comprehensive.md` | Ops + Backend | Open | Telemetry schema, backups |
| D-45 | Retention policies: telemetry 90 d, GPS 365 d, audit 2 y, deleted messages 90 d; batch-delete strategy | TBD | SD space, privacy and write stalls (audit M-7 / MR-4) | `database.md` §8; `operations/security.md`; `audits/*` | Ops + Backend | Open | Cleanup jobs |
| D-46 | Legacy inbox/outbox shim scope: which legacy email endpoints stay read-only? | TBD | Lets existing UIs migrate without breaking | `audits/comprehensive.md` (legacy shim); `adr-003` | Backend + UI | Open | Legacy `/api/v1` shim |
| D-47 | Observability on the Pi: enable Prometheus/metrics or keep disabled by default? | TBD | Metrics cost RAM; ops needs visibility | `operations/observability.md` | Ops | Open | Monitoring, alerting |
| D-48 | Packaging target: confirm Debian/Trixie via `hermes-net` units as the base image | TBD | Where systemd units, the release and updates land | `operations/deployment.md`; `development/setup.md` | Ops | Open | Release, packaging |

### Backend feature decisions (functional scope)

Raised by `architecture/*`, `hardware-integration.md`, `users-and-permissions.md` and
`operations/*` — the behaviour the port must reproduce. The README is silent on most of
these, so the team is deciding them for the first time rather than reconciling two texts.

| ID | Decision to take | Decision | Reason | Data | Members | Status | Blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-49 | GPS/geolocation feature: in scope (`POST /geolocation`, `GET /geolocation/current` and `/history`)? | TBD | GPS feeds clock sync, station location and any map view; the README never mentions GPS | `architecture/api.md` §4.11; `architecture/database.md` §4.7 | Product + Backend | Open | GPS schema, clock sync |
| D-50 | GPS storage: separate `gps.db` daily-sharded file with 365-day retention, or main DB / tmpfs? | TBD | SD-wear vs durability of location history; overlaps D-44/D-45 | `architecture/database.md` §4.7, §8; `adr-001` | Ops + Backend | Open | GPS schema, retention |
| D-51 | Clock source order GPS (NMEA, 30 s) → manual → saved timestamp, and is `created_at` ever mutated? | TBD | Air-gapped stations need a fallback; retroactive stamps broke idempotency (C-1) | `architecture/database.md` §13; `audits/comprehensive.md` C-1 | Backend + Ops | Open | Ordering, idempotency |
| D-52 | GPS privacy: never log coordinates, and restrict who may read `/geolocation`? | TBD | Precise location is sensitive in humanitarian deployments | `operations/observability.md` (never-log list); `users-and-permissions.md` | Security + Backend | Open | Logging, RBAC |
| D-53 | Telemetry scope: which signals are recorded and pushed (freq, mode, power, SWR, temp, voltage, current @ 1 Hz)? | TBD | Sets the time-series write load (H-9) and the UI panel | `architecture/hardware-integration.md`; `architecture/websocket.md` | Radio/HAL + Backend | Open | Telemetry schema, WS |
| D-54 | Telemetry stream death: add auto-reconnect in the HAL driver (M-8)? | TBD | Silent telemetry death leaves the UI stale with no alert | `audits/comprehensive.md` M-8; `development/plan.md` D3.2 | Radio/HAL | Open | HAL driver |
| D-55 | SWR protection: cut TX at SWR > 3.0 with manual reset, and log frequency/power context (M-9)? | TBD | TX safety is critical; the cut currently loses the context needed to diagnose it | `architecture/hardware-integration.md`; `audits/comprehensive.md` M-9 | Radio/HAL | Open | HAL, `/radio/protection/reset` |
| D-56 | WS gateway isolation: separate worker thread / circuit breaker, or leave it in the Fastify process (M-2)? | TBD | A single bad connection handler today takes down REST as well | `audits/comprehensive.md` M-2 | Backend | Open | WS gateway |
| D-57 | WS backpressure: drop telemetry/typing but never state-changing events (code `4010`) (H-5)? | TBD | Silent drops lose messages | `architecture/websocket.md`; `audits/comprehensive.md` H-5 | Backend | Open | WS gateway |
| D-58 | WS limits: keep 20 concurrent / 50 topics / typing 1-per-2 s, or raise them (H-6)? | TBD | 20 may be too low once telemetry and typing share the socket | `architecture/websocket.md`; `audits/comprehensive.md` H-6 | Backend | Open | WS gateway, UI |
| D-59 | Mid-session token invalidation: add a `token_version` claim and `AUTH_REQUIRED` code (M-1)? | TBD | Password/locale changes vs already-open WebSocket sessions | `audits/comprehensive.md` M-1; `adr-004` | Security + Backend | Open | JWT, WS |
| D-60 | Presence & typing indicators in scope (`PRESENCE_UPDATE`, `TYPING_*` events)? | TBD | Chat UX vs extra WS traffic and rate limits | `architecture/websocket.md`; `development/plan.md` D5.7–D5.8 | Product + Backend | Open | WS, UI |
| D-61 | Reactions: union semantics, max 20 emoji per message? | TBD | Conflict rule (ADR-005) and storage growth | `adr-005`; `architecture/api.md` §4.4 | Product + Backend | Open | Message schema |
| D-62 | Message limits: 64 KB content, 256 subject, 50/page, max 20 reactions per message — accept? | TBD | Pi 4 memory guardrails; enforced in the validator | `architecture/api.md` §4.4; `architecture/database.md` | Backend | Open | Validation |
| D-63 | Attachments: 50 MB cap, content-sniffed MIME, SHA-256 dedup, 1 h signed URL + 30-day HF token (LR-2)? | TBD | Store-and-forward timing vs signed-URL security | `architecture/api.md` §4.8; `audits/sbitx-v2.md` LR-2 | Backend + Security | Open | Attachments |
| D-64 | Setup wizard scope & fields (callsign, location, radioProfile, installedApps, network, locale)? | TBD | First-boot contract for the UI | `architecture/api.md` §4.13; `operations/deployment.md` | Product + Backend | Open | Setup flow |
| D-65 | App management: keep `/apps` install/remove/update (hermes-chat, hermes-gps)? | TBD | Plugin model vs a fixed firmware image | `architecture/api.md` §4.14 | Product + Ops | Open | Apps endpoint |
| D-66 | System control surface: expose reboot / shutdown / erase-sdcard over the API? | TBD | High-blast-radius endpoints need explicit guardrails | `architecture/api.md` §4.12 | Product + Security | Open | System endpoints |
| D-67 | Frequency presets model: alias / frequency / mode / `isGateway` / region? | TBD | Preset sharing and gateway/region metadata | `architecture/api.md` §4.9 | Product + Backend | Open | Frequencies |
| D-68 | Connection schedules: recurrence model and missed-schedule policy (skip, do not replay)? | TBD | Boot-time catch-up semantics | `architecture/api.md` §4.10; `operations/deployment.md` | Backend | Open | Scheduler |
| D-69 | Rate limiting: in-memory counters that reset on restart, with per-endpoint thresholds — accept (LR-3)? | TBD | Counters reset on the exact restarts field power causes | `architecture/users-and-permissions.md` §9; `audits/sbitx-v2.md` LR-3 | Backend | Open | Auth, endpoints |
| D-70 | Password policy: enforce complexity beyond "≥ 8 chars" (M-4)? | TBD | Weak passwords on field LANs | `audits/comprehensive.md` M-4; `operations/security.md` | Security | Open | Auth |
| D-71 | Transport security: TLS 1.2+, self-signed for LAN, HSTS, and cert pinning / TOFU (M-5)? | TBD | LAN threat model and mobile clients | `operations/security.md`; `audits/comprehensive.md` M-5 | Security + Ops | Open | Deployment |
| D-72 | Audit-log coverage: pin the exact event list (auth, role, radio command, config changes)? | TBD | Forensics and compliance; drives the schema | `operations/security.md`; `architecture/users-and-permissions.md` §8 | Security + Backend | Open | Audit schema |
| D-73 | i18n implementation: JSON bundles, locale in JWT, no runtime lib, English radio terms, content untranslated? | TBD | Complements D-24 (build i18n now); fixes the mechanism | `development/i18n.md`; `architecture/api.md` §1 | UI + Backend | Open | Translations |

### Backend platform & delivery decisions

| ID | Decision to take | Decision | Reason | Data | Members | Status | Blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-74 | Job-queue durability: mandatory SQLite write before the HTTP ack, and rehydrate `queued` jobs on boot (C-2)? | TBD | The "best-effort" queue defeated its own purpose | `audits/comprehensive.md` C-2; `architecture/database.md` §4.8 | Backend | Open | Messaging, radio jobs |
| D-75 | Systemd resilience: `StartLimitIntervalSec`/`StartLimitBurst` + `ExecStartPre` integrity check (C-3)? | TBD | Restart loops destroy the SD card | `audits/comprehensive.md` C-3; `operations/deployment.md` | Ops | Open | Deployment |
| D-76 | Data-integrity checks: `content_checksum` on messages + weekly attachment re-hash + `/health/deep` check (H-1)? | TBD | Silent corruption on SD cards | `audits/comprehensive.md` H-1; `development/plan.md` D2.3a/D6.13 | Backend | Open | Schema, health |
| D-77 | Health/alert surface: add `/health/stats` and a `/system/alerts` ring buffer, since WARN logs are invisible (H-7/H-8)? | TBD | Air-gapped ops has no log reader | `audits/comprehensive.md` H-7/H-8; `development/plan.md` D7.18 | Ops + Backend | Open | Observability |
| D-78 | Testing strategy: testing trophy, ≥ 80% line coverage, and Pi 4 latency targets (conv list < 50 ms, telemetry query < 100 ms)? | TBD | Defines the port's merge gate | `development/testing.md`; `development/ci-cd.md` | Backend | Open | CI |
| D-79 | CI/CD: GitHub Actions lint/test/build everywhere + tag→SSH deploy to the Pi; Docker only for CI? | TBD | Release mechanics for a node-less host | `development/ci-cd.md` | Ops + Backend | Open | Release |
| D-80 | Git workflow: phase branches, single-squash PRs, Conventional Commits? | TBD | History, review and audit traceability | `development/git-workflow.md` | Maintainer + team | Open | Repo process |
| D-81 | Deployment baseline: systemd unit + `MemoryMax`, SD-wear tuning, `.backup` restore, git-pull upgrade? | TBD | The operational contract for the field | `operations/deployment.md` | Ops | Open | Deployment |
| D-82 | Roadmap: adopt/sequence multi-process scaling, CQRS, plugin arch, multi-radio, multi-tenant, federation, GraphQL, API versioning, Delta Chat, LAN audio? | TBD | Keeps deferred scope visible instead of rediscovered | `architecture/api.md` §13 | Product + Backend | Open | Roadmap |

### Ratify — asserted as decided in the backend docs

The backend docs state these as settled, but were written without the README in hand.
Confirm or reverse each before they are treated as binding.

| ID | Decision to take | Decision | Reason | Data | Members | Status | Blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Messaging model = hybrid (chat UX + store-and-forward, `message_envelopes`)? | TBD | Overlaps D-04; must be confirmed before the schema is frozen | `architecture/api.md` §12 | Product + Backend | Open | D-04, message schema |
| R-02 | Conversations owned by the user within a station context? | TBD | Multi-user station model | `architecture/api.md` §12 | Product + Backend | Open | Schema, RBAC |
| R-03 | Local-only chat allowed (delivery `channel=websocket`), mixed local+radio per message? | TBD | Whether same-station users bypass HF | `architecture/api.md` §12 | Product + Backend | Open | Deliveries |
| R-04 | Radio config source of truth = daemon runtime state + DB desired config reconciled on boot? | TBD | Overlaps D-05/D-26 | `architecture/api.md` §12 | Radio/HAL + Backend | Open | Radio state |
| R-05 | Broadcast = one-to-many, no replies, ≤ 200 recipients? | TBD | Overlaps D-04 | `architecture/api.md` §12 | Product | Open | Conversations |
| R-06 | ADR-005 conflict rules: deletion wins over edits, reactions union, reject writes to deleted conversations? | TBD | Pins concurrent-edit/delete semantics | `adr-005`; `development/plan.md` D4.9–D4.10 | Backend | Open | Message edit/delete |
| R-07 | ADR-004 real JWT claims are `sub`/`callsign`/`role`/`locale` (the doc's `permissions`/`station` example was wrong)? | TBD | A port written to the old section produces tokens the UI cannot read | `adr-004` (Sept-2026 correction); `development/go-migration.md` §R-6.1 | Backend | Open | Auth, WS |

## Recommendation

- Treat the **README as authoritative for the real deployed station.** It is
  field-grounded: real routes (`iwatch`, `caller.sh`, `mailkill.sh`), real files
  (`/etc/uucp/sys`, `.hmp`), the actual 6 legacy tables, the 1 GB constraint, and
  Lumen 11. It is the upstream maintainer's design.
- Treat **`hermes-backend/` as a source of ideas to graft onto the README**, not as
  a description of the same system. Its best material — i18n, the audit taxonomy,
  JSON-Schema validation, the CI/CD and testing plans, ADR discipline — is
  independent of the engine/runtime/messaging conflicts and can be adopted either way.
- **Do not** mix the two contracts. A UI cannot speak `hermes.v1` *and* `hermes-v1`,
  send `camelCase` *and* `snake_case`, or post to `/api/v1` *and* `/api/v2` at once.
  Pick one axis at a time from the list above.

## Sources

- `README.md` — redesign of the UI ↔ backend API and the hermes-api database.
- `hermes-backend/architecture/{api,database,websocket,users-and-permissions,hardware-integration,erd}.md`
- `hermes-backend/adr/adr-00{1..6}-*.md`
- `hermes-backend/development/{plan,go-migration,i18n,testing,setup,ci-cd,git-workflow}.md`
- `hermes-backend/audits/*.md`, `hermes-backend/operations/*.md`

