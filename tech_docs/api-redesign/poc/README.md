# HERMES Redesign — POC Structure

2026-10-09 · draft POC — structure only, no implementation

## Purpose

This folder captures the **shape of the redesign** as contracts and a directory
map, so the real backend and frontend can be built against a fixed, agreed
structure. Nothing here is implemented: there is no Go source, no features, no
behaviour.

It embodies three decisions:

1. **One logical API** — a modular monolith (a single Go binary, per
   [ADR-006](../hermes-backend/adr/adr-006-go-rewrite-and-station-consolidation.md)),
   *not* one deployable per service (no separate GPS API, chat API, email API…).
2. **Split by transport, not by service** — REST for stored state and commands,
   WebSocket for pushed state, and a voice/media path gated off by default.
3. **Split by domain inside the process** — bounded contexts under `internal/`
   with clear route prefixes — plus **independent frontend apps** that all
   consume the same versioned contracts.

The complete component diagram lives in [`architecture.md`](architecture.md).

## Directory map

```
poc/
├── README.md                      # this file
├── architecture.md                # mermaid diagram of the complete architecture
├── contracts/
│   ├── openapi.yaml               # REST contract — single source of truth
│   ├── ws-protocol.md             # WebSocket contract (hermes-v1)
│   └── connectors.md              # engine connector contract (radio-daemon + mercury)
├── backend/                       # modular monolith — ONE Go binary (ADR-006)
│   ├── cmd/hermes/                # main entrypoint package
│   ├── internal/
│   │   ├── auth/                  #   JWT RS256 + RBAC (admin/operator/user/readonly)
│   │   ├── connectors/            #   engine connectors (interfaces only)
│   │   │   ├── radio-daemon/      #   RadioDaemonConnector → hermes-radio-daemon
│   │   │   └── mercury/           #   MercuryConnector → mercury modem
│   │   ├── radio/                 #   radio domain (uses RadioDaemonConnector)
│   │   ├── messaging/             #   conversations + messages (chat and email share this)
│   │   ├── geolocation/           #   GPS position + history
│   │   ├── system/                #   config, clock, reboot, setup
│   │   ├── email/                 #   store-and-forward transport boundary (UUCP/Postfix)
│   │   ├── gateway/               #   rest (net/http) + ws (hermes-v1)
│   │   ├── events/                #   in-process event bus (ADR-002)
│   │   └── store/                 #   DatabaseAdapter (SQLite now → Postgres later)
│   ├── cgo/                       #   C-engine bridges (cgo link, ADR-006 Spike B)
│   │   ├── radio-daemon/          #   → libradio_daemon_core.a
│   │   └── mercury/               #   → libmercury_core.a
│   └── api/                       #   imports ../contracts/ at build time
└── frontend/                      # independent micro-apps, one contract
    ├── shell/                     # host + /apps registry
    └── apps/
        ├── chat/                  # hermes-chat
        ├── gps/                   # hermes-gps
        ├── radio/                 # hermes-radio (telemetry / spectrum / voice)
        └── email/                 # hermes-email
```

> The backend tree is descriptive only. No `.go` files exist in this POC; it
> shows *where* each bounded context will live when implementation starts.

## Mapping to the design docs

| Structure element | Design document |
| --- | --- |
| `architecture.md` | `README.md` §Proposed architecture + `architecture.svg` |
| `contracts/openapi.yaml` | `hermes-backend/architecture/api.md` §4 (endpoints), §2 (principles) |
| `contracts/ws-protocol.md` | `hermes-backend/architecture/websocket.md` |
| `contracts/connectors.md` | `hardware-integration.md` (IRadioDriver) + ADR-006 (Spikes A/B) |
| `backend/internal/events/` | ADR-002 (in-process event bus) |
| `backend/internal/store/` | ADR-001 (SQLite WAL) + `database.md` (DatabaseAdapter) |
| `backend/internal/connectors/` + `backend/cgo/` | `contracts/connectors.md` + ADR-006 + `go-migration.md` S0.1/S1.x |
| `backend/` single binary | ADR-006 (Go rewrite + station consolidation) |
| `frontend/apps/*` | `api.md` §4.14 (`/apps`, `installedApps`) |

## Stack note

The backend is **Go** (ADR-006). The contracts are transport-level and
language-agnostic, so they bind the Go backend and the frontend apps to the
same surface. Runtime details (REST via `net/http`, WS via a Go library) are
intentionally left out of this POC.
