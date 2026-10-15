# HERMES Redesign — Complete Architecture

2026-10-09 · draft POC — structure only

The complete target architecture as one diagram. **Solid arrows** are
request/command flows; **dotted arrows** are event pushes (radio/modem →
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

    subgraph Backend["hermes-radio-daemon — the station backend (includes Mercury)"]
        GW["gateway — REST /api/v2 + WS hermes.v1 (/api/v2/ws)"]
        Auth["auth — sessions + roles"]
        Radio["radio (in-process)"]
        Modem["mercury (HF modem, in-process)"]
        Messaging["messaging (messages + stations)"]
        Email["email (UUCP/Postfix/Dovecot ties)"]
        Geo["geolocation"]
        System["system"]
        Bus["events — in-process bus"]
        Store[("store")]
    end

    HF["HF transceiver (sBitx v3 / IC-7100)"]:::ext
    UUCP["UUCP / Postfix / Dovecot — store-and-forward email"]:::ext

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
    N -->|WS hermes.v1| GW

    GW --> Auth
    GW --> Radio
    GW --> Messaging
    GW --> Geo
    GW --> System

    Radio --> HF
    Modem --> HF
    Messaging --> UUCP
    Email --> UUCP

    Radio -.->|telemetry / spectrum| Bus
    Modem -.->|link / transfer| Bus
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
- **radio and Mercury run in-process** inside hermes-radio-daemon (D-03, D-05);
  there is no WebSocket bridge or cgo seam.
- **`messaging`** spans chat and email — the same store-and-forward store;
  email's over-the-air path exits via **UUCP/Postfix**.
- **Voice** is not a separate service: it is the radio's audio channel
  (WebRTC signaling gated behind `ENABLE_WEBRTC=false`).
- **Store** is the database engine; the choice between MariaDB and SQLite is
  open under D-01.

## Rendering

GitHub renders this diagram natively in `.md`. For the GitHub Pages hub, add
`mermaid.js`, or render to SVG with `mermaid-cli` — matching the existing
`architecture.svg` convention in `tech_docs/api-redesign/`.
