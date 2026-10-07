# Hermes Backend — Go Migration Task List

Companion to [ADR-006](../adr/adr-006-go-rewrite-and-station-consolidation.md). This document turns the ADR's decision into an executable task list: the **gating spikes** that must pass before any domain code is ported, followed by **six porting waves**.

**Behavioral specification**: [`plan.md`](plan.md) (Phases 0–9) plus the architecture docs (`api.md`, `websocket.md`, `database.md`, `users-and-permissions.md`) remain authoritative. The Go port must satisfy them; this document only describes *how* and *in what order*.

**Golden rule**: the web UI (`hermes-gui`) must not require changes. HTTP, WebSocket, and error/response shapes are frozen.

**Ambiguity rule — split by surface, because the reference implementation is incomplete.** For surface that is *implemented*, today's Node behavior wins. For surface that is *specified but not built* — which is most of Phases 4–9, and all of Mercury integration — there is **no Node behavior to defer to**, and the architecture docs (`api.md`, `websocket.md`, `database.md`, `users-and-permissions.md`) are authoritative. Each wave below states which of the two it is. The Contract Freeze Checklist is split the same way.

---

## Part 1 — Gating Spikes

Spikes are throwaway probes, not production code. **No domain porting begins until S1–S3 pass on real sBitx v2 hardware.**

### S0 — Toolchain and CI groundwork

| Task | Deliverable | Acceptance criteria | Depends on |
|------|-------------|---------------------|:---:|
| S0.1 | `go.mod` + repo layout (`cmd/hermes`, `internal/…`, `cgo/…`) | `go build ./...` succeeds on the Pi 4 | — |
| S0.2 | cgo build target in `Makefile` (`CGO_ENABLED=1`, `CGO_CFLAGS`/`CGO_LDFLAGS` for Mercury + radiod, arch flags) | `make build` produces a binary that links both `.a` files | S0.1 |
| S0.3 | `aarch64` build path (on-device or `debootstrap` chroot with `-dev` packages) | Reproducible build documented in `docs/development/setup.md` | S0.2 |
| S0.4 | CI job producing an `aarch64` artifact | Artifact runs `--version` on the target | S0.3 |
| S0.5 | **Seam tiering — stub build.** `-tags stub` with stub `.a` files (or `//go:build stub` C shims) | `go build -tags stub ./...` and `go test -tags stub ./...` pass in CI **without** the real engines, so the ~90% of the code that is not cgo can be developed and tested on any machine; the real link is exercised only in the `aarch64` job | S0.1 |
| S0.6 | **Baseline RAM/thermal capture on the target** (ADR-006 §1) | Documented RSS breakdown of the *current* three-process layout, measured before any Go code exists — otherwise exit criterion 4 has nothing to compare against | — |

**Exit**: a Go binary with dummy cgo calls to both engines builds and runs on the Pi 4, **and** the same code builds *and tests* with the engines absent.

### S1 — Spike A: Mercury link

| Task | Deliverable | Acceptance criteria | Depends on |
|------|-------------|---------------------|:---:|
| S1.1 | Reuse Mercury's `mercury_bridge` cgo pattern from its Fyne GUI | Go calls `mercury_start()`; engine thread starts | S0.2 |
| S1.2 | Send/arq path exercised from Go | A test message round-trips through the modem (loopback or on-air) | S1.1 |
| S1.3 | Event handoff without C→Go callbacks | Mercury state reaches Go via poll/ring, not a Go callback on the engine thread | S1.2 |
| S1.4 | Core pinning option (`-c <cpu>` equivalent) wired from Go config | Mercury DSP thread confined to core 1 | S1.1 |

**Exit**: Go drives Mercury in-process; no TCP TNC client anywhere in the probe.

### S2 — Spike B: radio-daemon core extraction and link

| Task | Deliverable | Acceptance criteria | Depends on |
|------|-------------|---------------------|:---:|
| S2.1 | Upstream refactor: extract `libradio_daemon_core.a` from `radio_daemon.c` | Upstream `radio_daemon` executable still builds and passes `make test` | Coordination with radiod maintainer |
| S2.2 | Proposed core API (`radio_core_init`, `set_frequency`, `set_mode`, `set_power`, `ptt`, `get_state`, `event_fd`) | Each call works from a C harness | S2.1 |
| S2.3 | Go cgo wrapper over the core API | Go sets frequency/mode/PTT on real hardware; state reads back | S2.2 |
| S2.4 | Event pipe drained by a Go goroutine | Radio events reach the Go event bus with no engine-thread Go callback | S2.3 |
| S2.5 | Decide `radiod` fate (standalone unit vs. absorbed) | Documented in ADR-006 open questions + `docs/architecture/hardware-integration.md` | S2.1 |
| S2.6 | **RT-thread self-pinning (R1)** — `pthread_setaffinity_np` called by each engine RT thread | Threads remain on cores 0–1 **under load**, verified by sampling `ps -eLo tid,psr` during S3.5 rather than at idle. **This is new upstream C code and is *not* included in the `libradio_daemon_core.a` extraction** (ADR-006 → *R1 and R2 in practice*) | S2.1 |

**Exit**: Go controls the radio in-process on real hardware; the WebSocket client to radiod is unused; **and R1 holds because the engine pins itself — not because the system was idle when it was checked.**

### S3 — Spike C: real-time isolation validation

The DSP/audio path must be provably independent of HTTP/WS load. Validation is of the **isolation configuration**, not of traffic volume.

| Task | Deliverable | Acceptance criteria | Depends on |
|------|-------------|---------------------|:---:|
| S3.1 | Core map enforced (R1) | `isolcpus=0,1` on the kernel command line; audio→core 0, modem→core 1 **via the S2.6 self-pinning**. `GOMAXPROCS=2` bounds Go's parallelism but is *not* the placement mechanism. Verified **under load**, not at idle. If `isolcpus` is unavailable on the target kernel, the cpuset v2 equivalent is documented explicitly rather than improvised | S1.4, S2.6 |
| S3.2 | RT scheduling + buffer locking (R2) | Audio/DSP threads report `SCHED_FIFO`; **RT buffers are `mlock`ed** with `RLIMIT_MEMLOCK`/`CAP_IPC_LOCK` raised in the unit; zero allocations on the audio path. Process-wide `mlockall` is explicitly **rejected** — it locks the Go heap and fights the Go runtime | S3.1 |
| S3.3 | Thread ownership audit (R3) | `ps -eLo tid,comm,psr,cls` shows engine pthreads, not Go threads, on cores 0–1 | S3.1 |
| S3.4 | Lock-free handoff audit (R4, R5) | No engine→Go calls; no shared mutex on the RT path; commands go through a queue | S2.4 |
| S3.5 | Load test: HTTP/WS flood vs. audio | Zero dropouts with N concurrent WS clients + SQLite writes; capture `xrun`/underrun counters | S3.1–S3.4 |
| S3.6 | Failure-mode test: restart | `SIGTERM` → systemd restarts the unit → `radio.connected` recovers correctly | S3.5 |
| S3.7 | RAM/thermal measurement | Documented RSS + temperature **against the S0.6 baseline**, not against an estimate | S3.5 |
| S3.8 | **Transmitter safety — abnormal exit (ADR-006 → *Transmitter safety*)** | With PTT keyed, kill the process with `SIGKILL`, and separately fault-inject `SIGSEGV`. The transmitter **must drop the key** within a documented bound, via a mechanism that does not depend on the dying process. The chosen mechanism (systemd watchdog + hardware deadman / separate PTT supervisor / engine-side deadman) and its bound are recorded | S3.6 |

**Exit**: S3.5 shows no audio degradation under load with R1–R6 enforced. If it fails, the leak is in the isolation config (per ADR-006) and must be fixed here — not by abandoning the consolidation. **S3.8 is not optional and cannot be satisfied by `ExecStopPost`**, which does not run for `SIGKILL`, `SIGSEGV`, or an OOM kill.

---

## Part 2 — Porting Waves

Waves 1–6 bring the Go implementation to parity. Each wave keeps the API/WS contract frozen and lands with tests (`go test`).

**Waves 1–2 are translations; Waves 3–6 are builds.** The reference implementation is incomplete: Phases 0–2 are complete, Phase 3 is partial (D3.1–D3.4 ✅), and **Phases 4–9 are not started** — there is no Node code for the WS gateway, telemetry, retention, or packaging to translate. Those waves are therefore **built to the architecture docs**, consulting the Node implementation only where it exists. "Mirror the current Vitest coverage" applies to Waves 1–2; for the rest the test suite is derived from the spec (`api.md`, `websocket.md`, `database.md`), not from `tests/` (28 files, ~340 `it()` cases today).

### Wave 1 — Foundation

| Task | Deliverable | Acceptance criteria | Ref | Depends on |
|------|-------------|---------------------|:---:|:---:|
| G1.1 | Config loader | Same env vars as `src/shared/config.ts` (`DATABASE_PATH`, `PORT`, `HOST`, `CORS_ORIGINS`, `LOG_LEVEL`, `RADIO_DRIVER`, `DB_ADAPTER`, `JWT_*`, `APP_VERSION`) | `setup.md` | S0.4 |
| G1.2 | `slog` JSON logging | Field parity with the Pino output in `observability.md` (`msg`, `level`, `time`, …) | `observability.md` | G1.1 |
| G1.3 | SQLite open + pragmas ([ADR-001](../adr/adr-001-sqlite-for-pi4.md)) | Apply the **4 pragmas the adapter actually applies** (`journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `synchronous=NORMAL` — `src/db/sqlite.adapter.ts`), because parity is with the implementation. ADR-001 documents **3 further pragmas** (`cache_size=-64000`, `temp_store=MEMORY`, `mmap_size=268435456`) that are **documented but never applied** — decide explicitly (apply them, or amend ADR-001) instead of inheriting the discrepancy. `PRAGMA integrity_check` is a check, not a setting, and is not counted. WAL confirmed | ADR-001 | G1.1 |
| G1.4 | Migration runner over existing `.sql` files | The 4 existing migrations apply to a fresh DB identically to Drizzle's journal | `database.md` | G1.3 |
| G1.5 | Repository layer for all **16** tables | Query parity with the 16 TS repositories (`src/db/repositories/`); `content_checksum` semantics preserved. The daily-sharded `radio_telemetry_*` / `gps_*` tables are **not** migration-managed and are excluded from this count (Wave 5) | `database.md` | G1.4 |
| G1.6 | Typed in-process event bus ([ADR-002](../adr/adr-002-in-process-event-bus.md)) | Same event names as the TS typed map; subscriber isolation | ADR-002 | G1.1 |
| G1.7 | HTTP skeleton + `/health` | `GET /health` response byte-identical to current spec | `api.md §health` | G1.1 |

**Exit**: server boots, migrates, serves `/health`; repo tests pass against `:memory:`.

### Wave 2 — Auth

| Task | Deliverable | Acceptance criteria | Ref | Depends on |
|------|-------------|---------------------|:---:|:---:|
| G2.1 | bcrypt password verify/hash | Cost ≥ 12; rejects on mismatch | ADR-004 | G1.5 |
| G2.2 | RS256 signing + verification | Access claims **exactly** `sub, callsign, role, locale, iss, iat, exp`; refresh claims `sub, type, jti, iss, iat, exp` (`src/auth/token.ts`). There is **no `sessionId`, `permissions`, or `station` claim** — ADR-004 documents all three and is wrong (§R-6). `locale` **is** present and is load-bearing (§R-6.1) | ADR-004, §R-6 | G2.1 |
| G2.3 | `POST /auth/login` | 200 `{accessToken, refreshToken, expiresIn: 900}`; 401 invalid; audit log on success; refresh stored as SHA-256 hash. **429 comes from the global limiter only**: `max: 300` per 1 minute, `global: true`, keyed on `X-Forwarded-For ?? request.ip`, body `{error: 'auth.rate_limited', code: 'RATE_LIMITED'}` (`src/app.ts`). There is **no per-IP login-failure limiter**; and the `X-Forwarded-For` key is **spoofable** unless a trusted proxy strips the header (§R-6.2) | ADR-004, `api.md §4.1`, §R-6.2 | G2.2 |
| G2.4 | `POST /auth/refresh` | Rotation + reuse detection: reuse revokes all sessions and logs `auth.token_reuse_detected`; expired → 401 | ADR-004 | G2.3 |
| G2.5 | `POST /auth/logout` | Session revoked; refresh token invalidated | ADR-004 | G2.3 |
| G2.6 | JWT middleware + RBAC guard | Role checks (`admin`/`operator`/`viewer`) match `users-and-permissions.md` | `users-and-permissions.md` | G2.2 |

**Exit**: the full auth lifecycle passes integration tests mirrored from `tests/integration/auth/`.

### Wave 3 — Domain (messaging)

| Task | Deliverable | Acceptance criteria | Ref | Depends on |
|------|-------------|---------------------|:---:|:---:|
| G3.1 | Users: `GET /users`, `GET /users/me`, `POST /users` | Validation + RBAC parity; error codes per `api.md §4` | `api.md §4.2` | G2.6 |
| G3.2 | Conversations CRUD + participants | Create/list/get/archive/unarchive; participant checks (`403 NOT_PARTICIPANT`) | ADR-003 | G3.1 |
| G3.3 | Messages: create/list/edit/delete | Idempotent create via `client_message_id`; edit/delete per ADR-005 (`409 MESSAGE_DELETED`) | ADR-003, ADR-005 | G3.2 |
| G3.4 | Delivery tracking | `message_deliveries` transitions match `api.md` | ADR-003 | G3.3 |
| G3.5 | Reactions add/remove | Union semantics; duplicate is idempotent (200 + existing object) | ADR-005 | G3.3 |
| G3.6 | Attachments + integrity | `content_checksum` verification (AUDIT H-1) | `database.md` | G3.3 |
| G3.7 | Audit log writes | Same event names/locales as the TS implementation | `observability.md` | G1.5 |
| G3.8 | Conversation list query benchmark | < 50 ms on Pi 4 (AUDIT M-6) | `plan.md` D4.15 | G3.2 |

**Exit**: full messaging lifecycle works; conflict-resolution scenarios from ADR-005 pass.

### Wave 4 — WebSocket gateway

| Task | Deliverable | Acceptance criteria | Ref | Depends on |
|------|-------------|---------------------|:---:|:---:|
| G4.1 | `hermes-v1` subprotocol handshake | 10-second auth timeout → close `4001` | `websocket.md` | G2.6 |
| G4.2 | `AUTHENTICATE` → `AUTHENTICATED` and `SUBSCRIBE` → `SUBSCRIBED` flows | `AUTHENTICATED` payload exactly `{ userId, callsign, role, locale, serverTime, connectionId }`; `SUBSCRIBED` payload `{ topics }` (`websocket.md`). **`websocket.md` defines no `sessionId` field here** — an earlier revision of this task listed one; it is the same phantom field as the JWT claim-set defect (§R-6.1) | `websocket.md` | G4.1 |
| G4.3 | Topic routing from the event bus | Same topic grammar (`conversation:*`, `radio:telemetry`) | ADR-002, `websocket.md` | G4.2 |
| G4.4 | Event payload parity | `MESSAGE_NEW`/`MESSAGE_EDITED`/`MESSAGE_DELETED`/reactions/typing/presence shapes unchanged | `websocket.md` | G4.3 |
| G4.5 | Backpressure + connection limits | Slow-consumer handling and max-connection cap (AUDIT H-5, H-6) | `plan.md` D5.10/D5.11 | G4.3 |

**Mode: build.** There is no Node WS gateway to translate (Phase 5 is not started) — this wave is written to `websocket.md`.

**Exit**: a web-UI client built against the documented gateway works unmodified.

### Wave 5 — Radio and telemetry (linked engines)

| Task | Deliverable | Acceptance criteria | Ref | Depends on |
|------|-------------|---------------------|:---:|:---:|
| G5.1 | Go `Driver` interface (port of `IRadioDriver`) | `connect`/`disconnect`/`isConnected`/`getStatus`/`setFrequency`/`setMode`/`setPower`/`pttOn`/`pttOff`/`getSwr` + typed events | `hardware-integration.md` | S3.5 |
| G5.2 | `SimulatedDriver` | Dev/test parity with `SimulatedRadioDriver` (plausible 1 Hz telemetry, no hardware) | `hardware-integration.md` | G5.1 |
| G5.3 | `LinkedRadioDriver` over `libradio_daemon_core.a` | Real status/frequency/mode/power/PTT on hardware | S2.3, G5.1 | S2.3 |
| G5.4 | Telemetry at 1 Hz | Snapshots match `TelemetrySnapshot` fields exactly; recorded to telemetry tables | `hardware-integration.md` | G5.3 |
| G5.5 | SWR protection | SWR > 3.0 while TX → immediate `pttOff`, `swr-protection` event, `swrProtection: true` in `GET /radio/status`, manual reset endpoint | `hardware-integration.md` | G5.4 |
| G5.6 | `GET /radio/status` + profiles endpoints | `radio.connected: false` degraded contract preserved (new cause: engine init failure) | `api.md §Radio` | G5.3 |
| G5.7 | `MercuryDriver`/messaging transport | Outbound messages handed to Mercury in-process; delivery/ack events flow back via the ring | S1.3 | S1.3, G3.4 |
| G5.8 | Startup reconciliation | Persisted `radio_profiles` applied to the engine at boot | `api.md §Radio` | G5.6 |
| G5.9 | **Time-series storage: `telemetry.db` + daily shards** | Separate database file; `radio_telemetry_YYYYMMDD` created at startup; application-level sharding — **not** a Drizzle migration, so the Go migrator must not try to manage it | `database.md §4.5` | G5.4 |
| G5.10 | **Telemetry retention + cleanup job** | **90-day** retention: daily tables older than the window are dropped by a scheduled job | `database.md §4.5` | G5.9 |
| G5.11 | **`GET /radio/telemetry` + the H-9 performance gate** | Time-range query across daily tables (`UNION ALL`). **Gate: a 7-day range (604,800 rows) completes in < 200 ms on a Pi 4 SD card.** If it does not, the alternative design (single table + composite index) is documented before the task closes — the D3.9 gate applies to the Go implementation too | `plan.md` D3.9 (AUDIT H-9) | G5.9 |
| G5.12 | **`gps.db` + `gps_YYYYMMDD` shards + retention** | Same sharding pattern as telemetry, with **365-day** retention (not 90), plus `GET /geolocation/history`'s time-range query | `database.md §4.7`, `plan.md` D6.8 | G5.4 |

**Exit**: radio control and telemetry work end-to-end with no WebSocket/TCP bridge to radiod or Mercury. **The H-9 gate (G5.11) has been *measured on the target*, not assumed**; and the separate `telemetry.db`/`gps.db` files with their retention jobs exist — `database.md` specifies them, and dropping them silently would discard an audited design decision rather than defer it.

### Wave 6 — Packaging and operations

| Task | Deliverable | Acceptance criteria | Ref | Depends on |
|------|-------------|---------------------|:---:|:---:|
| G6.1 | systemd unit | Single unit; restart rate-limiting (AUDIT C-3); **PTT is unkeyed by a mechanism that survives an abnormal exit** (see S3.8) — `ExecStopPost` alone is **not** sufficient, because it does not run on `SIGKILL`, `SIGSEGV`, or an OOM kill | `deployment.md`, ADR-006 → *Transmitter safety* | S3.8 |
| G6.2 | Debian package | Installs binary, config, systemd unit, avahi service (mirrors `hermes-net`) | `deployment.md` | G6.1 |
| G6.3 | RT/isolation config shipped | `isolcpus`/cpuset + `GOMAXPROCS` baked into the unit or documented boot args | ADR-006 R1–R6 | G6.1 |
| G6.4 | Graceful shutdown | Stop telemetry → unkey → close DB on `SIGTERM` | `hardware-integration.md` | G6.1 |
| G6.5 | Retention + `/health/stats` + `/system/alerts` | Parity with Phase 7 tasks | `plan.md` Phase 7 | G1.7 |
| G6.6 | Fault-injection + power-loss tests | Coverage parity incl. fault injection (AUDIT M-10) | `plan.md` D9.2a | G6.4 |

**Exit**: the station installs, boots, survives reboot and power loss, and is operable by a non-developer.

---

## Part 3 — ADR Re-Validation (ADR-001…005 → Go)

ADR-006 exit criterion 5 requires every prior ADR to be re-validated against its Go implementation. ADR-001…005 remain **Accepted and unmodified** — this section records where the Go port needs an *equivalent mechanism* to keep their decisions true, and flags assumptions that are load-bearing.

| ADR | Decision | Holds in Go? | Action required |
|:---:|----------|:---:|----------------|
| 001 | SQLite + WAL, `DatabaseAdapter` seam | ✅ Yes | Driver swap + **§R-1 serialization mitigation** (per-file write discipline) |
| 002 | In-process event bus | ✅ Yes | **§R-2 delivery model must be *specified*, not inherited** |
| 003 | Conversation messaging model | ✅ Yes | None |
| 004 | JWT RS256 + rotation + reuse detection | ✅ Yes | **§R-3 key bootstrap + alg allow-list**, plus **§R-6 documented claim set is wrong** |
| 005 | Last-writer-wins + priority rules | ⚠️ **Conditional** | Depends entirely on §R-1 |

### R-1 (ADR-001, ADR-005) — Serialization must move from the event loop to the storage layer 🔴 **highest-risk item**

Three load-bearing statements assume Node's single-threaded event loop:

- ADR-001 footnote ¹ — *"all writes go through a single Node.js process (the event loop serializes them)."*
- ADR-001 hardware table — *"Writers: Single Node.js process (event loop serializes all writes)."*
- ADR-005 — *"Since all writes are serialized by the Node.js event loop and SQLite's single-writer…"*, reinforced by the SQL comment *"No `updated_at` check needed — SQLite serializes writes. The 'last' write in event loop order is the winner."*

**In Go this is not automatically true.** Goroutines write concurrently and `database/sql` hands out a *pool* of connections. Two concurrent writes mean `SQLITE_BUSY` / `database is locked` — and, worse for ADR-005, a **nondeterministic winner**, which silently invalidates the "last writer wins" guarantee.

**Required mitigation (port-blocking):**

- Split the pools: a **read pool** (WAL allows concurrent readers) and a **write path that resolves to exactly one connection** (`SetMaxOpenConns(1)`) or a single serialized writer goroutine fed by a bounded queue.
- Keep `PRAGMA busy_timeout = 5000` as the second line of defense.
- This restores the serialization ADR-001 and ADR-005 depend on, enforced by the Go layer instead of by V8.
- **Do not** substitute optimistic locking or `updated_at` compare-and-set guards in the edit SQL: ADR-005 deliberately rejected both, and its documented 409 `MESSAGE_DELETED` behavior depends on the check-then-write shape.
- **“One write connection” means one per database file, not one per process.** `database.md` puts the main DB, `telemetry.db`, and `gps.db` in **separate files** specifically to avoid write contention — so the write discipline is per file, and the telemetry/GPS writers must not open a second connection to the main DB.
- **Bounded queue + an explicit overflow policy.** A single writer goroutine fed by an *unbounded* channel is a memory leak on a 4 GB Pi under a write burst. The queue is bounded and what happens at the bound is **decided and written down** (block the producer, or reject with an error the HTTP layer maps to a status). Silence here means unbounded growth.
- **The telemetry writer is the one high-rate writer** (1 Hz, plus GPS): it lives on the same serialized path discipline, and it must not block the RT ring drain (ADR-006 R4).
- **Test:** N goroutines issuing concurrent edit/delete/reaction must produce exactly the ADR-005 outcomes. Add a **deterministic** variant (fixed interleaving via a barrier, e.g. `go test -race -count=100` with a seeded schedule) rather than relying on a chance-ordered stress loop to expose the race.

### R-2 (ADR-002) — The delivery model must be specified, not inherited

ADR-002's guarantees are `EventEmitter`'s; Go channels do not share them.

| ADR-002 claim | Go reality | Requirement |
|---|---|---|
| "Synchronous delivery … within the same tick" | Channel delivery is asynchronous | Specify per-subscriber buffering + ordering; accept and document async |
| `setMaxListeners(50)` | No equivalent | Explicit subscriber cap |
| Listener error isolation | A panicking subscriber kills its goroutine | `recover()` per subscriber — one bad subscriber must not break the bus |
| `emit()` fire-and-forget | Needs `ctx` + error semantics | Bounded queue + documented drop policy for slow subscribers |
| "No persistence … if a listener is not registered, it misses the event" | Same | Unchanged — still acceptable, events needing durability write to SQLite directly |

Two additions the Go bus must account for:

- **Removed subscriber:** ADR-002's diagram shows a **Sync Queue** subscriber. The sync engine was removed (audit C-1, C-4, H-3) — the Go bus must not reintroduce it.
- **New producer:** the engine ring drain (ADR-006 §Event flow) publishes onto the same bus. Because HTTP handlers and the ring drain both publish, **publish order per topic must be defined** — simplest rule: one publisher goroutine per topic.

**Minimum specification — to be written before Wave 1 merges.** "Specify per-subscriber buffering + ordering" is not itself a specification; the following must be *decided and recorded* (in `websocket.md` and/or ADR-002's successor), not left to the implementer:

| Decision | Why it cannot stay implicit |
|---|---|
| **Ordering scope** — per topic, per conversation, or global | HTTP handlers and the ring drain are both publishers. Without a rule, two events for one conversation can be delivered out of order and the UI has no way to detect it |
| **Publisher discipline** — one publisher goroutine per topic | Turns ordering into a property of the bus instead of a property of luck |
| **Per-subscriber buffer size + drop policy** | A slow WS client must not stall the bus. The policy (drop-oldest / drop-newest / disconnect) must also name **which topics it applies to** — `radio:telemetry` is droppable, `MESSAGE_NEW` is not |
| **Panic isolation semantics** | `recover()` per subscriber is in the table above; what is undecided is whether a panicking subscriber is **removed** or retried, and whether the failure is logged/audited |
| **Subscriber cap** | ADR-002's `setMaxListeners(50)` equivalent must be a **number**, and exceeding it must do something defined |

**Durability boundary (what makes the drop policy safe):** ADR-002's "no persistence" stays as decided — but *which* events are additionally written to SQLite is currently unstated. `MESSAGE_*` events are recoverable from the database; `radio:telemetry` is not. That boundary is the reason a drop policy is acceptable for some topics and not others, so it must be written down with it.

### R-3 (ADR-004) — Key bootstrap and algorithm allow-list

1. **Key bootstrap.** ADR-004 says *"Generate RSA key pair (if first run)"*. In Go this must complete **before the server reports itself ready** (or be produced by the install step), and `/auth/login` must fail closed with an explicit error until keys exist. Serving without keys, or silently generating them per request, is not acceptable.
2. **Explicit algorithm allow-list — security-critical.** ADR-004's PASETO discussion rests on *"explicit `algorithms: ["RS256"]`"* preventing `alg: none` attacks. The Go equivalent is **mandatory**: verify with `jwt.WithValidMethods([]string{"RS256"})`. Without it, a token can be submitted as HS256 signed with the public key as the HMAC secret.
3. **Rotation is transactional.** Mark-used + issue-new must be a single transaction on the write connection (§R-1). ADR-004's own negative — *"requires careful transaction handling"* — is stricter under Go concurrency than under a serialized event loop.
4. **The claim set is contract-frozen — and ADR-004 documents the wrong one.** Mirror the **implementation**: access = `sub, callsign, role, locale, iss, iat, exp`; refresh = `sub, type, jti, iss, iat, exp` (`src/auth/token.ts`). ADR-004 lists `permissions` and `station` (which do not exist) and omits `callsign` and `locale` (which do, and `locale` is load-bearing). See §R-6.

### R-4 (ADR-003) — No changes required

ADR-003 is a data-model and API decision with no runtime-language assumptions: conversations as the central entity, per-recipient/per-channel `message_deliveries`, the legacy inbox/outbox read-only shim (Phase 8, D8.7–D8.8), and reaction semantics. It ports verbatim.

One Go-specific note: the `participants × channels` delivery fanout is per-message work inside the now-consolidated process. It belongs on the Go cores (2–3) and must never run on an engine thread — it is reached only through the ring drain (ADR-006 R4).

### R-5 (ADR-001) — Documentation defects: one corrected, one outstanding

ADR-001 documented the adapter selector as `DATABASE_ADAPTER=sqlite`; the implementation reads **`DB_ADAPTER`** (`src/shared/config.ts`). ADR-001's text now matches the implementation, and the Go port uses `DB_ADAPTER`.

A second ADR-001 discrepancy was found and is **not** corrected: ADR-001 documents **7** pragmas, but `src/db/sqlite.adapter.ts` applies only **4** (`journal_mode`, `busy_timeout`, `foreign_keys`, `synchronous`). `cache_size=-64000`, `temp_store=MEMORY`, and `mmap_size=268435456` are documented and never applied. The port task (**G1.3**) requires an explicit decision rather than inheriting the gap — note that the documented `cache_size`/`mmap_size` values matter for the RAM baseline in ADR-006 §1.

### R-6 (ADR-004) — Documentation defects found; ADR-004 must be corrected

Same class of defect as §R-5, found by checking the port contract against the code. **ADR-004's *decision* is unaffected** — it is the documented contract that is wrong, and the port follows the implementation.

**R-6.1 — the documented JWT claim set does not match the implementation.** ADR-004's "RBAC Claims in JWT" documents `permissions: [...]` and `station: "sbitx-v2-001"`. Neither is issued:

| Token | Claims actually issued (`src/auth/token.ts`) |
|---|---|
| Access (`TokenPayload`) | `sub`, `callsign`, `role`, `locale`, `iss`, `iat`, `exp` |
| Refresh (`RefreshTokenPayload`) | `sub`, `type`, `jti`, `iss`, `iat`, `exp` |

So **`permissions` and `station` do not exist**, while **`callsign` and `locale` do and are absent from ADR-004**. `locale` is load-bearing: it is how a client learns the user's language without a second request, and it is what the Go access token must keep emitting. A port that trusted ADR-004 would emit a token the current UI cannot read and would invent two claims nothing consumes. **Action:** ADR-004's claim section carries a correction note; G2.2 is written against this table.

**R-6.1a — the same phantom field appears in the WebSocket contract.** `websocket.md` defines the `AUTHENTICATED` payload as `{ userId, callsign, role, locale, serverTime, connectionId }`, with **no `sessionId`** — yet an earlier revision of G4.2 listed one. Three independent places (`api.md`/ADR-004's claim set, this task, and the WS payload) drifted toward the same non-existent identifier, which suggests `sessionId` survives from an earlier design. **Treat `sessionId` as unverified wherever it appears** and check it against `src/` before porting it; the WS one is corrected in G4.2, and the REST/WS payloads should be swept for others when the fixtures are captured (Freeze Checklist §A).

**R-6.2 — the rate limit that is documented is not the one that is implemented.** The docs describe login protection as *5 failures per IP*. What exists is a **single global limiter** in `src/app.ts`: `global: true`, `max: 300` per `1 minute`, keyed on `request.headers['x-forwarded-for'] ?? request.ip`, returning `{error: 'auth.rate_limited', code: 'RATE_LIMITED'}` with 429.

Two things the port must carry deliberately rather than inherit:

- **Parity means porting the global limiter**, not the per-IP login limiter the docs promise. If per-IP login throttling is actually wanted, it is a **new feature** and needs its own task — and the docs need correcting either way.
- **`X-Forwarded-For` is attacker-controlled.** Using a client-supplied header as the limiter key lets a client evade the limit by varying it, so the limit is not a security control until a trusted proxy strips or overwrites the header. In the consolidated station the backend is likely the **edge** (LAN/avahi, no proxy), which makes this worse rather than better. The Go implementation must bind the key to the real peer address or document the trusted-proxy requirement explicitly.

**R-6.3 — scope of the correction.** ADR-004 is `Accepted`, so it is amended by note rather than silently rewritten (§R-5's silent correction of ADR-001 is not repeated here). Both defects are *documentation* defects: no runtime behaviour changes, and nothing in ADR-004's decision is reopened.

### Re-validation gate

Run this matrix explicitly at the end of the port (ADR-006 exit criterion 5). §R-1 and §R-3.2 are **port-blocking**: without them, ADR-005's "last writer wins" is nondeterministic and ADR-004's `alg` protection claim does not hold. Any divergence found must be documented as a new ADR rather than patched silently.

---

## Contract Freeze Checklist

Before Wave 1 merges, freeze the contract so parity is mechanical rather than remembered. **The list is split by whether a Node implementation exists**, because only the first group can be captured as fixtures.

**A. Implemented surface — capture as fixtures:**

- [ ] REST response corpus for the routes that **exist** (success + every error code) — not the full OpenAPI surface, most of which is unbuilt.
- [ ] Log field corpus (Pino → `slog` field mapping) from `observability.md`.
- [ ] SQLite schema + migration journal hashes (`src/db/migrations/` — 4 migrations plus `meta/`).
- [ ] Telemetry snapshot corpus from `SimulatedRadioDriver`.
- [ ] The bindings that are cheap to record and expensive to get wrong: the **4 applied pragmas** (G1.3), the **canonical JWT claim set** (§R-6.1), the **global rate-limit parameters and key** (§R-6.2), and the `429` body shape.

**B. Specified but not built — freeze the *document*, not a fixture:**

- [ ] WS transcript corpus (handshake, auth, subscribe, event types, close codes) — **there is no gateway to record; `websocket.md` is the contract** (Phase 5).
- [ ] Telemetry time-range query, retention, and `telemetry.db`/`gps.db` sharding — `database.md` §4.5/§4.7 are the contract (Wave 5).
- [ ] Packaging and ops surfaces — `deployment.md` is the contract (Wave 6).

**C. Must be decided before Wave 1 (neither capturable nor yet specified):**

- [ ] The §R-2 delivery model — ordering scope, drop policy, subscriber cap, panic semantics.
- [ ] The §R-1 write-queue bound and overflow policy.
- [ ] The TypeScript **feature-freeze / cut-over point** (ADR-006 → *Freeze/cut-over requirement*).

## Overall Exit Criteria

1. Spikes S1–S3 pass on real sBitx v2 hardware (audio clean under load, R1–R6 enforced, **and the S3.8 abnormal-exit transmitter-safety test passing**).
2. Waves 1–4 pass with the web UI **unmodified**.
3. Waves 5–6 land with parity against the frozen contracts above.
4. Measured RSS and thermal figures meet or beat the **S0.6 baseline captured on the target** — ADR-006 §1 requires a recorded baseline, and without one this criterion is unmeasurable.
5. ADR-001…005 re-validated against the Go implementations; any divergence is documented as a new ADR. The §R-5 and §R-6 documentation defects are resolved (corrected in the ADRs or explicitly adopted).

## Repository topology

*Deferred decision — ADR-006 open question 5. Recorded here because the analysis belongs with the plan; the decision is gated on Spikes S1/S2.*

ADR-006 does **not** decide whether the consolidated artifact gets a new repository. The question is not cosmetic: consolidation changes what the artifact *is*. It stops being "the backend" — a service that talks to engines over protocols — and becomes "the station image": a binary that *is* the station's control plane, linking GPL C engines, ALSA, GPIO, and RT threads. The HTTP/WS contract is a small part of that artifact's surface, but it is the part that already has a spec, a client, and ~340 tests written against it in **this** repository.

### Shape A — stay in `hermes-backend` (rename later if the name hurts)

| Dimension | Effect |
|---|---|
| Traceability | ADR-001…007, `plan.md`, `progress.md`, `database.md`, `api.md`, `websocket.md`, the audits, and the `src/` evidence stay in one tree — so the Go port can cite the TypeScript it replaces, file and line |
| CI | One pipeline; the `aarch64` cgo job (S0.4) is added alongside the existing Node job for the duration of the transition |
| Cost now | Zero |
| Risk | The name becomes wrong: the artifact is the whole station, yet systemd units and Debian packaging (Wave 6) land in a repo called `hermes-backend` |
| Reversibility | Splitting later is cheap — **if** the Go tree is laid out self-contained from S0.1 (`cmd/hermes`, `internal/…`, `cgo/…`, no imports back into the TS tree), which makes a later subtree split mechanical |

### Shape B — new repository now (`hermes-station` / `hermes-core`)

| Dimension | Effect |
|---|---|
| Clarity | The artifact's name matches what it is; the GPL §6 source-offer and Debian packaging live with the thing being shipped |
| Cost now | Every ADR (`docs/adr/`), the architecture docs, `plan.md`, `progress.md`, the audits, and the frozen fixtures must be **ported or duplicated**. Duplication is how two copies of `api.md` drift, and the audit of this plan already found one doc-vs-code defect class (§R-5, §R-6) — a second copy doubles that surface |
| Cross-repo work | Upstream coordination, `hermes-net` packaging, and the `hermes-gui` contract all become cross-repository |
| Transition | The port starts with no `src/`/`tests/` beside it — precisely for Waves 1–2, which *are* translations and depend on reading the code being replaced |
| Reversibility | Merging back later loses the clean split and costs roughly what the split cost |

### Recommendation: Shape A until Spike S2 resolves — then decide explicitly

Three reasons, in order of force:

1. **The deciding input does not exist yet.** If upstream will not expose a linkable core (or accept the S2.6 self-pinning that R1 requires), ADR-006's own fallback is *"Link Mercury only; keep the radio daemon as a WebSocket dependency"* — which is a **backend with a WS client**: exactly what `hermes-backend` already is. Naming a new repository for a station-shaped artifact before knowing whether the station-shaped artifact is viable bakes in an answer the spike can still overturn.
2. **Waves 1–2 need the TypeScript next to them.** "Capture fixtures, then translate" is far cheaper in one working tree than across a repository boundary with a duplicated spec.
3. **The split is cheap later and expensive now** — conditional on S0.1's self-contained layout being honoured from the first commit. That condition is the whole reason this deferral is safe, so **S0.1 is where the option value is created or lost**.

**Trigger to revisit — write it down or the deferral becomes permanent by accident.** The moment S2.6 passes on real hardware (engine self-pins; Go controls the radio in-process), choose Shape A or B **before Wave 5 starts**. Wave 5 is where the artifact's identity stops being hypothetical, and Wave 6 (packaging, Debian, systemd) is where the wrong boundary becomes expensive.

## References

- [ADR-006](../adr/adr-006-go-rewrite-and-station-consolidation.md) — the decision this task list executes
- [`plan.md`](plan.md) — behavioral specification (Phases 0–9)
- [`progress.md`](progress.md) — current implementation state
- [`testing.md`](testing.md) — test strategy to mirror in `go test`
- [docs/audits/comprehensive.md](../audits/comprehensive.md), [plan-review.md](../audits/plan-review.md) — the audit findings cited by task (M-8, H-9, C-3)
- [docs/architecture/api.md](../architecture/api.md), [websocket.md](../architecture/websocket.md), [database.md](../architecture/database.md), [hardware-integration.md](../architecture/hardware-integration.md)
- [docs/operations/deployment.md](../operations/deployment.md), [observability.md](../operations/observability.md)

