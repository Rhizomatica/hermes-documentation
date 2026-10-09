# ADR-006: Go Rewrite and Single-Process Station Consolidation

## Status

**Proposed** (September 2026)

This ADR combines two coupled decisions — the language migration of `hermes-backend` to Go, and the **consolidation of the backend, Mercury (modem), and hermes-radio-daemon (radio controller) into a single linked process**. It re-expresses [ADR-001](adr-001-sqlite-for-pi4.md) (SQLite/WAL) and [ADR-002](adr-002-in-process-event-bus.md) (in-process event bus) in Go, **with two implementation-critical caveats** defined in [`go-migration.md` Part 3](../development/go-migration.md): **§R-1** (single-writer serialization must be re-established at the storage layer — it is currently provided by V8, and Go does not provide it for free) and **§R-3.2** (the explicit RS256 algorithm allow-list is mandatory, not optional). Both are port-blocking. **§R-6** (also in Part 3) records a **documentation defect** in [ADR-004](adr-004-jwt-rs256-token-rotation.md): its documented JWT claim set does not match the implementation. It does **not** supersede [ADR-003](adr-003-conversation-messaging-model.md) or [ADR-005](adr-005-conflict-resolution-strategy.md), whose semantics are preserved verbatim; the remaining parts of ADR-001…005 are likewise unchanged.

**Artifact and repository boundary — deliberately deferred.** Consolidation changes what the artifact *is* (a station image that links two C engines, not a backend that talks to them), which raises whether it should live in a new repository. This ADR does **not** decide that: the boundary depends on the outcome of Spike S1/S2 (whether upstream exposes `libradio_daemon_core.a`), and a repository split is cheap to do later and painful to undo. The two candidate shapes are analysed in [`go-migration.md` §Repository topology](../development/go-migration.md#repository-topology). Until that input exists, the Go implementation lands in **this** repository.

> **Numbering note:** [ADR-005](adr-005-conflict-resolution-strategy.md) contains a forward reference to "an ADR-006" for the future multi-station federation work. Since that work is Phase 10+, this ADR claims `ADR-006` and federation becomes `ADR-007`. ADR-005's reference has been updated to `ADR-007`.

## Context

### 1. The RAM blocker (audit finding CR-1)

The [sbitx-v2 audit](../audits/sbitx-v2.md) identified RAM as the single most critical constraint: the target is a **Raspberry Pi 4 with 4 GB RAM** shared across the OS, the Node.js backend, SQLite, Mercury, and the radio daemon. A single Node.js process on this platform costs **~150–600 MB** resident (V8 heap + `--max-old-space-size=384` + native modules). Consolidation removes that consumer. The C engines' memory is already accounted for today and does not change.

**This ADR makes no claim about binary size.** The saving is the *V8 runtime's resident footprint*, not the artifact's size on disk: a Go binary statically linking the DSP/audio libraries is larger than a pure-Go binary and may well be larger than today's `node_modules` tree. Exit criterion 4 ("meet or beat") is therefore only meaningful against a **recorded baseline**, captured on the target before it is evaluated: total RSS of `node` + the SQLite page cache + `mmap_size` + Mercury + radio daemon + WAL, measured against the ~3.7 GiB actually usable on a 4 GB Pi 4 running the OS.

> The baseline must record **which** pragmas are actually in effect. ADR-001 documents `cache_size = -64000` and `mmap_size = 268435456`, but `src/db/sqlite.adapter.ts` applies neither (it applies 4 of the 7 documented pragmas — see `go-migration.md` G1.3 and §R-5). Quoting the documented values as though they were in use would misstate the baseline by ~300 MB in the one measurement this ADR's main argument rests on.

### 2. The "shared language" rationale is dead

`docs/architecture/api.md` originally justified Node.js partly by *"shared language with the Web UI."* The UI lives in a **separate repository** (`hermes-gui`) and consumes the backend exclusively through **HTTP + WebSocket with JSON**. The backend and the UI share no code, so the language-selection argument for Node no longer applies.

> **Sourcing note:** this repository describes the UI only as *"Web UI for the radio operator"* (`README.md`) and *"Web UI frontend"* (`api.md`) — it does not name a frontend framework. The argument above depends solely on the HTTP/WS/JSON boundary, so no framework is asserted here. Earlier drafts of this ADR named one; that was unsourced and has been removed rather than verified.

### 3. The bridge is the real problem, not the language

**As designed** (`api.md`, `websocket.md`, `hardware-integration.md`), the station is three processes joined by three bridges:

```
┌────────────────────┐   WebSocket (JSON)   ┌──────────────────┐
│ hermes-radio-daemon │◀────────────────────│  hermes-backend  │
│ (C — radio control) │                     │  (Node.js API)   │
└─────────┬───────────┘                     └────────┬─────────┘
          │ shared memory (PTT/keying)               │ TCP TNC
┌─────────▼───────────┐                              │
│       Mercury       │◀─────────────────────────────┘
│     (C — modem)     │
└─────────────────────┘
```

**As implemented today** (`src/hal/sbitx-cli-driver.ts`, plan.md Phase 3 / D3.2 ✅), the backend reaches the radio by **spawning a process per command** — `child_process.execFile('/usr/local/bin/sbitx', […])` with a 5 s timeout for `ptt`, `set-frequency`, `set-mode`, `set-power` — plus one long-lived `sbitx telemetry --interval 1` child whose stdout is parsed line-by-line as JSON. **No WebSocket client and no TCP TNC client exist in this repository**: the WS gateway is Phase 5 (not started, `progress.md`) and a Mercury/TNC integration phase does not exist in [`plan.md`](../development/plan.md) at all.

So the diagram above is the **target station topology** — a design, not a description of the running system — and this ADR is the decision that closes the gap. The costs of the bridge that *actually exists* are concrete:

- **Process spawn per command** — PTT, frequency, mode, and power are separate process invocations with a 5 s timeout and a per-command failure mode, not in-process calls.
- **Text-protocol parsing of a telemetry stream** — 1 Hz JSON read off a child's stdout and split on newlines, with no frame-boundary guarantee and no backpressure.
- **Reconnect / stale-state reconciliation** — exponential backoff and permanent disconnect after 10 consecutive failures (audit finding **M-8**, implemented in D3.2), plus `api.md`'s degraded contract: *"When the daemon is unreachable, the API serves last-known state… `radio.connected: false`"*.
- **Duplicated state** — the backend's view of the radio can diverge from the radio's reality between polls.

### 4. Both engines are C, and one is already linkable from Go

| Engine | Language | Builds today | Linkable? |
|---|---|---|---|
| **Mercury** (modem, `Rhizomatica/mercury`) | C | `mercury` executable **and** `libmercury_core.a` | ✅ **Reported yes** — Mercury's own Go/Fyne GUI is reported to link the core via a cgo bridge. **External claim, not verifiable from this repository**; Spike S1 exists to confirm it. |
| **hermes-radio-daemon** (`Rhizomatica/hermes-radio-daemon`) | C (gcc, `-std=gnu11`) | `radio_daemon` + `radio_client` executables — **no library target** | ⚠️ **Not yet** — but its core is cleanly separated (`radio_daemon_core.c`, `radio_backend.c`, `radio_controls.c`, `radio_pipeline.c`, `dsp/*`, `sbitx/*`) and can be extracted into `libradio_daemon_core.a` |

Both are **GPL-3.0-or-later**, matching `hermes-backend`'s GPL-3.0 — linking is license-compatible. The two engines are reported to share an inter-process shared-memory interface for PTT/keying in the wider station (upstream; **no `hermes_shm` code is vendored in this repository**), which is exactly the kind of loose, duplicated bridge this ADR removes. The in-process handoff introduced below is a **new SPSC ring**, deliberately *not* an extension of that inter-process surface — reusing its name would obscure which mechanism is in play.

**Unverified externals:** every identifier in this section that refers to another repository — `libmercury_core.a`, `mercury_start`/`mercury_send`/`mercury_broadcast`/`mercury_poll`, the proposed `radio_core_*` surface, and the `hermes_shm` name — is sourced from those projects and **cannot be verified from `hermes-backend`**. They are marked here as claims to be confirmed by Spikes S1/S2, not as established facts.

## Decision

**Rewrite `hermes-backend` in Go and consolidate the station into a single process by linking `libmercury_core.a` and (after a core extraction) `libradio_daemon_core.a` into the Go binary via cgo.** The only network surface facing the web UI (`hermes-gui`) is HTTP + WebSocket. The backend stops spawning processes and speaking text protocols to the radio, and instead calls the engines in-process.

### Target architecture

```
┌────────────────────────────────────────────────────────────┐
│  hermes-backend (single Go binary, CGO_ENABLED=1)          │
│                                                            │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ HTTP (chi)   │  │ WS gateway     │  │ Typed event bus│  │
│  └──────┬───────┘  └───────┬────────┘  └───────┬────────┘  │
│         └──────────────────┼──────────────────┘            │
│                     ┌──────▼──────┐                        │
│                     │ HAL (Go)    │  ← Driver seam         │
│                     └──┬───────┬──┘                        │
│        ┌───────────────┘       └──────────────┐            │
│  ┌─────▼──────────────────┐  ┌───────────────▼──────────┐ │
│  │ radio engine (cgo)     │  │ modem engine (cgo)       │ │
│  │ libradio_daemon_core.a │  │ libmercury_core.a        │ │
│  └─────┬──────────────────┘  └────────────┬─────────────┘ │
│        │  ALSA / I²C / GPIO (RT threads)  │ lock-free ring│
└────────┼──────────────────────────────────┼───────────────┘
         │                    ┌─────────────▼──────────┐
     ┌───▼────┐               │ ring → Go reader → WS  │
     │ sBitx  │               └────────────────────────┘
     │ HW     │
     └────────┘

        ┌──────────────────────────────────────┐
        │  Web UI (phone / laptop browser)     │
        └──────────────▲───────────────────────┘
                       └── HTTP + WS (JSON) only
```

### Explicit non-goals

- **Not** a "cgo everywhere" rewrite — the web-UI protocol is untouched (REST + WS + JSON, `hermes-v1` subprotocol).
- **Not** a removal of the HAL seam — `IRadioDriver` is preserved (ported to a Go interface), so `SimulatedRadioDriver` keeps working for tests and dev.
- **Not** a reimplementation of Mercury's or the radio daemon's DSP in Go.

### Build: cgo is mandatory (supersedes the earlier "pure Go" premise)

An earlier draft premise of this decision proposed a `CGO_ENABLED=0`, pure-Go, cross-compiled binary. **That premise is withdrawn** — linking the C engines requires cgo. (The withdrawn premise is recorded here for traceability; it was never written down in this repository, so there is no document to cite, and it should not be treated as an argument anyone made in a review.) The build mirrors Mercury's reported `make fyne-ui` procedure:

```make
# Makefile (sketch)
CC      ?= gcc
CGO_ENABLED = 1
CGO_CFLAGS  = -I$(MERCURY_DIR)/src -I$(RADIOD_DIR) -I$(RADIOD_DIR)/include
CGO_LDFLAGS = -L$(MERCURY_DIR) -L$(RADIOD_DIR) \
              -lmercury_core -lradio_daemon_core \
              -lasound -lfftw3f -lfftw3 -lcsdr -lhamlib -li2c \
              -lspecbleach -lcw -lmbe-neo -liniparser -lcrypto -lssl \
              -lpthread -lm -lrt

build:
	go build -trimpath -ldflags="-s -w" -o bin/hermes-backend ./cmd/hermes
```

Architecture flags follow the radio daemon's own convention (`-march=armv8-a+crc -moutline-atomics` on `aarch64`, `-march=x86-64-v2` otherwise). **Cross-compilation caveat:** because cgo links target-architecture C libraries, the default is to build **on-device or in an `aarch64` container/`debootstrap` chroot** with the target `-dev` packages installed, or to use a full cross toolchain (`aarch64-linux-gnu-gcc`) plus a target sysroot. A naive `GOOS=linux GOARCH=arm64 go build` will not work.

### SQLite driver

Since cgo is now required, use **`github.com/mattn/go-sqlite3`** (cgo) rather than a pure-Go driver — there is no reason to accept a second, slower SQLite implementation when the cgo toolchain is already a hard requirement. All [ADR-001](adr-001-sqlite-for-pi4.md) pragmas are preserved verbatim.

## The Bridge Contract

### What is removed

| Removed | Replaced by |
|---|---|
| **Process spawn per command** — `execFile('/usr/local/bin/sbitx', …)` with a 5 s timeout for PTT / frequency / mode / power | Direct in-process calls into `libradio_daemon_core.a` (control-plane only, off the RT path) |
| **Telemetry stdout-stream parsing** — 1 Hz JSON read off a child process, line-split, no frame boundary | A lock-free SPSC ring drained by a Go goroutine → event bus |
| Reconnect loops, exponential backoff, and permanent disconnect after 10 consecutive failures (audit finding **M-8**, implemented in D3.2) | Nothing — an in-process failure is a process failure |
| Duplicated "backend's idea of radio state" vs. engine state | One state, owned by the linked engine |
| *(not yet built)* Backend → radiod **WebSocket client** + JSON event decoding (Phase 5) | Direct calls into `libradio_daemon_core.a` + lock-free event ring |
| *(not yet built)* Backend → Mercury **TCP TNC client** (no integration phase exists yet) | Direct calls into `libmercury_core.a` (Mercury's cgo bridge pattern) |

> **Removed before they were written.** The last two rows describe design surfaces that do not exist in this repository today (the Phase 5 gateway is not started; Mercury integration has no phase in `plan.md`). They are listed so the removals stay honest: this decision removes them *before* they are implemented rather than after.
>
> **Audit finding M-8 becomes obsolete, by construction — recorded deliberately.** The backoff and permanent-disconnect logic that D3.2 implemented to survive a flaky child process has no counterpart once the engine is linked: a failure *is* a process failure, and recovery is a systemd restart of the single unit. That is a **trade, not a free win** — the same in-process coupling that removes the reconnect logic also changes the transmitter-safety surface (see *Transmitter safety* below), and the two must be read together.

### What is kept

- **HTTP + WebSocket surface to the web UI** — unchanged contract (`api.md`, `websocket.md`, `hermes-v1` subprotocol).
- **`IRadioDriver` / HAL seam** — ported to a Go interface; `LinkedRadioDriver` (cgo-backed) for production, `SimulatedRadioDriver` for dev/test.
- **The `radio.connected: false` degraded contract** — redefined: it now means *"the linked engine failed to initialize or hardware is absent,"* rather than *"the daemon is unreachable."* The API response shape is identical, so the frontend is unaffected.
- **Radio profiles persistence + startup reconciliation** (`radio_profiles`, `api.md` §Radio) — the backend still persists *desired* configuration and applies it to the engine at startup.

### Proposed engine boundaries

Go wraps each engine behind a narrow, testable interface; the C surfaces are **new, minimal, and control-plane only**:

```c
/* Proposed — exposed by libradio_daemon_core.a (new; upstream contribution) */
int  radio_core_init(const char *config_path);
int  radio_core_set_frequency(uint64_t hz);
int  radio_core_set_mode(int mode);
int  radio_core_set_power(float watts);
int  radio_core_ptt(int on);
int  radio_core_get_state(radio_state_t *out);   /* snapshot, RT-safe read */
int  radio_core_event_fd(void);                  /* poll-able event pipe, no callbacks */
```

```
Existing — reused from Mercury's Go/Fyne cgo bridge:
  mercury_start() / mercury_send() / mercury_broadcast() / mercury_poll()
```

> The `radio_core_*` names are **proposed**, not existing API. Extracting this surface from `radio_daemon.c` is a prerequisite task (see Implementation).

**Open question:** whether `radiod` remains a separate systemd unit for other consumers (the Fyne GUI, the CAT gateway on port 4534, rigctld, loggers) or is fully absorbed into the backend. Recommendation: keep `radiod` **buildable and installable** upstream, but have the backend link the core — so the station's protocol gateway surfaces for third-party loggers (`cat_server.c`) are not lost.

## Threading and Real-Time Isolation Contract

The radio daemon performs **ALSA audio, RTP, DSP (FT8/CW/RTTY/D-Star/RADE), and GPIO/I²C hardware I/O**. Co-locating this with a Go HTTP server is safe **only under an explicit isolation contract**. The risk is *not* that HTTP/WS traffic interferes with audio through the protocol — it cannot — but that Go and the C engines now **share one process's CPU, caches, allocator, and locks**.

### Coupling vectors and required rules

| # | Coupling vector | Rule |
|---|---|---|
| R1 | **CPU sharing** | Boot-time `isolcpus=0,1` on the kernel command line, **plus engine self-pinning** — each RT thread calls `pthread_setaffinity_np` (or the engine's own equivalent, e.g. Mercury's `-c <cpu>`) to bind itself to core 0/1. `GOMAXPROCS=2` only bounds Go's parallelism; it does **not** place Go's threads, so it is not an isolation mechanism. See *R1 and R2 in practice* below. |
| R2 | **Scheduling** | Audio/DSP/modem threads run `SCHED_FIFO` at appropriate RT priority; **buffer-level `mlock`** on the RT audio/DSP buffers; zero allocations on the audio path. Process-wide `mlockall` is **not** the mechanism here — see *R1 and R2 in practice* below. |
| R3 | **Thread ownership** | Engines spawn their **own `pthread`s** via `pthread_create`; never driven from Go-created threads |
| R4 | **C → Go direction** | The engine **never calls into Go**. It posts to a lock-free SPSC ring; a Go-owned goroutine drains it. *(This is the one real coupling path — the WS fanout must not run on the engine's thread.)* |
| R5 | **Locks** | No shared mutex between the RT path and Go. WS-driven commands (PTT/frequency) go through a command **queue**, never a lock the audio thread holds |
| R6 | **cgo call direction** | Go → C calls are control-plane only, off the RT path |

### Core budget (Raspberry Pi 4, 4 × Cortex-A72)

```
core 0 : radio engine audio/DSP/ALSA/I²C   (RT, isolated; RT buffers locked)
core 1 : Mercury modem DSP                 (RT, isolated — Mercury has a -c <cpu> equivalent)
core 2 : Go — HTTP, WS fanout, SQLite      (GOMAXPROCS=2)
core 3 : Go — HTTP, WS fanout, SQLite
```

**Consequence:** real-time DSP/audio becomes **independent of HTTP/WS load — but only once the configuration below actually holds**. A burst of WS clients or a flood of SQLite writes runs on cores 2–3 and cannot inject jitter into cores 0–1. What must be validated on real hardware is the **isolation configuration** (R1–R6), not the WS load itself. If the isolation leaks — Go left on all four cores, or a shared lock on the WS command path — glitches will appear, and the cause will be the leak, not the traffic.

### R1 and R2 in practice (both require work not yet in the plan)

R1–R2 are stated as outcomes. Turning them into a configuration exposes two problems that must be solved *in the spikes*, because neither is a checkbox:

**R1 — "`isolcpus`/cpuset" is not one mechanism, and neither works alone.**

- A **cgroup cpuset applies to the whole process**, so it cannot give cores 0–1 to the engines while cores 2–3 serve Go *from inside a single process*. Only **`isolcpus=0,1`** (removing those cores from the general scheduler balance) produces the intended map. On 6.x kernels `isolcpus` is deprecated in favour of cpuset v2 partitions, so the mechanism must be validated against the target kernel rather than assumed.
- **Go has no supported API for pinning runtime threads to specific cores.** `GOMAXPROCS=2` bounds parallelism; it places nothing. "Keep Go off cores 0–1" is a *kernel-level* property (isolation), not a Go-level setting.
- **The engines must pin themselves.** `pthread_setaffinity_np` has to be called *by each RT thread*, which is **new C code inside `hermes-radio-daemon`** and appears nowhere in the current spike list. Until it exists, the `ps -eLo tid,comm,psr,cls` check in S3.3 can pass by luck on an unloaded system and fail under load.
- Pinning engine threads from the Go side (by `tid`, via `/proc`) is possible in principle but racy and unsupported. If upstream will not take self-pinning, that trade-off must be decided explicitly rather than discovered during validation.

**R2 — process-wide `mlockall` is the wrong tool in a process that hosts a Go runtime.**

`mlockall(MCL_CURRENT | MCL_FUTURE)` attempts to lock *the Go heap and every future allocation*: it will hit `RLIMIT_MEMLOCK` (default 64 KiB — needing `CAP_IPC_LOCK` or a raised limit in the systemd unit) and it fights the Go runtime's own `madvise`/scavenging behaviour and heap growth. The requirement is **`mlock` on the RT buffers only** — audio ring, DSP scratch, and engine state touched by the RT path — leaving Go's heap pageable. "Zero allocations on the audio path" is the actual determinism guarantee; `mlockall` was standing in for it.

### Transmitter safety: an existing risk whose stated mitigation does not work

**The risk is not created by this decision.** Today `pttOn()` and `pttOff()` are two *independent* process invocations (`execFile('sbitx', ['ptt','on'])` / `['ptt','off']`, `src/hal/sbitx-cli-driver.ts`). A backend crash *between* them already leaves the transmitter keyed, with no watchdog, no systemd unit (packaging is a later phase), and no unkey-on-exit path.

**What this decision changes is the mitigation surface — and the mitigation proposed for it is ineffective.** [`go-migration.md` G6.1](../development/go-migration.md) proposes *"`ExecStopPost` unkeys PTT."* **`ExecStopPost` does not run when the main process dies from `SIGSEGV`, `SIGKILL`, or the OOM killer** — precisely the abnormal exits that matter. In a consolidated process the engine holds keyed state inside a long-lived unit, so a DSP fault, a cgo violation, or a Go runtime crash mid-transmission leaves a **sustained unmodulated carrier** (interference, PA/thermal exposure, and a possible licence issue).

**Requirement:** the mitigation must be **independent of the dying process** and must be tested rather than assumed. Candidate mechanisms, to be chosen during the spike:

1. **systemd watchdog** (`WatchdogSec` + `sd_notify`), with the stop path unkeying *and* a hardware-side deadman; or
2. a **minimal separate PTT supervisor** that owns the keying line and requires a heartbeat — process dies, heartbeat stops, key drops; or
3. an **engine-side deadman** on the RT thread that unkeys on a missed heartbeat — noted as the *weakest* option, because it dies with the same crash it is meant to survive.

**Positive counterpart:** after consolidation, SWR protection becomes an in-process engine-side reaction instead of a `pttOff()` triggered by parsing a 1 Hz telemetry line (`src/hal/sbitx-cli-driver.ts` cuts TX when `swr_reading > 3.0 && ptt_active`). That path gets faster and more reliable — it is the one safety mechanism that improves.

### Event flow (the single handoff)

```
engine thread ──post──▶ lock-free SPSC ring ──drain──▶ Go goroutine ──▶ event bus ──▶ WS gateway
     (RT, C)          (in-process SPSC ring)             (Go)              (Go)         (Go)
```

## Component Mapping (TypeScript → Go)

| Concern | Today (Node/TS) | Go |
|---|---|---|
| HTTP framework | Fastify v5 | `net/http` + `chi` |
| Schema validation | Zod | Structs + `go-playground/validator` |
| ORM / queries | Drizzle + better-sqlite3 | `sqlc` or `sqlx` + `mattn/go-sqlite3`; **same `.sql` migrations** applied by an embedded migrator |
| Event bus ([ADR-002](adr-002-in-process-event-bus.md)) | `EventEmitter` | Typed in-process bus (channels) — decision unchanged |
| JWT ([ADR-004](adr-004-jwt-rs256-token-rotation.md)) | `@fastify/jwt` (RS256) | `golang-jwt/jwt/v5` — same claims, rotation, reuse detection |
| Password hashing | bcrypt | `golang.org/x/crypto/bcrypt` |
| Logging | Pino | `log/slog` (JSON handler) |
| Config | `src/shared/config.ts` | Same env contract (`RADIO_DRIVER`, `DB_ADAPTER`, `JWT_*`, `PORT`, …) |
| i18n | JSON + `check-i18n` | JSON via `embed` + same checker |
| Tests | Vitest (~340 tests) | `go test` + `httptest`; keep `SimulatedRadioDriver` |
| Packaging | npm + systemd | Single binary + systemd + Debian packaging (as `hermes-net` already does) |

## Consequences

### Positive

- **RAM headroom** — removes the largest remaining consumer on a 4 GB Pi (node/V8), directly addressing audit finding CR-1.
- **No bridge to maintain** — the WebSocket/TCP clients, JSON schemas, reconnect logic, and stale-state reconciliation for two internal links disappear.
- **One source of truth for radio state** — the backend reads the engine directly; no divergence window.
- **Deployment matches the ecosystem** — a single systemd unit and a Debian package, consistent with `hermes-net`'s existing model; no npm toolchain on the target.
- **Cleaner concurrency** — Go for telemetry (1 Hz), WS fanout, and bcrypt/JWT off the event loop; C RT threads for DSP.
- **Mercury linkage is reported to be already proven** — Mercury's Fyne GUI establishes the cgo pattern upstream (external claim; confirmed by Spike S1).

### Negative

- **cgo build complexity** — cross-compilation must go through a target sysroot or on-device build; CI must produce `aarch64` artifacts with the C libraries present.
- **C library provenance is unresolved** — the sketch above links the engines' own dependency list (`-lcsdr`, `-lspecbleach`, `-lmbe-neo`, `-lcw`, `-lhamlib`, …). Whether those are vendored, built from source in CI, or taken from the target distro determines the build's reproducibility — and shipping a combined binary that links GPL-3.0 libraries carries a **source-offer obligation (§6) for the exact sources used**.
- **Upstream C refactor required — and it is more than the library extraction** — `hermes-radio-daemon` must expose a linkable core (`libradio_daemon_core.a`) *and* its RT threads must pin themselves (R1; see *R1 and R2 in practice*). This is C work in another repository and a coordination cost with its maintainer.
- **Transmitter safety must be re-engineered and tested** — the plan's `ExecStopPost` mitigation does not run on abnormal exits (see *Transmitter safety*). A mechanism independent of the dying process must be chosen and proven before this can be accepted as a production station.
- **Fault isolation is lost by design** — a crash in the radio/DSP engine takes down HTTP/WS. Recovery is a systemd restart of the single unit. This is a conscious trade for the simplification.
- **Larger binary** — statically linked DSP/audio libraries make the artifact far bigger than a pure-Go binary. Resident memory is the metric that matters (see §1); binary size is not claimed to improve.
- **Real-time co-location risk** — the isolation contract (R1–R6) must hold, and R1 requires new upstream C code for it to hold at all. This is the primary hardware validation item.
- **TypeScript work does not stop by itself** — until a cut-over is declared, feature work in this repository continues to grow the surface the port must match (Phases 4–9 are unbuilt, and a Mercury integration phase is not yet planned). **A freeze/cut-over point must be named as part of accepting this ADR.**
- **Language churn (smaller than it looks, for the same reason)** — the *implemented* surface (~4,270 LOC, ~340 tests) is rewritten. Most of Phases 3–9 exists as specification rather than code, so those waves are **built to spec**, not translated. ADR-001…005 must still be re-validated against the Go implementations.

## Implementation Plan

Aligned to [`docs/development/plan.md`](../development/plan.md). **State of the reference implementation:** Phases 0–2 complete, Phase 3 partially complete (D3.1–D3.4 landed), **Phases 4–9 not started** — so most of the porting surface exists as *specification* (`plan.md` + the architecture docs) rather than as Node behavior. Waves 1–2 are translations of working code; Waves 3–6 are **built to spec**, using the Node implementation as a reference only where it exists.

**Freeze/cut-over requirement.** Accepting this ADR must come with a **named point at which TypeScript feature work stops** (bug fixes on already-✅ tasks remain permitted). Without that, the parity surface keeps growing while the port is being written — which raises the cost of the decision continuously and makes "today's Node behavior wins" progressively less meaningful. The detailed spike and port task list lives in [`docs/development/go-migration.md`](../development/go-migration.md).

**Spikes (gate the whole migration — must pass before porting domain code):**

1. **Spike A — Mercury link.** Go binary links `libmercury_core.a` via cgo; drive ARQ send/receive in-process, reusing Mercury's `mercury_bridge` pattern.
2. **Spike B — radio-daemon link.** Extract `libradio_daemon_core.a` upstream; link it; run it alongside a synthetic HTTP/WS load generator on real sBitx hardware and measure audio/DSP stability (target: no dropouts with R1–R6 enforced).
3. **Spike C — isolation validation.** Verify the core map, RT priorities, `mlockall`, lock-free handoff, and absence of Go callbacks on RT threads.

**Porting waves (after Spikes A–C pass):**

1. **Foundation** — config, `slog`, SQLite + migrations, event bus, HTTP skeleton.
2. **Auth** — port ADR-004 semantics (login/refresh/logout, rotation, reuse detection).
3. **Domain** — users, conversations, messages, reactions, attachments, audit (ADR-003, ADR-005).
4. **WS gateway** — `hermes-v1` protocol parity (`websocket.md`).
5. **Radio** — `LinkedRadioDriver` over the extracted core; telemetry 1 Hz; SWR protection; profiles reconciliation.
6. **Packaging** — systemd unit, Debian package, avahi/CAT gateway parity.

**Compat requirement:** the API and WS contracts are frozen during the rewrite; the web UI must not require changes. **Ambiguity resolution is split by surface:** for surface that is *implemented*, today's Node behavior wins; for surface that is *specified but not built*, the architecture docs (`api.md`, `websocket.md`, `database.md`, `users-and-permissions.md`) are authoritative — there is no Node behavior to defer to. The freeze checklist in [`go-migration.md`](../development/go-migration.md) is split along exactly those lines.

**Re-validation gate:** ADR-001…005 are re-validated against the Go implementations in [Part 3 of `go-migration.md`](../development/go-migration.md). Two items are port-blocking: **§R-1** (single-writer serialization, which ADR-005's "last writer wins" silently depends on) and **§R-3.2** (explicit RS256 algorithm allow-list).

## Alternatives Considered

### Keep Node.js; consume Mercury and the radio daemon as external clients
Rejected. This is the model the project is explicitly moving away from: it leaves the RAM blocker (CR-1) in place, keeps two serialized bridges plus their reconnect/stale-state logic, and does nothing to simplify the station. It also keeps the now-vacuous "shared language with the UI" rationale alive.

### Pure Go, `CGO_ENABLED=0`, external clients, cross-compiled
Rejected. Incompatible with the core requirement of linking the C engines. A pure-Go build cannot call `libmercury_core.a` or `libradio_daemon_core.a`. The earlier analysis that proposed this is withdrawn.

### Link Mercury only; keep the radio daemon as a WebSocket dependency
Viable **fallback / intermediate step** (and essentially Spike A in isolation). Retains the daemon WebSocket bridge and its reconciliation logic, so it delivers half the simplification. Recommended only as a waypoint if Spike B proves too costly.

### Reimplement Mercury and the radio daemon in Go
Rejected. Would discard years of hardened real-time DSP (FT8, RADE, ALSA, GPIO/I²C, SWR protection) and diverge from upstream, creating a permanent fork burden. The C engines are the durable asset.

### Consolidate into a single C/C++ application
Rejected. Loses Go's concurrency model, standard library, and ecosystem for the HTTP/WS/database/auth layers, which are the bulk of `hermes-backend`.

## Validation / Open Questions

1. **Audio stability under load** on real sBitx hardware with R1–R6 enforced (Spikes B and C).
2. **Upstream buy-in** for extracting `libradio_daemon_core.a` from `hermes-radio-daemon` — **and, separately, for RT-thread self-pinning (`pthread_setaffinity_np`), which R1 requires but which is not part of the library extraction** (see *R1 and R2 in practice*).
3. **Which isolation mechanism holds on the target kernel** — `isolcpus` vs cpuset v2 partitions on the kernel actually shipped by `hermes-net`.
4. **Which transmitter-safety mechanism is adopted** (systemd watchdog + hardware deadman, separate PTT supervisor, or engine-side deadman) and how it is tested — see *Transmitter safety*.
5. **The repository/artifact boundary** — deferred by this ADR and gated on items 2 and 6; the two candidate shapes are in [`go-migration.md` §Repository topology](../development/go-migration.md#repository-topology).
6. **Build/CI pipeline** for `aarch64` cgo artifacts (on-device, chroot, or cross toolchain + sysroot), including whether the engines' C dependencies are vendored or distro-provided, and the GPL §6 source-offer for the shipped binary.
7. **Fate of `radiod`** as a standalone unit for the Fyne GUI / CAT gateway / rigctld consumers.
8. **Measured RAM and thermal budget** of the consolidated process vs. the current three-process layout — including the **recorded baseline** required by §1 before exit criterion 4 can be evaluated.

## References

- [docs/audits/sbitx-v2.md](../audits/sbitx-v2.md) — CR-1: RAM as the primary blocker
- [docs/development/plan.md](../development/plan.md) — Phase map for the port
- [docs/development/go-migration.md](../development/go-migration.md) — Spike and port task list
- [docs/development/progress.md](../development/progress.md) — current implementation state
- [docs/architecture/api.md](../architecture/api.md) — API contract, `radio.connected: false` reconciliation
- [docs/architecture/websocket.md](../architecture/websocket.md) — `hermes-v1` gateway protocol
- [docs/architecture/hardware-integration.md](../architecture/hardware-integration.md) — HAL design and degraded modes
- [ADR-001](adr-001-sqlite-for-pi4.md) — SQLite (WAL) as primary database
- [ADR-002](adr-002-in-process-event-bus.md) — in-process event bus
- [ADR-003](adr-003-conversation-messaging-model.md) — conversation-based messaging model
- [ADR-004](adr-004-jwt-rs256-token-rotation.md) — JWT RS256 with refresh rotation
- [ADR-005](adr-005-conflict-resolution-strategy.md) — conflict resolution strategy
- [Rhizomatica/mercury](https://github.com/Rhizomatica/mercury) — modem engine; `libmercury_core.a` + existing cgo bridge
- [Rhizomatica/hermes-radio-daemon](https://github.com/Rhizomatica/hermes-radio-daemon) — radio controller; C sources and build flags
- [Rhizomatica/hermes-net](https://github.com/Rhizomatica/hermes-net) — systemd/Debian packaging model

