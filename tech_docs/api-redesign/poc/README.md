# HERMES Redesign — POC Structure

2026-10-09 · draft POC — structure only, no implementation

## Purpose

This folder captures the **shape of the redesign** as contracts and a directory
map, so the real backend and frontend can be built against a fixed, agreed
structure. Nothing here is implemented: there is no source, no features, no
behaviour.

It embodies three decisions (see [`../COMPARISON.md`](../COMPARISON.md)):

1. **One logical API** — hermes-radio-daemon is the station's backend and
   includes Mercury in-process (D-03); it serves REST and WebSocket on one
   port, *not* one deployable per service.
2. **Split by transport, not by service** — REST for stored state and commands
   (`api-rest.yaml`), WebSocket for pushed state (`api-ws.yaml`, `hermes.v1`),
   and a voice/media path gated off by default.
3. **Split by domain inside the process** — bounded contexts with clear route
   prefixes — plus **independent frontend apps** that all consume the same
   versioned contracts.

The complete component diagram lives in [`architecture.md`](architecture.md).

## Directory map

```
poc/
├── README.md                      # this file
├── architecture.md                # mermaid diagram of the complete architecture
├── contracts/
│   ├── openapi.yaml               # pointer → the canonical REST spec (api-rest.yaml)
│   ├── ws-protocol.md             # pointer → the canonical WS spec (api-ws.yaml, hermes.v1)
│   └── connectors.md              # the remaining seams (radio_client, UUCP ties)
└── frontend/                      # independent micro-apps, one contract
    ├── shell/                     # host + /apps registry
    └── apps/
        ├── chat/                  # hermes-chat
        ├── gps/                   # hermes-gps
        ├── radio/                 # hermes-radio (telemetry / spectrum / voice)
        └── email/                 # hermes-email
```

> The backend is hermes-radio-daemon, not a new Go service; there is no
> `backend/` tree in this POC. Its REST surface is `../api-rest.yaml` and its
> WebSocket surface is `../api-ws.yaml`.

## Mapping to the design docs

| Structure element | Design document |
| --- | --- |
| `architecture.md` | `../COMPARISON.md` (D-00, D-03, D-05, D-07, D-23) + `../api-rest.yaml` / `../api-ws.yaml` |
| `contracts/openapi.yaml` | `../api-rest.yaml` (canonical REST contract) |
| `contracts/ws-protocol.md` | `../api-ws.yaml` (canonical `hermes.v1` WebSocket contract) |
| `contracts/connectors.md` | `../COMPARISON.md` D-03/D-05/D-23; `../README.md` "must keep working" |
| `frontend/apps/*` | `api-rest.yaml` `/apps` |

## Stack note

The backend is **hermes-radio-daemon** (which includes Mercury). The contracts
are transport-level and language-agnostic, so they bind the backend and the
frontend apps to the same surface. Runtime details are intentionally left out
of this POC.
