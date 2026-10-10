# HERMES Engine Connectors

Contract for how the Go backend reaches the two C engines. The backend is a
single binary (ADR-006) that either **bridges to the running daemons over
WebSocket** (fallback, Spike A) or **links the C cores directly via cgo**
(target, Spike B). This file declares the connector interfaces that hide that
choice from the domain modules.

Status: draft POC — structure only (no Go source).

## Why connectors exist

`hermes-radio-daemon` (radio control + telemetry) and `mercury` (HF modem) are
hardened C DSP engines with their own release cycles. They are *not* business
services to be split into their own APIs; they are hardware-adjacent engines
the backend must talk to. A connector is the seam that:

- hides the transport (WebSocket bridge now, cgo link later),
- isolates the C/DSP boundaries so domain modules stay testable,
- lets radio and modem state flow into the in-process event bus (ADR-002)
  and out to the `hermes-v1` WebSocket gateway (`ws-protocol.md`).

## Base interface

```go
// Connector is the lifecycle + health contract shared by every engine connector.
type Connector interface {
    Name() string
    Connect(ctx context.Context) error
    Close() error
    State(ctx context.Context) (EngineState, error)
}

// EngineState is the health snapshot every connector reports.
type EngineState struct {
    Name      string
    Connected bool
    Stale     bool // last-known state, engine unreachable
}
```

## Radio daemon connector

Mirrors `IRadioDriver` in `hardware-integration.md`, re-expressed in Go.

```go
type RadioDaemonConnector interface {
    Connector

    // Commands (request/response)
    GetStatus(ctx context.Context) (RadioStatus, error)
    SetFrequency(ctx context.Context, khz int) error
    SetMode(ctx context.Context, mode RadioMode) error
    SetPower(ctx context.Context, watts int) error
    SetPTT(ctx context.Context, on bool) error
    GetSWR(ctx context.Context) (float64, error)
    ResetProtection(ctx context.Context) error

    // Events pushed engine → backend → event bus → gateway
    Subscribe(ctx context.Context) (<-chan RadioEvent, error)
}

type RadioMode string // "USB" | "LSB" | "AM" | "FM" | "CW"

type RadioStatus struct {
    FrequencyKhz int
    Mode         RadioMode
    Power        int
    SWR          float64
    Temperature  float64 // °C
    TXActive     bool
}

type RadioEvent struct {
    Type    string // "telemetry" | "state" | "spectrum" | "swr-protection"
    Payload []byte // JSON, or raw binary for spectrum
}
```

## Mercury connector

Exposes the modem state the station UI historically could not see (link, SNR,
bitrate, transfer progress) — see `README.md` §Current state.

```go
type MercuryConnector interface {
    Connector

    GetLinkState(ctx context.Context) (LinkState, error)
    SetConfig(ctx context.Context, cfg ModemConfig) error
    StartLink(ctx context.Context) error
    StopLink(ctx context.Context) error

    Subscribe(ctx context.Context) (<-chan ModemEvent, error)
}

type LinkState struct {
    Connected bool
    SNR       float64 // dB
    Bitrate   int     // bit/s
    BytesTx   int64
    BytesRx   int64
}

type ModemConfig struct {
    // bandwidth, waveform, frequency — expanded from the real daemon
}

type ModemEvent struct {
    Type    string // "link" | "transfer" | "spectrum" | "chat"
    Payload []byte
}
```

## Transport strategy

Two implementations of each connector, selected at build time; both satisfy the
same interface so nothing above this layer changes.

| Transport | Shape | Status |
| --- | --- | --- |
| **WebSocket bridge** | backend dials the daemon's socket (`/ws/radio` :8080, `/ws/modem` :10000) | Fallback / waypoint (Spike A, ADR-006) |
| **cgo link** | backend links `libradio_daemon_core.a` / `libmercury_core.a` and calls `mercury_start()` | Target (Spike B, ADR-006) |

The cgo bridge lives in `backend/cgo/`; the Go-side interfaces live in
`backend/internal/connectors/`. Event handoff from the C engines is via
poll/ring (`go-migration.md` S1.3), never a C→Go callback on the engine thread.

## Mapping to the design docs

| Element | Source |
| --- | --- |
| `RadioDaemonConnector` | `hardware-integration.md` (IRadioDriver) |
| Radio state → gateway topics | `websocket.md` (`radio:telemetry`, `radio:spectrum`) |
| cgo link + consolidation | ADR-006 (Spikes A/B) |
| repo layout `cmd/`, `internal/`, `cgo/` | `go-migration.md` S0.1 |
| Mercury bridge pattern | `go-migration.md` S1.1 (`mercury_bridge`) |
