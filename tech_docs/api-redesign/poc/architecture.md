# HERMES Redesign — Complete Architecture

2026-10-09 · draft POC — structure only

The complete target architecture as one diagram. **Solid arrows** are
request/command flows; **dotted arrows** are event pushes (engine → connector →
in-process bus → gateway → WS subscribers). Companion to the contracts in
`contracts/`.

```mermaid
flowchart TB
    Browser["Browser — phone / laptop (WiFi)"]:::client

    subgraph Nginx["nginx :443 — single front door (TLS)"]
        N["nginx"]
    end

    subgraph Apps["Frontend micro-apps (static, run in browser)"]
        Shell["shell — host + /apps registry"]
        Chat["hermes-chat"]
        GPS["hermes-gps"]
        RadioApp["hermes-radio"]
        EmailApp["hermes-email"]
    end

    subgraph Backend["hermes-backend — modular monolith (one Go binary)"]
        GW["gateway — REST /api/v2 + WS hermes-v1"]
        Auth["auth"]
        RadioDomain["radio"]
        Messaging["messaging (chat + email)"]
        Geo["geolocation"]
        System["system"]
        Conn["connectors"]
        Bus["events — in-process bus (ADR-002)"]
        Store[("store — SQLite WAL → Postgres")]
    end

    subgraph Engines["C engines"]
        Radiod["hermes-radio-daemon"]
        Mercury["mercury (HF modem)"]
    end

    HF["HF transceiver (sBitx v2)"]:::ext
    UUCP["UUCP / Postfix — store-and-forward email"]:::ext

    Browser -->|HTTPS| N
    N -->|static files| Shell
    Shell --> Chat
    Shell --> GPS
    Shell --> RadioApp
    Shell --> EmailApp

    Chat -->|REST + WS| N
    GPS -->|REST + WS| N
    RadioApp -->|REST + WS| N
    EmailApp -->|REST + WS| N

    N -->|REST /api/v2| GW
    N -->|WS hermes-v1| GW

    GW --> Auth
    GW --> RadioDomain
    GW --> Messaging
    GW --> Geo
    GW --> System

    RadioDomain --> Conn
    Messaging --> Conn
    Messaging --> UUCP

    Conn -->|"WS bridge (Spike A) / cgo link (Spike B)"| Radiod
    Conn -->|"WS bridge / cgo link"| Mercury

    Radiod --> HF
    Mercury --> HF

    Radiod -.->|telemetry / spectrum| Bus
    Mercury -.->|link / transfer| Bus
    Messaging -.->|message events| Bus
    Bus -.->|push| GW

    GW --- Store
    Auth --- Store
    Messaging --- Store

    classDef client fill:#fff3cd,stroke:#b58900
    classDef ext fill:#ffe0e0,stroke:#c0392b
```

## Legend

- **Solid arrows** = request/command flow; **dotted arrows** = event push
  (via the in-process bus → gateway → WS subscribers).
- **Connectors** are the seam hiding the transport: WebSocket bridge *now*
  (Spike A) vs. cgo link *later* (Spike B, ADR-006).
- **`messaging`** spans chat and email — the same store-and-forward store;
  email's over-the-air path exits via **UUCP/Postfix**.
- **Voice** is not a separate service: it is the radio's audio channel
  (WebRTC signaling gated behind `ENABLE_WEBRTC=false`).
- **Store** is SQLite WAL today, PostgreSQL via `DatabaseAdapter` later
  (ADR-001).

## Rendering

GitHub renders this diagram natively in `.md`. For the GitHub Pages hub, add
`mermaid.js`, or render to SVG with `mermaid-cli` — matching the existing
`architecture.svg` convention in `tech_docs/api-redesign/`.
