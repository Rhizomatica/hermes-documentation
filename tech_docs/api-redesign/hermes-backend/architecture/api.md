# HERMES REST API

**Project**: hermes-backend  
**Status**: Architecture Design — Adapted for sBitx v2 (Raspberry Pi 4)  
**Based on**: [hermes-backend](https://github.com/Rhizomatica/hermes-backend) architecture

---

## 1. Overview

The HERMES REST API is the primary synchronous interface of the HERMES ecosystem. It exposes all HTTP endpoints consumed by the Web UI, mobile clients, CLI tools, and third-party integrations while coordinating with the Radio Daemon and the messaging services.

Built with **Fastify v5**, the API focuses on performance, schema validation, and a clean separation between transport and business logic. The entire stack runs in a **single Node.js process** with **SQLite (WAL mode)** as the only external resource — optimized for Raspberry Pi 4 field deployments with 4 GB RAM.

### Responsibilities

| Domain | Scope |
|--------|-------|
| **Authentication & Authorization** | User login, session management, JWT tokens, RBAC, permission validation |
| **Radio Management** | Radio control, configuration, diagnostics, frequency management, PTT, TX/RX state |
| **Messaging** | Conversation management, message CRUD, delivery tracking, attachments, broadcast, reactions |
| **User & Station Management** | Users, stations, devices, permissions, device registration |
| **System Management** | Initial setup (Quiz), configuration, health endpoints, clock sync, metrics, logs |
| **Geolocation** | GPS position, station location, position history |

---

### Internationalization

All API error responses are localized based on the user's language preference. The API supports three languages: English (`en`), Spanish (`es`), and Portuguese Brazil (`pt-BR`).

**Locale resolution order:**

1. User preference (`users.locale` in database, cached in JWT `locale` claim)
2. `Accept-Language` HTTP header (e.g., `es-MX, es;q=0.9, en;q=0.8`)
3. Fallback: `en`

**Usage:**

```http
GET /api/v1/conversations HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept-Language: es-MX, es;q=0.9
```

**Localized error response (RFC 7807):**

```json
{
  "type": "https://hermes.example.com/errors/forbidden",
  "title": "Forbidden",
  "status": 403,
  "code": "FORBIDDEN",
  "message": "No tiene permisos suficientes para esta operación.",
  "requestId": "req-uuid"
}
```

> **Note**: The `title` field stays in English (RFC 7807 convention). The `code` field is a machine-readable identifier (never translated). Only `message` and `details[].message` are localized.

**Changing language**: Users update their preference via `PATCH /users/me` with `{ "locale": "es" }`. This invalidates existing JWT tokens (old tokens carry the old locale) — the client must re-authenticate.

See [docs/development/i18n.md](../development/i18n.md) for the full internationalization strategy.

---

## 2. Architecture & Design Principles

### Technology Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Runtime | Node.js 20 LTS | Single process, `--max-old-space-size=384` |
| Language | TypeScript 5.x (strict) | |
| HTTP Framework | Fastify v5 | |
| Validation | JSON Schema (AJV) at request boundary | |
| API Documentation | OpenAPI 3.1 auto-generated via `@fastify/swagger` | |
| ORM | Drizzle ORM (SQLite adapter) | |
| Database | SQLite (WAL mode) | Single-file, zero daemon, ~2–5 MB memory |
| Event Bus | In-process EventEmitter | No external broker |
| Job Queues | In-memory priority queue + SQLite backing store | Jobs survive process restart |
| Auth | JWT RS256 + RBAC | |
| Session Store | SQLite (`user_sessions` table) | Token hashes, never plaintext |
| Rate Limiting | In-memory counters | Resets on process restart (acceptable for single-station) |
| Logging | Pino (structured JSON) | |

### What Was Removed from the Original Architecture

| Removed | Replacement |
|---------|-------------|
| PostgreSQL 17 + TimescaleDB | SQLite (WAL mode) — see [database.md](../architecture/database.md) |
| Redis 7 (Pub/Sub, BullMQ, sessions) | In-process EventEmitter + in-memory queues + SQLite sessions |
| mediasoup SFU + coturn | Gated behind `ENABLE_WEBRTC=false` config flag (default off on Pi 4) |
| OpenTelemetry tracing | Disabled by default; can be enabled for debugging |

### Component Replacement Rationale

**Database**: SQLite (WAL mode) was chosen over PostgreSQL for single-station sBitx v2 deployments. PostgreSQL's 300–800 MB RAM footprint and daemon process are incompatible with the Pi 4's 4 GB budget. The `DatabaseAdapter` interface allows migration to PostgreSQL for larger multi-station server deployments (Phase 4 federation) — Drizzle ORM's adapter pattern makes this a configuration switch, not a code rewrite.

**Event Bus**: An in-process EventEmitter replaces Redis Pub/Sub. In a single Node.js process, there is no cross-process fan-out to manage. If the EventEmitter were unavailable (should never happen in normal operation — it's in the same process), the system falls back to direct service calls. This is a non-issue for a modular monolith.

**Job Queues**: In-memory priority queue with SQLite backing store (`jobs` table) replaces BullMQ/Redis. Jobs survive process restarts via the backing store.

**Session Store**: SQLite `user_sessions` table replaces Redis. Token hashes are stored directly in the database; no external cache dependency.

**Rate Limiting**: In-memory counters replace Redis counters. Counters reset on a process restart — an acceptable tradeoff for single-station deployments. The rate limiter interface supports swapping to Redis or database-backed counters for multi-station deployments.

**WebRTC / Audio Streaming**: mediasoup SFU (200–400 MB RAM) and coturn are removed. On sBitx v2, the radio itself is the audio channel. Peer-to-peer WebRTC signaling is gated behind `ENABLE_WEBRTC=false` (default off). Browser audio for LAN testing is a future consideration (browser capture → WebSocket → ALSA playback, no SFU needed).

### Runtime Decision

Node.js 20 LTS with TypeScript was chosen over Go and Python because:

- Shared language with the Web UI frontend
- Faster development velocity
- Strong Fastify v5 ecosystem with first-class TypeScript support
- Single-process concurrency via the event loop — no multi-process overhead on Pi 4
- `--max-old-space-size=384` keeps V8 heap within memory budget

### Radio Daemon Integration

The API must remain fully compatible with the upstream Radio Daemon:

- [hermes-radio-daemon](https://github.com/Rhizomatica/hermes-radio-daemon) — Radio control, state, metrics, PTT, TX/RX state, WebSocket event consumption
- [hermes-api](https://github.com/Rhizomatica/hermes-api) — Legacy API compatibility reference

**Source of truth**: The Radio Daemon provides runtime state via WebSocket; the API persists desired configuration in the `radio_profiles` table. On startup, the API reconciles database state with daemon state. When the daemon is unreachable, the API serves last-known state from the database with `radio.connected: false`.

### Design Decisions

- **Thin Controllers**: Route handlers delegate to domain services — no business logic in controllers
- **Repository Pattern**: Data access abstracted behind typed repositories with `DatabaseAdapter` interface (SQLite implementation for Pi 4; PostgreSQL implementation available for server deployments)
- **Dependency Injection**: Services composed via constructor injection
- **Versioned Endpoints**: All routes under `/api/v1/`
- **JSON Schema Everywhere**: Request validation, response validation, shared DTOs — with `maxLength` constraints on all string fields
- **Full TypeScript**: End-to-end type safety from route schema to database row

### Project Structure

```
src/api/
├── v1/
│   ├── auth/              # POST /auth/login, /auth/refresh, /auth/logout
│   ├── radio/             # GET/POST radio state, frequency, mode, PTT
│   ├── conversations/     # CRUD conversations, participants
│   ├── messages/          # CRUD messages, delivery, reactions
│   ├── users/             # CRUD users, roles
│   ├── devices/           # Device registration, push tokens
│   ├── system/            # Setup wizard, config, health, clock sync, diagnostics
│   ├── geolocation/       # GPS readings, position history
│   ├── frequencies/       # Frequency presets
│   ├── schedules/         # Connection schedules (UUCP/call)
│   └── attachments/       # File upload, download, processing
└── openapi/               # OpenAPI/Swagger spec generation
```

---

## 3. Authentication & Authorization

### JWT Token Architecture

```
Access Token:  JWT RS256, 15-minute expiry
                Payload: { sub (userId), callsign, role, sessionId, iat, exp }

Refresh Token: 30-day expiry, opaque random string
               SHA-256 hash stored in SQLite user_sessions table (never plaintext)
```

### Login Flow

```
POST /api/v1/auth/login
  Body: { callsign, password }
  
  → Lookup user by callsign (constant-time)
  → Verify password with bcrypt (cost factor ≥ 12)
  → Generate access token (JWT RS256, 15 min)
  → Generate refresh token (crypto.randomBytes(48))
  → Store SHA-256(refreshToken) in user_sessions (SQLite)
  → Return: { accessToken, refreshToken, expiresIn: 900 }
```

### Token Refresh

```
POST /api/v1/auth/refresh
  Body: { refreshToken }
  
  → Look up SHA-256(refreshToken) in user_sessions table (SQLite)
  → Verify session not expired, not revoked
  → Revoke current refresh token (rotation)
  → Issue new access + refresh token pair
  → Detect token reuse → alert + increment counter
```

### RBAC Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| `admin` | Full system access | All operations, user management, system config, audit logs |
| `operator` | Radio operator | All radio controls, messaging, schedule management |
| `user` | Standard user | Messaging, read radio status, view schedules |
| `readonly` | Observer | Read-only access to status and messages |

### Permission Matrix

| Operation | admin | operator | user | readonly |
|-----------|:-----:|:--------:|:----:|:--------:|
| Send messages | ✓ | ✓ | ✓ | — |
| Delete own messages | ✓ | ✓ | ✓ | — |
| Delete any message | ✓ | — | — | — |
| Read conversations | ✓ | ✓ | ✓ | ✓ |
| Set radio frequency | ✓ | ✓ | — | — |
| Set PTT | ✓ | ✓ | — | — |
| View radio telemetry | ✓ | ✓ | ✓ | ✓ |
| Manage users | ✓ | — | — | — |
| Manage frequencies | ✓ | ✓ | — | — |
| Create schedules | ✓ | ✓ | — | — |
| Modify system config | ✓ | — | — | — |
| Reboot/shutdown | ✓ | — | — | — |
| Access audit logs | ✓ | — | — | — |

### Middleware Chain

```
Request
  → CORS (configured allowlist)  
  → Helmet (security headers)
  → Rate Limiter (in-memory, per-IP / per-user)
  → JWT Verifier (extract + validate access token)
  → RBAC Guard (check role against required roles)
  → Schema Validator (AJV request + response validation)
  → Controller
  → Service
  → Repository
```

---

## 4. REST API Endpoints

### 4.1 Authentication — `/api/v1/auth`

| Method | Path | Description | Auth | Roles |
|--------|------|-------------|:----:|-------|
| `POST` | `/auth/login` | Login with callsign + password | No | — |
| `POST` | `/auth/refresh` | Refresh access token | No | — |
| `POST` | `/auth/logout` | Revoke current session | Yes | All |
| `GET` | `/auth/sessions` | List active sessions | Yes | All |
| `DELETE` | `/auth/sessions/:id` | Revoke a specific session | Yes | All |

**Request/Response examples:**

```json
// POST /api/v1/auth/login — Request
{
  "callsign": "XA1ABC",
  "password": "secure-password"
}

// POST /api/v1/auth/login — Response 200
{
  "accessToken": "eyJhbGciOiJSUzI1NiIs...",
  "refreshToken": "8f3a1b2c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f",
  "expiresIn": 900
}

// POST /api/v1/auth/refresh — Request
{
  "refreshToken": "8f3a1b2c4d5e..."
}

// POST /api/v1/auth/refresh — Response 200
{
  "accessToken": "eyJhbGciOiJSUzI1NiIs...",
  "refreshToken": "a1b2c3d4e5f6...",
  "expiresIn": 900
}
```

**Rate limit**: `POST /auth/login` — 5 requests per 15 minutes per IP.

---

### 4.2 Radio Management — `/api/v1/radio`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/radio/status` | Full radio status (telemetry snapshot) | user+ |
| `GET` | `/radio/profiles` | List all radio profiles | user+ |
| `GET` | `/radio/profiles/:idx` | Get specific profile | user+ |
| `POST` | `/radio/profiles/:idx/frequency` | Set frequency (Hz) | operator+ |
| `POST` | `/radio/profiles/:idx/mode` | Set operating mode | operator+ |
| `POST` | `/radio/profiles/:idx/volume` | Set volume (0–100) | operator+ |
| `POST` | `/radio/active-profile` | Switch active profile | operator+ |
| `POST` | `/radio/ptt` | Push-to-talk (activate/deactivate) | operator+ |
| `POST` | `/radio/stop` | Stop transmission | operator+ |
| `POST` | `/radio/protection/reset` | Reset SWR protection | operator+ |
| `GET` | `/radio/telemetry` | Historical telemetry (time range) | user+ |
| `GET` | `/radio/sessions` | List radio sessions | user+ |

**Key request/response examples:**

```json
// GET /api/v1/radio/status — Response 200
{
  "radio": {
    "frequencyHz": 14200000,
    "mode": "USB",
    "tx": false,
    "rx": true,
    "snr": 15,
    "bitrate": 1200,
    "bytesTransmitted": 1048576,
    "bytesReceived": 524288,
    "powerLevel": 10
  },
  "system": {
    "ok": true,
    "connected": true,
    "protection": false,
    "profileActiveIdx": 0,
    "timeoutCounter": 0,
    "digitalVoice": false
  },
  "profiles": [
    {
      "idx": 0,
      "frequencyHz": 14200000,
      "mode": "USB",
      "volume": 50,
      "digitalVoice": false
    }
  ]
}

// POST /api/v1/radio/profiles/0/frequency — Request
{
  "frequencyHz": 14250000
}

// POST /api/v1/radio/ptt — Request
{
  "active": true,
  "profileIdx": 0
}
```

**Rate limit**: 60 radio command requests per minute per user.

---

### 4.3 Conversations — `/api/v1/conversations`

Conversations replace the legacy inbox/outbox email model with a chat-native architecture.

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/conversations` | List user's conversations (paginated) | user+ |
| `POST` | `/conversations` | Create a new conversation | user+ |
| `GET` | `/conversations/:id` | Get conversation details | participant |
| `PATCH` | `/conversations/:id` | Update conversation (title, metadata) | participant |
| `POST` | `/conversations/:id/archive` | Archive conversation | participant |
| `POST` | `/conversations/:id/unarchive` | Unarchive conversation | participant |
| `GET` | `/conversations/:id/participants` | List participants | participant |
| `POST` | `/conversations/:id/participants` | Add participants | owner/admin |
| `DELETE` | `/conversations/:id/participants/:userId` | Remove participant | owner/admin |
| `POST` | `/conversations/:id/read` | Mark conversation as read up to message | participant |

**Conversation types:**

| Type | Description | Max Participants |
|------|-------------|:---:|
| `direct` | 1-to-1 chat | 2 |
| `group` | N-to-N group chat | 50 |
| `broadcast` | 1-to-many (announcements, no replies) | 200 |
| `radio` | Linked to a radio channel/frequency | Varies |

**Request/response examples:**

```json
// POST /api/v1/conversations — Request (direct)
{
  "type": "direct",
  "participantIds": ["uuid-of-other-user"]
}

// POST /api/v1/conversations — Request (group)
{
  "type": "group",
  "title": "Coordination Group",
  "participantIds": ["uuid-1", "uuid-2", "uuid-3"]
}

// POST /api/v1/conversations — Request (broadcast)
{
  "type": "broadcast",
  "title": "Emergency Alert",
  "recipientStationIds": ["uuid-station-1", "uuid-station-2"]
}

// GET /api/v1/conversations — Response 200
{
  "data": [
    {
      "id": "uuid",
      "type": "direct",
      "title": null,
      "lastActivityAt": "2026-07-17T12:00:00Z",
      "lastMessage": {
        "contentPreview": "Radio check, over.",
        "senderCallsign": "XA1XYZ",
        "createdAt": "2026-07-17T12:00:00Z"
      },
      "unreadCount": 3,
      "participants": [
        { "userId": "uuid", "callsign": "XA1ABC", "role": "member" },
        { "userId": "uuid", "callsign": "XA1XYZ", "role": "member" }
      ]
    }
  ],
  "pagination": {
    "total": 42,
    "page": 1,
    "pageSize": 50,
    "hasMore": false
  }
}
```

**Note**: The conversation list query returns `contentPreview` (first 200 characters) instead of full `content` to prevent large message bodies from bloating the list response.

---

### 4.4 Messages — `/api/v1/conversations/:conversationId/messages`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/conversations/:id/messages` | List messages (paginated, cursor-based) | participant |
| `POST` | `/conversations/:id/messages` | Send a message | participant |
| `PATCH` | `/conversations/:id/messages/:msgId` | Edit message content | sender |
| `DELETE` | `/conversations/:id/messages/:msgId` | Soft-delete message | sender |
| `POST` | `/conversations/:id/messages/:msgId/reactions` | Add emoji reaction | participant |
| `DELETE` | `/conversations/:id/messages/:msgId/reactions/:emoji` | Remove reaction | participant |

**Message content constraints:**

| Field | Constraint | Rationale |
|-------|------------|-----------|
| `content` | `maxLength: 65536` (64 KB) | More than sufficient for HF radio text messaging; prevents memory exhaustion on Pi 4 |
| `subject` | `maxLength: 256` | Email interoperability |
| `reactions` per message | Maximum 20 unique emoji | Prevent spam |
| Messages per request | `pageSize` max 50 | Pagination safety |

**Message status lifecycle:**

```
draft → sending → sent → (delivered → read, per recipient)
                       ↘ failed
```

**Request/response examples:**

```json
// POST /api/v1/conversations/:id/messages — Request
{
  "content": "Radio check, over.",
  "contentType": "text",
  "clientMessageId": "uuid-client-generated",   // Idempotency key
  "replyToMessageId": "uuid-of-parent-message"   // Optional: flat threading
}

// POST /api/v1/conversations/:id/messages — Response 201
{
  "id": "uuid",
  "conversationId": "uuid",
  "senderId": "uuid",
  "senderCallsign": "XA1ABC",
  "content": "Radio check, over.",
  "contentType": "text",
  "replyToMessageId": null,
  "status": "sending",
  "createdAt": "2026-07-17T12:00:00Z"
}

// GET /api/v1/conversations/:id/messages — Response 200
{
  "data": [
    {
      "id": "uuid",
      "senderId": "uuid",
      "senderCallsign": "XA1ABC",
      "content": "Radio check, over.",
      "contentType": "text",
      "replyToMessageId": null,
      "status": "sent",
      "editedAt": null,
      "reactions": [{ "emoji": "👍", "count": 2, "reactedByMe": true }],
      "delivery": {
        "total": 3,
        "delivered": 2,
        "read": 1
      },
      "createdAt": "2026-07-17T12:00:00Z"
    }
  ],
  "pagination": {
    "cursor": "base64-encoded-cursor",
    "pageSize": 50,
    "hasMore": true
  }
}
```

**Idempotency**: The `clientMessageId` field is a client-generated UUID. The server deduplicates on this key — if a client resends the same request (network failure, timeout), the server returns the already-created message instead of creating a duplicate.

---

### 4.5 Message Delivery — `/api/v1/messages/:messageId/delivery`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/messages/:id/delivery` | Get delivery status per recipient | sender |
| `POST` | `/messages/:id/acknowledge` | Acknowledge receipt (client) | recipient |

Delivery tracking is **per-recipient, per-channel**:

```
message_deliveries:
  message_id=X, recipient_id=UserA, channel=websocket, status=delivered
  message_id=X, recipient_id=UserA, channel=radio,    status=pending
  message_id=X, recipient_id=UserB, channel=websocket, status=read
```

**Delivery channels:**

| Channel | Trigger | Delivery Confirmation |
|---------|---------|----------------------|
| `websocket` | Recipient online (WebSocket connected) | `MESSAGE_ACK` from client |
| `push` | Recipient has push token (mobile) | FCM/APNs delivery receipt |
| `radio` | Target station reachable via HF | UUCP acknowledgment |
| `email` | Recipient has email configured | SMTP delivery report |

---

### 4.6 Users — `/api/v1/users`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/users` | List users (paginated) | admin |
| `POST` | `/users` | Create user | admin |
| `GET` | `/users/:id` | Get user details | admin, self |
| `PATCH` | `/users/:id` | Update user | admin, self |
| `DELETE` | `/users/:id` | Soft-delete user | admin |
| `GET` | `/users/me` | Get current user profile | All |

**User roles**: `admin`, `operator`, `user`, `readonly`

**User statuses**: `active`, `suspended`, `pending`

```json
// POST /api/v1/users — Request
{
  "callsign": "XA1DEF",
  "displayName": "Station Delta",
  "email": "delta@example.com",        // Optional: for email interop
  "password": "secure-password",
  "role": "user"
}

// GET /api/v1/users/me — Response 200
{
  "id": "uuid",
  "callsign": "XA1ABC",
  "displayName": "Base Station Alpha",
  "email": "alpha@example.com",
  "role": "operator",
  "status": "active",
  "lastSeenAt": "2026-07-17T12:00:00Z",
  "createdAt": "2026-01-01T00:00:00Z"
}
```

---

### 4.7 Devices — `/api/v1/devices`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/devices` | List user's devices | All |
| `POST` | `/devices` | Register a device | All |
| `PATCH` | `/devices/:id` | Update device (e.g., push token) | owner |
| `DELETE` | `/devices/:id` | Remove device | owner |

**Device types**: `mobile`, `desktop`, `station`, `browser`

```json
// POST /api/v1/devices — Request
{
  "deviceName": "iPhone 15",
  "deviceType": "mobile",
  "platform": "ios",
  "pushToken": "fcm-token-here"      // Optional
}
```

---

### 4.8 Attachments — `/api/v1/attachments`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `POST` | `/attachments` | Upload file (multipart/form-data) | user+ |
| `GET` | `/attachments/:id` | Get attachment metadata | participant |
| `GET` | `/attachments/:id/download` | Download file (signed URL) | participant |
| `DELETE` | `/attachments/:id` | Delete attachment | uploader |
| `POST` | `/attachments/:id/link` | Link attachment to a message | participant |

**Security controls:**
- MIME type validated from file content bytes, not from `Content-Type` header
- Maximum file size enforced at streaming level (default: 50 MB)
- Storage path uses server-generated UUID — client filename stored only as `original_filename`
- Downloads served via signed time-limited URLs (1-hour expiry; see note below for HF radio store-and-forward)
- Attachment access requires conversation membership
- SHA-256 checksum enables deduplication

**HF radio store-and-forward consideration**: For attachments sent over radio (which may arrive days after the original upload), the download flow uses a separate `attachment_token` with a 30-day expiry issued at message creation time. This token is embedded in the radio-transmitted message envelope and can be redeemed when the attachment eventually arrives.

**Attachment statuses**: `pending` → `processing` → `ready` | `failed` | `expired`

```json
// POST /api/v1/attachments (multipart/form-data) — Response 201
{
  "id": "uuid",
  "filename": "a1b2c3d4-image.jpg",
  "originalFilename": "IMG_2026.jpg",
  "mimeType": "image/jpeg",
  "sizeBytes": 2048576,
  "status": "processing",
  "checksum": "sha256-hex-string",
  "createdAt": "2026-07-17T12:00:00Z"
}
```

---

### 4.9 Frequencies — `/api/v1/frequencies`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/frequencies` | List frequency presets | user+ |
| `POST` | `/frequencies` | Create frequency preset | operator+ |
| `PATCH` | `/frequencies/:id` | Update frequency preset | operator+ |
| `DELETE` | `/frequencies/:id` | Delete frequency preset | operator+ |

```json
// POST /api/v1/frequencies — Request
{
  "alias": "LocalNet-20m",
  "frequencyHz": 14200000,
  "mode": "USB",
  "description": "Local 20m net frequency",
  "isGateway": false,
  "region": "Americas"
}
```

---

### 4.10 Connection Schedules — `/api/v1/schedules`

Replaces the legacy `/caller` endpoint. Represents UUCP/radio call schedules for automatic station connections.

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/schedules` | List schedules | user+ |
| `POST` | `/schedules` | Create schedule | operator+ |
| `PATCH` | `/schedules/:id` | Update schedule | operator+ |
| `DELETE` | `/schedules/:id` | Delete schedule | operator+ |
| `POST` | `/schedules/:id/cancel` | Cancel a scheduled connection | operator+ |

```json
// POST /api/v1/schedules — Request
{
  "targetCallsign": "XA1XYZ",
  "frequencyId": "uuid-of-frequency",
  "scheduledAt": "2026-07-18T14:00:00Z",
  "recurrence": {
    "freq": "DAILY",
    "byhour": [14, 18]
  }
}

// Response 201
{
  "id": "uuid",
  "targetCallsign": "XA1XYZ",
  "frequencyId": "uuid",
  "scheduledAt": "2026-07-18T14:00:00Z",
  "recurrence": { "freq": "DAILY", "byhour": [14, 18] },
  "status": "pending",
  "nextRunAt": "2026-07-18T14:00:00Z",
  "createdAt": "2026-07-17T12:00:00Z"
}
```

---

### 4.11 Geolocation — `/api/v1/geolocation`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/geolocation/current` | Get latest GPS reading for station | user+ |
| `GET` | `/geolocation/history` | Query position history (time range) | user+ |
| `POST` | `/geolocation` | Report GPS position | user+ |

```json
// GET /api/v1/geolocation/current — Response 200
{
  "stationId": "uuid",
  "time": "2026-07-17T12:00:00Z",
  "latitude": 19.4326,
  "longitude": -99.1332,
  "altitudeM": 2250.0,
  "accuracyM": 5.0,
  "speedKmh": 0.0,
  "headingDeg": 0.0,
  "source": "gps"
}

// POST /api/v1/geolocation — Request
{
  "latitude": 19.4326,
  "longitude": -99.1332,
  "altitudeM": 2250.0,
  "accuracyM": 5.0
}
```

---

### 4.12 System — `/api/v1/system`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/system/config` | Get system configuration | operator+ |
| `PATCH` | `/system/config` | Update system configuration | admin |
| `POST` | `/system/reboot` | Reboot the station | admin |
| `POST` | `/system/shutdown` | Shutdown the station | admin |
| `POST` | `/system/erase-sdcard` | Erase SD card | admin |
| `GET` | `/system/clock` | Get clock sync status (synced, source, last sync time) | user+ |
| `POST` | `/system/clock/sync` | Manually set system clock (air-gapped stations) | admin |

---

### 4.13 Initial Setup (Quiz) — `/api/v1/setup`

Drives the first-time setup wizard for new stations.

| Method | Path | Description | Auth |
|--------|------|-------------|:----:|
| `GET` | `/setup/status` | Check if setup has been completed | No |
| `POST` | `/setup` | Submit setup configuration | No (one-time) |

```json
// POST /api/v1/setup — Request
{
  "country": "MX",
  "callsign": "XA1ABC",
  "stationName": "Base Station Alpha",
  "radioProfile": {
    "frequencyHz": 14200000,
    "mode": "USB"
  },
  "installedApps": ["hermes-chat", "hermes-gps"],
  "adminUser": {
    "callsign": "XA1ABC",
    "displayName": "Station Operator",
    "password": "secure-admin-password"
  },
  "networkSettings": {
    "hostname": "hermes-alpha",
    "dhcp": true
  }
}
```

---

### 4.14 Installed Applications — `/api/v1/apps`

| Method | Path | Description | Roles |
|--------|------|-------------|-------|
| `GET` | `/apps` | List installed applications | user+ |
| `POST` | `/apps/install` | Install an application | admin |
| `POST` | `/apps/remove` | Remove an application | admin |
| `POST` | `/apps/update` | Update an application | admin |

---

### 4.15 Health & Metrics

| Method | Path | Description | Auth |
|--------|------|-------------|:----:|
| `GET` | `/health` | Health check (liveness/readiness) | No |
| `GET` | `/health/deep` | Deep health check (runs actual queries) | No |
| `GET` | `/version` | API version and build info | No |
| `GET` | `/metrics` | Prometheus metrics endpoint | No |

```json
// GET /health — Response 200
{
  "status": "ok",
  "uptime": 86400,
  "checks": {
    "database": "ok",
    "radio": "connected",
    "clock_synced": true
  },
  "version": "1.0.0",
  "timestamp": "2026-07-17T12:00:00Z"
}

// GET /health — Response 200 (degraded radio)
{
  "status": "degraded",
  "uptime": 86400,
  "checks": {
    "database": "ok",
    "radio": "disconnected",
    "clock_synced": false
  },
  "version": "1.0.0",
  "timestamp": "2026-07-17T12:00:00Z"
}
```

**Health status levels:**

| Status | Meaning |
|--------|---------|
| `ok` | All critical services operational |
| `degraded` | One or more services in fallback/degraded mode; API still functional |
| `unhealthy` | Critical service unavailable; API may return 503 |

**`/health/deep`** runs actual queries (SQLite `SELECT 1`, radio daemon ping) rather than just checking connection state. Returns timing information for each check.

```json
// GET /health/deep — Response 200
{
  "status": "ok",
  "checks": {
    "database": { "status": "ok", "latencyMs": 1.2 },
    "radio": { "status": "connected", "latencyMs": 45 },
    "clock_synced": { "status": "ok", "source": "gps", "lastSyncAt": "2026-07-17T12:00:00Z" }
  }
}
```

---

## 5. WebSocket API

The WebSocket gateway provides real-time event streaming, complementing the REST API. Events are delivered via the **in-process EventEmitter** — no external Pub/Sub broker is needed on a single Pi 4.

**Connection**: `wss://host/ws` (subprotocol: `hermes-v1`)

### Connection Lifecycle

```
Client → TCP/TLS handshake → WebSocket Upgrade
  ↓
Client → AUTHENTICATE { token, deviceId }
Server → AUTHENTICATED { userId, callsign, role, sessionId, serverTime }
  ↓
Client → SUBSCRIBE { topics: ["radio.telemetry", "conversation.<id>"] }
Server → SUBSCRIBED { grantedTopics: [...] }
  ↓
[Normal operation: server pushes events to subscribed clients]
  ↓
[Heartbeat: PING/PONG every 30 seconds]
```

**Authentication timeout**: 10 seconds — connections that don't authenticate are dropped with code `4001`.

**`serverTime`**: The `AUTHENTICATED` response includes `serverTime` (ISO 8601 UTC) so clients can synchronize their clocks. On air-gapped stations, this time may be from GPS or a manually-set clock — check `clock_synced` in the health endpoint.

### Event Topics

| Topic | Description | Required Role |
|-------|-------------|:---:|
| `radio.telemetry` | Periodic radio state snapshots (~1s) | user |
| `radio.state` | Significant radio state changes | user |
| `radio.commands` | Radio command results | operator |
| `message.new` | New messages in subscribed conversations | user |
| `conversation.<id>` | All events for a specific conversation | participant |
| `conversation.<id>.typing` | Typing indicators | participant |
| `presence.<userId>` | User online/offline/away | user |
| `sync.<deviceId>` | Sync events for a device | self |
| `system` | System-level notifications | user |
| `geolocation` | Real-time GPS updates | user |
| `admin.*` | Administrative events | admin |

> **Note**: The `webrtc.<sessionId>` topic is gated behind the `ENABLE_WEBRTC` configuration flag (default `false` on sBitx v2). WebRTC audio streaming is not required for field-deployed sBitx stations where the radio itself is the audio channel.

### Key Event Types (Server → Client)

| Type | Description |
|------|-------------|
| `RADIO_TELEMETRY` | Full radio state snapshot |
| `RADIO_STATE_CHANGE` | PTT, connection, protection change |
| `MESSAGE_NEW` | New message in a conversation |
| `MESSAGE_UPDATED` | Message content edited |
| `MESSAGE_DELETED` | Message soft-deleted |
| `MESSAGE_DELIVERED` | Delivery receipt |
| `MESSAGE_READ` | Read receipt |
| `REACTION_ADDED` / `REACTION_REMOVED` | Emoji reaction change |
| `TYPING_START` / `TYPING_STOP` | Typing indicators |
| `PRESENCE_UPDATE` | User presence change |
| `SYNC_DELTA` | Batch of missed events (reconnect) |
| `SYNC_COMPLETE` | Reconnection sync complete |
| `SYNC_SUMMARY` | Catch-up summary (when missed events > 500) |
| `SYSTEM_NOTIFICATION` | System-level notification |
| `CLOCK_SYNCED` | Clock has been synchronized (GPS/manual) |

### Message Envelope

All WebSocket messages use this envelope:

```typescript
interface WsEnvelope {
  type: string        // Event type identifier
  requestId?: string  // Client correlation ID (echoed in responses)
  payload: unknown    // Type-specific payload
  timestamp: string   // ISO 8601 UTC
  version: number     // Protocol version (always 1)
}
```

### Example: Radio Telemetry Event

```json
{
  "type": "RADIO_TELEMETRY",
  "payload": {
    "stationId": "uuid",
    "timestamp": "2026-07-17T12:00:01.000Z",
    "radio": {
      "frequencyHz": 14200000,
      "mode": "USB",
      "tx": false,
      "rx": true,
      "snr": 15,
      "bitrate": 1200,
      "bytesTransmitted": 1048576,
      "bytesReceived": 524288,
      "powerLevel": 10
    },
    "system": {
      "ok": true,
      "connected": true,
      "protection": false,
      "profileActiveIdx": 0,
      "timeoutCounter": 0
    }
  },
  "timestamp": "2026-07-17T12:00:01.000Z",
  "version": 1
}
```

### Offline Reconnection & Sync

When a client reconnects after being offline:

```
Client → AUTHENTICATE { token, deviceId, resumeSessionId: "prev-session-id" }
Server → AUTHENTICATED
Client → SYNC_REQUEST { cursors: { messages: 1234, reactions: 567 } }
Server → SYNC_DELTA { batchId, batchIndex: 1, totalBatches: 3, events: [...] }
Server → SYNC_DELTA { batchId, batchIndex: 2, totalBatches: 3, events: [...] }
Server → SYNC_DELTA { batchId, batchIndex: 3, totalBatches: 3, events: [...] }
Server → SYNC_COMPLETE { cursors: { messages: 1250, reactions: 570 }, missedEvents: 19 }
```

**Sync catch-up threshold**: If more than 500 events accumulated while offline, the server sends a `SYNC_SUMMARY` with conversation-level unread counts instead of individual `SYNC_DELTA` frames. The client can then lazy-load conversations individually. This prevents WebSocket saturation on reconnect after long offline periods.

### WebRTC Signaling (Conditional)

When `ENABLE_WEBRTC=true` (not default on sBitx v2), the following additional topic and event types are available:

**Additional topic**: `webrtc.<sessionId>` (participant)

**Additional event types**:
| Type | Description |
|------|-------------|
| `WEBRTC_OFFER` | SDP offer |
| `WEBRTC_ANSWER` | SDP answer |
| `WEBRTC_ICE_CANDIDATE` | ICE candidate exchange |

WebRTC on sBitx v2 uses **peer-to-peer connections** (no mediasoup SFU) to minimize memory overhead. This is suitable for 1–2 LAN clients.

---

## 6. Security

### Transport Security

- **TLS**: Minimum TLS 1.2 required; TLS 1.3 preferred
- **HSTS**: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **CORS**: Configured allowlist; credentials enabled
- **Helmet**: Security headers enforced (CSP, XSS filter, no-sniff, referrer policy)

### Input Validation

- **JSON Schema**: All request bodies validated via AJV before reaching controllers
- **Unknown fields stripped**: `additionalProperties: false` globally
- **`maxLength` constraints**: All string fields have explicit maximum lengths (e.g., message `content`: 64 KB, `callsign`: 20 chars, `displayName`: 100 chars)
- **WebSocket payloads**: Validated against typed schemas at gateway boundary
- **CLI injection prevention**: All HAL commands use `execFile` with argument arrays — no shell interpolation

### SQL Injection Prevention

- All database queries use Drizzle ORM parameterized queries
- Raw SQL restricted to migration files only

### Audit Logging

All significant actions are written to the `audit_logs` table:

| Action | Description |
|--------|-------------|
| `auth.login` | Successful login |
| `auth.login_failed` | Failed login attempt |
| `auth.logout` | Session revocation |
| `user.created` / `user.updated` / `user.deleted` | User management |
| `user.role_changed` | Role escalation/demotion |
| `message.deleted` | Message deletion |
| `radio.frequency_changed` | Frequency modification |
| `radio.ptt_activated` | PTT enabled |
| `system.config_changed` | Configuration modification |
| `system.reboot` / `system.shutdown` | System operations |
| `system.clock_set` | Manual clock adjustment |
| `auth.unauthorized_access` | RBAC violation attempt |

---

## 7. Error Handling

All errors follow RFC 7807 Problem Detail format:

```json
{
  "type": "https://hermes.example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "code": "INVALID_PAYLOAD",
  "message": "Request body failed validation",
  "details": [
    {
      "field": "frequencyHz",
      "message": "Must be between 1000000 and 30000000"
    }
  ],
  "requestId": "req-uuid"
}
```

### Common Error Codes

| HTTP Status | Code | Description |
|:---:|------|-------------|
| 400 | `INVALID_PAYLOAD` | Request body failed schema validation |
| 400 | `CONTENT_TOO_LARGE` | Message content exceeds 64 KB limit |
| 401 | `UNAUTHENTICATED` | Missing or invalid access token |
| 401 | `TOKEN_EXPIRED` | Access token has expired |
| 403 | `FORBIDDEN` | Insufficient role for operation |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `CONFLICT` | Duplicate resource (e.g., direct conversation exists) |
| 422 | `BUSINESS_RULE` | Business logic constraint violated |
| 422 | `PARTICIPANT_LIMIT_EXCEEDED` | Conversation would exceed max participants |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Unexpected server error |
| 503 | `SERVICE_UNAVAILABLE` | SQLite or radio daemon unavailable |

---

## 8. Rate Limiting

| Endpoint | Limit | Implementation |
|----------|-------|---------------|
| `POST /auth/login` | 5 requests / 15 min per IP | In-memory counter |
| `POST /auth/refresh` | 20 requests / hour per user | In-memory counter |
| REST API (general) | 300 requests / min per user | In-memory sliding window |
| REST API (radio commands) | 60 requests / min per user | In-memory sliding window |
| File upload | 20 uploads / hour per user | In-memory counter |
| WebSocket messages | 60 messages / min per connection | In-memory counter |
| WebSocket `RADIO_COMMAND` | 10 / min per connection | In-memory counter |
| WebSocket `TYPING_START` | 1 per 2 sec per conversation | In-memory counter |

**Note**: Rate limiting uses in-memory counters (no Redis). A process restart resets all counters — an acceptable tradeoff for single-station Pi 4 deployments. For server/multi-station deployments, the rate limiter can be backed by the database or an external Redis instance via the same interface.

---

## 9. OpenAPI & Swagger

- OpenAPI 3.1 specification auto-generated from Fastify route schemas
- Swagger UI available at `/docs`
- JSON schema definitions shared between routes for consistency
- All request/response types defined as TypeScript types synchronized with JSON Schema

---

## 10. Legacy Compatibility

During migration from the legacy `hermes-api`:

- All existing REST endpoints preserved under `/api/v1/` with identical response formats
- The `sbitx_websocket.c` C daemon telemetry stream is bridged through the new WebSocket gateway
- UUCP / HMP message flows are preserved through the sync engine and transport adapters
- Legacy inbox/outbox queries are translated to conversation queries internally via compatibility shim
- **Scope of shim**: Read-only for message retrieval; write operations go through new conversation-based endpoints. Legacy endpoints preserved: `GET /messages/inbox`, `GET /messages/outbox`, `GET /messages/:id`. Write endpoints (`POST /messages/send`) are redirected to the new conversation API.

---

## 11. Resource Constraints & Limits

Enforced limits to protect the Raspberry Pi 4's 4 GB RAM:

| Resource | Limit | Enforcement |
|----------|-------|-------------|
| Message `content` | 64 KB (`maxLength: 65536`) | JSON Schema / AJV |
| Message `subject` | 256 chars | JSON Schema / AJV |
| `callsign` field | 20 chars | JSON Schema / AJV |
| `displayName` field | 100 chars | JSON Schema / AJV |
| Conversation participants (group) | 50 | Business logic |
| Conversation participants (broadcast) | 200 | Business logic |
| File upload size | 50 MB | Streaming parser |
| Messages per page | 50 | Query parameter validation |
| Sync delta batch size | 100 events | Sync engine |
| Sync catch-up threshold | 500 missed events → send `SYNC_SUMMARY` | Sync engine |
| WebSocket connections | 10 concurrent | Gateway |
| In-memory job queue depth | 1000 jobs | Job queue |
| V8 heap | 384 MB (`--max-old-space-size=384`) | Node.js flag |
| **Total estimated memory** | **~450–620 MB** | Well within 4 GB budget |

---

## 12. Design Decisions & Resolved Questions

During the architecture redesign for sBitx v2, the following design questions were evaluated and resolved:

### Messaging Model

| Model | Characteristics |
|-------|----------------|
| Delta Chat | Email as transport, conversations, offline-first, asynchronous |
| Traditional Chat | Real-time, WebSocket, radio synchronization |
| Hybrid | Chat UX, store-and-forward messaging, email-like metadata, offline synchronization |

**Decision**: **Hybrid model** — conversation-based UX with store-and-forward transport. The same message model works for real-time WebSocket delivery and delayed radio delivery. The `message_envelopes` abstraction handles email/SMTP interop without polluting the chat model.

### Conversation Ownership

| Model | Structure |
|-------|-----------|
| Station | `Station → Conversation` |
| User | `User → Conversation` |
| Both | `Station → Users → Conversations` |

**Decision**: **User-owned conversations within a station context.** Users are members of conversations; conversations exist within the station database. Multi-user support within a single station is first-class.

### Local Chat

Should users connected to the same station be able to exchange messages without transmitting over HF?

**Decision**: **Yes.** Local-only conversations use `channel=websocket` delivery. Mixed local + radio conversations are supported — delivery records are created per-channel and the system attempts all available channels.

### Radio Configuration Source of Truth

Should the Radio Daemon remain the source of truth, or should the configuration also be persisted in the database?

**Decision**: **Daemon provides runtime state via WebSocket; API persists desired configuration in `radio_profiles` table.** On startup, the API reconciles database state with daemon state. When the daemon is unreachable, the API serves last-known state from the database with `radio.connected: false`.

### Broadcast Messaging Behavior

**Decision**: **One-to-many `broadcast` conversations with recipient station lists.** Recipients cannot reply (broadcast is one-directional). Maximum 200 recipients per broadcast conversation.

---

## 13. Future Considerations & Roadmap

Items under consideration for future phases:

- **Multi-process scaling**: Swap in-process EventEmitter to Redis Pub/Sub; in-memory queues to BullMQ/Redis for multi-station server deployments
- **CQRS**: Command Query Responsibility Segregation for messaging at scale
- **Offline synchronization**: Richer conflict resolution and merge strategies
- **Plugin architecture**: Hot-pluggable application modules
- **Multi-radio support**: Multiple transceivers per station
- **Multi-tenant stations**: Multiple independent station contexts on one deployment
- **Federation**: Station-to-station federation (Phase 4 — PostgreSQL + Redis may be reintroduced)
- **GraphQL gateway**: Alternative query interface for complex data fetching
- **Full API versioning strategy**: `/api/v2/` and deprecation policies
- **Delta Chat integration**: Bridging conversation model with email transport for broader interoperability
- **LAN audio streaming**: Browser audio capture → WebSocket → ALSA playback (no SFU needed)

---

## Related Documents

- [Database Schema](../architecture/database.md) — Full normalized SQLite schema with indexes, migrations, retention policies, power-loss strategy, and clock sync
- [Architecture Audit](architecture-audit-sbitx-v2.md) — Critical risks, memory budget, and hardware feasibility assessment
- [hermes-backend Architecture](https://github.com/Rhizomatica/hermes-backend) — Upstream architecture documentation