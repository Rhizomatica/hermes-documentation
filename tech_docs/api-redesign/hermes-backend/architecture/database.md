# HERMES Database Schema

**Project**: hermes-backend  
**Status**: Architecture Design — Adapted for sBitx v2 (Raspberry Pi 4)  
**Based on**: [hermes-backend](https://github.com/Rhizomatica/hermes-backend) architecture

---

## 1. Design Philosophy

The schema is fully normalized (3NF minimum) with deliberate denormalizations where query performance demands it. Every design decision documents its rationale. The schema is migration-managed via Drizzle ORM — no manual SQL patches.

This schema is designed for **SQLite in WAL mode** as the primary production database for single-station sBitx v2 deployments on Raspberry Pi 4. A `DatabaseAdapter` interface in the repository layer abstracts the database backend, enabling PostgreSQL for multi-station server deployments without changing application code.

### Deployment Model

The hermes-backend runs on a **Raspberry Pi 4** accessed via **local WiFi hotspot**. Clients (browser on phone/laptop) connect to the Pi directly. All data lives in SQLite on the Pi — the server is the single source of truth. There is no offline sync protocol or multi-device conflict resolution. Clients that disconnect simply fetch current state via the REST API on reconnection.

### Guiding Principles

| Principle | Implementation |
|-----------|---------------|
| **UUID Primary Keys** | Application-generated UUIDs (SQLite has no `gen_random_uuid()`) |
| **Timestamps** | ISO 8601 text stored as `TEXT` (SQLite has no `TIMESTAMPTZ` type) |
| **Soft Deletes** | `deleted_at` for user-visible entities (messages, attachments) |
| **Timezone Awareness** | All timestamps stored as UTC ISO 8601 strings; timezone conversion handled in application layer |
| **Extensible Metadata** | `TEXT` columns storing JSON (SQLite has no native `JSONB`, but has JSON functions) |
| **Time-Series** | Separate database file with daily table partitioning via application-level sharding |
| **Referential Integrity** | All foreign keys have explicit `ON DELETE` behavior (`PRAGMA foreign_keys = ON`) |
| **Named Indexes** | Descriptive names for debuggability |
| **Write-Ahead Logging** | `PRAGMA journal_mode=WAL` — concurrent reads with a single writer |

---

## 2. Technology Stack

| Component | Technology |
|-----------|------------|
| Primary Database | **SQLite 3.45+ (WAL mode)** |
| ORM | Drizzle ORM (SQLite adapter — `drizzle-orm/sqlite-core`) |
| Migrations | `drizzle-kit` (versioned, sequential, in version control) |
| Event Bus | In-process EventEmitter |
| Job Queues | In-memory priority queue + SQLite jobs table |
| Session Store | SQLite (`user_sessions` table) |

### Why SQLite for sBitx v2

The original hermes-backend architecture chose PostgreSQL for concurrent writes, JSONB, full-text search, and TimescaleDB. These are correct for a **server deployment**. On a **Raspberry Pi 4 field station**, the calculus is different:

| Criteria | SQLite (WAL mode) | PostgreSQL 17 | Winner for Pi 4 |
|----------|:---:|:---:|:---:|
| Memory footprint | 2–5 MB | 300–800 MB (shared_buffers, workers) | **SQLite** |
| Daemon process | None (in-process) | Required (postgres daemon) | **SQLite** |
| Concurrent reads | Excellent (WAL mode) | Excellent | Tie |
| Concurrent writes | Single-writer, queued | Multi-writer MVCC | **Tie on Pi 4**¹ |
| Crash recovery | Near-instant WAL replay | WAL replay (minutes on Pi 4) | **SQLite** |
| SD card wear | Minimal (WAL append-only) | VACUUM generates heavy I/O | **SQLite** |
| Backup | Copy `.sqlite` file | `pg_dump` or WAL archiving | **SQLite** |
| Full-text search | Built-in (FTS5) | Built-in | Tie |
| JSON querying | JSON functions (json_extract, json_each) | JSONB indexing | **PostgreSQL**² |
| Time-series | Application-level sharding | TimescaleDB extension | **PostgreSQL**² |
| Multi-station federation | Limited | Excellent (but Phase 4) | **PostgreSQL**³ |

¹ The single-writer limitation is irrelevant: all writes go through a single Node.js process (the event loop serializes them). At most 2–3 client writes contend for the lock — SQLite's busy_timeout handles this transparently.

² JSON querying and time-series features are less critical on a single-station Pi 4. JSON metadata queries are infrequent. Time-series data (telemetry, GPS) is simple append-and-query-by-time-range — application-level table sharding handles this.

³ PostgreSQL is the correct choice for multi-station server deployments (Phase 4 federation). The `DatabaseAdapter` interface makes this a configuration switch, not a rewrite.

### Dual-Database Strategy

The repository layer is implemented behind a `DatabaseAdapter` interface:

```typescript
// src/db/adapter.ts
interface DatabaseAdapter {
  // Query methods common to both backends
  findConversationById(id: string): Promise<Conversation | null>
  listUserConversations(userId: string, opts: PaginationOpts): Promise<PaginatedResult<Conversation>>
  // ... all repository methods
}

// SQLite implementation (default for sBitx v2)
class SQLiteAdapter implements DatabaseAdapter { /* ... */ }

// PostgreSQL implementation (for multi-station server deployments)
class PostgresAdapter implements DatabaseAdapter { /* ... */ }
```

The adapter is selected at startup via the `DB_ADAPTER` environment variable (default: `sqlite`). This ensures sBitx v2 field stations get SQLite's minimal footprint while the same codebase can scale to PostgreSQL for server deployments.

---

## 3. Entity Relationship Diagram

> **See also**: [Entity-Relationship Diagram](erd.md) — the same model with the complete column list, nullability, unique constraints and all 23 foreign keys, verified against a migrated database.

```mermaid
erDiagram
	direction TB

	users||--o{user_sessions:"has"
	users||--o{user_devices:"owns"
	users||--o{conversation_participants:"member"
	users||--o{messages:"sends"
	users||--o{message_deliveries:"receives"
	users||--o{message_reactions:"reacts"
	users|o--o{audit_logs:"performs"
	users||--o{radio_profiles:"configures"
	users|o--o{connection_schedules:"creates"
	users||--o{attachments:"uploads"
	users||--o{conversations:"creates"
	users||--o{radio_sessions:"runs"
	conversations||--o{conversation_participants:"contains"
	conversations||--o{messages:"contains"
	conversations|o--o{attachments:"contains"
	messages||--o{message_deliveries:"delivery"
	messages||--o{message_reactions:"reactions"
	messages|o--o{attachments:"attachments"
	messages||--o|message_envelopes:"envelope"
	messages|o--o{messages:"replies_to"
	messages|o--o{messages:"forwarded_from"
	radio_profiles|o--o{radio_sessions:"used_in"
	frequencies|o--o{connection_schedules:"scheduled"

    users {
        text id PK "UUID"
        text callsign UK "XA1ABC"
        text display_name
        text role "admin|operator|user|readonly"
        text status "active|suspended|pending"
        text created_at
    }

    user_sessions {
        text id PK "UUID"
        text user_id FK
        text token_hash UK "SHA-256"
        text expires_at
        text revoked_at
    }

    user_devices {
        text id PK "UUID"
        text user_id FK
        text device_type "mobile|desktop|station|browser"
        text push_token
        text platform
    }

    conversations {
        text id PK "UUID"
        text type "direct|group|broadcast|radio"
        text title
        text created_by FK
        text last_activity_at
        text archived_at
    }

    conversation_participants {
        text id PK "UUID"
        text conversation_id FK
        text user_id FK
        text role "owner|admin|member"
        text last_read_message_id
        text left_at
    }

    messages {
        text id PK "UUID"
        text conversation_id FK
        text sender_id FK
        text client_message_id UK "Idempotency"
        text content "max 64KB"
        text content_type "text|markdown|html|audio|system|attachment_only"
        text reply_to_message_id FK
        text status "draft|sending|sent|failed"
        text deleted_at "soft delete"
        text created_at
    }

    message_deliveries {
        text id PK "UUID"
        text message_id FK
        text recipient_id FK
        text channel "websocket|radio|email|push|sms"
        text status "pending|sent|delivered|read|failed"
        int attempts
    }

    message_reactions {
        text id PK "UUID"
        text message_id FK
        text user_id FK
        text emoji
        text created_at
    }

    message_envelopes {
        text id PK "UUID"
        text message_id FK UK
        text envelope_type "inbound|outbound"
        text from_address
        text transport "smtp|uucp|radio|hmp|internal"
        text status
    }

    attachments {
        text id PK "UUID"
        text message_id FK
        text conversation_id FK
        text uploader_id FK
        text storage_path
        text checksum "SHA-256 dedup"
        text status "pending|processing|ready|failed|expired"
        int size_bytes
        text mime_type
    }

    radio_profiles {
        text id PK "UUID"
        text station_id FK
        int profile_index
        int frequency_hz
        text mode "USB|LSB|CW|AM|FM|DIGITAL"
        int volume
        int is_active "0|1"
    }

    radio_sessions {
        text id PK "UUID"
        text station_id FK
        text profile_id FK
        text started_at
        text ended_at
        int bytes_tx
        int bytes_rx
    }

    frequencies {
        text id PK "UUID"
        text alias UK
        int frequency_hz
        text mode "USB|LSB|CW|AM|FM|DIGITAL"
        int is_gateway "0|1"
        text region
    }

    connection_schedules {
        text id PK "UUID"
        text target_callsign
        text frequency_id FK
        text scheduled_at
        text recurrence "JSON RRULE-like"
        text status "pending|running|completed|failed|cancelled"
        text next_run_at
        text created_by FK
    }

    audit_logs {
        text id PK "UUID"
        text actor_id FK
        text action "auth.login|message.deleted|..."
        text entity_type
        text entity_id
        text old_value "JSON"
        text new_value "JSON"
        text created_at
    }

    jobs {
        text id PK "UUID"
        text type "radio_command|send_message|..."
        text payload "JSON"
        int priority "1-10"
        text status "queued|running|completed|failed|cancelled"
        int attempts
        int max_attempts
        text scheduled_at
    }
```

> **Note**: Tables `radio_telemetry_YYYYMMDD` (in `telemetry.db`) and `gps_YYYYMMDD` (in `gps.db`) are daily-sharded time-series tables managed by the application layer, not shown in the ER diagram. See §4.5 and §4.7 for their schemas.
>
> **Implementation status**: neither sharded table exists yet — there is no migration, no Drizzle table and no repository for them in `src/`. They are planned work (see [Go Migration Guide](../development/go-migration.md), Wave 5).

### Relationship Summary

| Parent | Child | Type | On Delete |
|--------|-------|------|-----------|
| `users` | `user_sessions` | 1:∞ | CASCADE |
| `users` | `user_devices` | 1:∞ | CASCADE |
| `users` | `conversations` (creator) | 1:∞ | RESTRICT |
| `users` | `conversation_participants` | 1:∞ | CASCADE |
| `users` | `messages` (sender) | 1:∞ | RESTRICT |
| `users` | `message_deliveries` (recipient) | 1:∞ | CASCADE |
| `users` | `message_reactions` | 1:∞ | CASCADE |
| `users` | `attachments` (uploader) | 1:∞ | RESTRICT |
| `users` | `radio_profiles` | 1:∞ | CASCADE |
| `users` | `radio_sessions` | 1:∞ | CASCADE |
| `users` | `connection_schedules` (creator) | 1:∞ | SET NULL |
| `users` | `audit_logs` (actor) | 1:∞ | SET NULL |
| `conversations` | `conversation_participants` | 1:∞ | CASCADE |
| `conversations` | `messages` | 1:∞ | CASCADE |
| `conversations` | `attachments` | 1:∞ | SET NULL |
| `messages` | `message_deliveries` | 1:∞ | CASCADE |
| `messages` | `message_reactions` | 1:∞ | CASCADE |
| `messages` | `attachments` | 1:∞ | SET NULL |
| `messages` | `messages` (reply_to) | 1:∞ | SET NULL |
| `messages` | `messages` (forwarded_from) | 1:∞ | SET NULL |
| `messages` | `message_envelopes` | 1:1 | CASCADE |
| `radio_profiles` | `radio_sessions` | 1:∞ | SET NULL |
| `frequencies` | `connection_schedules` | 1:∞ | SET NULL |

---

## 4. Schema Definitions

> **SQLite note**: All DDL below uses SQLite-compatible syntax. UUIDs are generated in the application layer. Timestamps are stored as ISO 8601 `TEXT`. Partial indexes use `CREATE INDEX ... WHERE` (supported in SQLite 3.8+).

### 4.1 Identity & Authentication

#### `users`

Represents both human operators and remote station identities.

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    callsign        TEXT NOT NULL UNIQUE,           -- Amateur radio callsign or station ID
    display_name    TEXT NOT NULL,
    email           TEXT UNIQUE,                    -- Optional: for email interoperability
    password_hash   TEXT,                           -- NULL for remote-only station users
    role            TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('admin', 'operator', 'user', 'readonly')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'pending')),
    avatar_path     TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',     -- JSON stored as TEXT
    locale          TEXT NOT NULL DEFAULT 'en'      -- User's preferred language (ISO 639-1)
                    CHECK (locale IN ('en', 'es', 'pt-BR')),
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    last_seen_at    TEXT                             -- ISO 8601 UTC
);

CREATE INDEX idx_users_callsign ON users (callsign);
CREATE INDEX idx_users_role ON users (role);
CREATE INDEX idx_users_status ON users (status);
```

**Columns explained:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | Application-generated UUID (v4 or v7) |
| `callsign` | TEXT UNIQUE | Amateur radio callsign (e.g., `XA1ABC`) |
| `display_name` | TEXT | Human-readable name |
| `email` | TEXT UNIQUE | Optional email for SMTP interop |
| `password_hash` | TEXT | bcrypt hash (NULL for remote-only users) |
| `role` | CHECK | `admin`, `operator`, `user`, `readonly` |
| `status` | CHECK | `active`, `suspended`, `pending` |

#### `user_sessions`

JWT refresh token tracking. Tokens stored as SHA-256 hashes — never plaintext.

```sql
CREATE TABLE user_sessions (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    user_id         TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,           -- SHA-256 of refresh token
    device_id       TEXT,                           -- Links to user_devices if known
    ip_address      TEXT,                           -- Stored as string (SQLite has no INET)
    user_agent      TEXT,
    expires_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    revoked_at      TEXT,                           -- ISO 8601 UTC
    created_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_user_sessions_user_id ON user_sessions (user_id);
CREATE INDEX idx_user_sessions_token_hash ON user_sessions (token_hash);
CREATE INDEX idx_user_sessions_expires_active ON user_sessions (expires_at)
    WHERE revoked_at IS NULL;
```

#### `user_devices`

Tracks devices per user for push notifications and session management.

```sql
CREATE TABLE user_devices (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    user_id         TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    device_name     TEXT NOT NULL,
    device_type     TEXT NOT NULL
                    CHECK (device_type IN ('mobile', 'desktop', 'station', 'browser')),
    push_token      TEXT,                           -- FCM/APNs token
    platform        TEXT,                           -- ios | android | web | linux
    last_seen_at    TEXT,                           -- ISO 8601 UTC
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_user_devices_user_id ON user_devices (user_id);
```

---

### 4.2 Conversations & Messaging

#### `conversations`

The fundamental unit of messaging context. Replaces the legacy inbox/outbox email model.

```sql
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    type            TEXT NOT NULL
                    CHECK (type IN ('direct', 'group', 'broadcast', 'radio')),
    title           TEXT,                           -- NULL for direct conversations
    description     TEXT,
    avatar_path     TEXT,
    created_by      TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    last_activity_at TEXT,                          -- ISO 8601 UTC — denormalized for sort performance
    archived_at     TEXT,                           -- ISO 8601 UTC
    metadata        TEXT NOT NULL DEFAULT '{}',     -- JSON: associated frequency, radio profile, etc.
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_conversations_type ON conversations (type);
CREATE INDEX idx_conversations_last_activity ON conversations (last_activity_at DESC);
CREATE INDEX idx_conversations_created_by ON conversations (created_by);
```

**Conversation types:**

| Type | Description | Max Participants | Title |
|------|-------------|:---:|:---:|
| `direct` | 1-to-1 chat | 2 | Not required |
| `group` | N-to-N group chat | 50 | Required |
| `broadcast` | 1-to-many (announcements, no replies) | 200 | Required |
| `radio` | Linked to a radio channel/frequency | Varies | Optional |

**Key rules:**
- A `direct` conversation is identified by its two participant IDs (ordered) — no duplicates allowed
- A user leaving a `group` conversation is soft-tracked via `conversation_participants.left_at`
- A `broadcast` conversation has recipients who cannot reply
- Conversations are never hard-deleted — only `archived_at` is set

#### `conversation_participants`

Many-to-many relationship between users and conversations. `last_read_message_id` enables efficient unread counts without a full scan.

```sql
CREATE TABLE conversation_participants (
    id                      TEXT PRIMARY KEY,       -- Application-generated UUID
    conversation_id         TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    user_id                 TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role                    TEXT NOT NULL DEFAULT 'member'
                            CHECK (role IN ('owner', 'admin', 'member')),
    last_read_message_id    TEXT,                   -- For unread tracking
    last_read_at            TEXT,                   -- ISO 8601 UTC
    muted_until             TEXT,                   -- ISO 8601 UTC
    joined_at               TEXT NOT NULL,          -- ISO 8601 UTC
    left_at                 TEXT,                   -- ISO 8601 UTC
    UNIQUE (conversation_id, user_id)
);

CREATE INDEX idx_conv_participants_conversation ON conversation_participants (conversation_id);
CREATE INDEX idx_conv_participants_user ON conversation_participants (user_id);
CREATE INDEX idx_conv_participants_active ON conversation_participants (user_id)
    WHERE left_at IS NULL;
```

#### `messages`

The core message entity. Chat-native design with email-compatible fields.

```sql
CREATE TABLE messages (
    id                      TEXT PRIMARY KEY,       -- Application-generated UUID
    conversation_id         TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    sender_id               TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    client_message_id       TEXT UNIQUE,            -- Client-generated idempotency key
    content                 TEXT,                   -- NULL for attachment-only messages; max 64 KB enforced in app
    content_type            TEXT NOT NULL DEFAULT 'text'
                            CHECK (content_type IN ('text', 'markdown', 'html', 'audio', 'system', 'attachment_only')),
    reply_to_message_id     TEXT REFERENCES messages (id) ON DELETE SET NULL,
    forwarded_from_id       TEXT REFERENCES messages (id) ON DELETE SET NULL,
    subject                 TEXT,                   -- Email interoperability: optional subject line (max 256 chars)
    status                  TEXT NOT NULL DEFAULT 'sending'
                            CHECK (status IN ('draft', 'sending', 'sent', 'failed')),
    edited_at               TEXT,                   -- ISO 8601 UTC
    deleted_at              TEXT,                   -- ISO 8601 UTC — soft delete; content replaced with NULL
    metadata                TEXT NOT NULL DEFAULT '{}', -- JSON
    created_at              TEXT NOT NULL,           -- ISO 8601 UTC
    updated_at              TEXT NOT NULL            -- ISO 8601 UTC
);

-- Critical: conversation + time is the primary query pattern
CREATE INDEX idx_messages_conversation_created ON messages (conversation_id, created_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_messages_sender ON messages (sender_id);
CREATE INDEX idx_messages_client_id ON messages (client_message_id)
    WHERE client_message_id IS NOT NULL;
CREATE INDEX idx_messages_reply_to ON messages (reply_to_message_id)
    WHERE reply_to_message_id IS NOT NULL;
```

**Message content constraints (enforced in application layer):**

| Field | Constraint |
|-------|------------|
| `content` | Max 64 KB (65,536 bytes) |
| `subject` | Max 256 characters |
| Reactions per message | Max 20 unique emoji |

**Message status lifecycle:**

```
draft → sending → sent
                   ├──→ (delivered → read, per recipient)
                   └──→ failed
```

**Idempotency**: `client_message_id` is a client-generated UUID. If a client resends the same request due to network failure, the server deduplicates by this key — returning the already-created message.

**Soft delete behavior**: When `deleted_at` is set, `content` is replaced with `NULL` but the row is retained. The conversation list query filters `WHERE deleted_at IS NULL`. Reply chains reference deleted messages via `reply_to_message_id` with `ON DELETE SET NULL` — the API response marks these as `{ replyDeleted: true }`.

#### `message_deliveries`

Per-recipient, per-channel delivery tracking. Fundamentally different from the legacy binary sent/received model.

```sql
CREATE TABLE message_deliveries (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    message_id      TEXT NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    recipient_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    channel         TEXT NOT NULL
                    CHECK (channel IN ('websocket', 'email', 'radio', 'push', 'sms')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'delivered', 'read', 'failed')),
    sent_at         TEXT,                           -- ISO 8601 UTC
    delivered_at    TEXT,                           -- ISO 8601 UTC
    read_at         TEXT,                           -- ISO 8601 UTC
    failed_at       TEXT,                           -- ISO 8601 UTC
    error           TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TEXT,                           -- ISO 8601 UTC
    UNIQUE (message_id, recipient_id, channel)
);

CREATE INDEX idx_deliveries_message ON message_deliveries (message_id);
CREATE INDEX idx_deliveries_recipient_status ON message_deliveries (recipient_id, status)
    WHERE status IN ('pending', 'sent', 'delivered');
CREATE INDEX idx_deliveries_next_retry ON message_deliveries (next_retry_at)
    WHERE status = 'pending' AND next_retry_at IS NOT NULL;
```

**Delivery channels:**

| Channel | Trigger | Delivery Confirmation |
|---------|---------|----------------------|
| `websocket` | Recipient online (WebSocket connected) | `MESSAGE_ACK` from client |
| `push` | Recipient has push token (mobile) | FCM/APNs delivery receipt |
| `radio` | Target station reachable via HF | UUCP acknowledgment |
| `email` | Recipient has email configured | SMTP delivery report |
| `sms` | Recipient has SMS configured | SMS gateway delivery report |

#### `message_reactions`

Emoji reactions on messages (WhatsApp/Telegram model).

```sql
CREATE TABLE message_reactions (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    message_id      TEXT NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    emoji           TEXT NOT NULL,
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    UNIQUE (message_id, user_id, emoji)
);

CREATE INDEX idx_reactions_message ON message_reactions (message_id);
```

---

### 4.3 Attachments

Normalized attachment model. An attachment can exist before being linked to a message (upload-first flow).

```sql
CREATE TABLE attachments (
    id                  TEXT PRIMARY KEY,           -- Application-generated UUID
    message_id          TEXT REFERENCES messages (id) ON DELETE SET NULL,
    conversation_id     TEXT REFERENCES conversations (id) ON DELETE SET NULL,
    uploader_id         TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    filename            TEXT NOT NULL,              -- Sanitized, stored filename
    original_filename   TEXT NOT NULL,              -- Original client-provided name
    mime_type           TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,           -- SQLite INTEGER = 64-bit signed
    storage_path        TEXT NOT NULL,              -- Relative to storage root
    storage_backend     TEXT NOT NULL DEFAULT 'local'
                        CHECK (storage_backend IN ('local', 's3', 'gcs')),
    checksum            TEXT NOT NULL,              -- SHA-256 (enables dedup)
    preview_path        TEXT,                       -- Thumbnail/preview
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'expired')),
    metadata            TEXT NOT NULL DEFAULT '{}', -- JSON: image dimensions, duration, etc.
    created_at          TEXT NOT NULL,              -- ISO 8601 UTC
    expires_at          TEXT,                       -- For temporary attachments
    deleted_at          TEXT                        -- ISO 8601 UTC
);

CREATE INDEX idx_attachments_message ON attachments (message_id)
    WHERE message_id IS NOT NULL;
CREATE INDEX idx_attachments_checksum ON attachments (checksum);
CREATE INDEX idx_attachments_uploader ON attachments (uploader_id);
CREATE INDEX idx_attachments_status ON attachments (status)
    WHERE status IN ('pending', 'processing');
```

**Security controls:**
- MIME type validated from file content bytes (`file-type` library), not from `Content-Type` header
- Filename sanitized: `path.basename(filename)` prevents path traversal
- Stored with UUID filename — client name stored as `original_filename` only
- SHA-256 checksum enables deduplication (same file uploaded twice → reuse)
- Downloads via signed time-limited URLs
- Attachment access requires conversation membership
- For HF radio store-and-forward: a 30-day `attachment_token` is embedded in the radio message envelope

**Attachment status lifecycle:**

```
pending → processing → ready
                     → failed
                     → expired
```

---

### 4.4 Email Transport Envelope

Email-compatible transport metadata attached to messages without polluting the core message model.

```sql
CREATE TABLE message_envelopes (
    id                  TEXT PRIMARY KEY,           -- Application-generated UUID
    message_id          TEXT NOT NULL UNIQUE REFERENCES messages (id) ON DELETE CASCADE,
    envelope_type       TEXT NOT NULL
                        CHECK (envelope_type IN ('inbound', 'outbound')),
    from_address        TEXT NOT NULL,
    to_addresses        TEXT NOT NULL DEFAULT '[]', -- JSON array stored as TEXT
    cc_addresses        TEXT NOT NULL DEFAULT '[]', -- JSON array stored as TEXT
    bcc_addresses       TEXT NOT NULL DEFAULT '[]',-- JSON array stored as TEXT
    subject             TEXT,
    headers             TEXT NOT NULL DEFAULT '{}', -- JSON stored as TEXT
    raw_message_path    TEXT,                       -- Path to original raw message file
    transport           TEXT NOT NULL
                        CHECK (transport IN ('smtp', 'uucp', 'radio', 'hmp', 'internal')),
    external_message_id TEXT,                       -- Message-ID from email header
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'sent', 'received', 'failed')),
    locale              TEXT NOT NULL DEFAULT 'en', -- Recipient's language for email templates
    created_at          TEXT NOT NULL,              -- ISO 8601 UTC
    processed_at        TEXT                        -- ISO 8601 UTC
);

CREATE INDEX idx_envelopes_message ON message_envelopes (message_id);
CREATE INDEX idx_envelopes_status ON message_envelopes (status, transport)
    WHERE status IN ('pending', 'processing');
CREATE INDEX idx_envelopes_external_id ON message_envelopes (external_message_id)
    WHERE external_message_id IS NOT NULL;
```

**Design principle**: The chat UX never knows or cares about email envelopes. Email is a **transport concern**, not a messaging concern. The envelope carries all the metadata needed for SMTP/UUCP/HMP delivery without cluttering the message model.

---

### 4.5 Radio Domain

#### `radio_profiles`

Replaces the flat profile struct from sBitx. Maps 1:1 to hardware profiles but stored in a normalized database.

```sql
CREATE TABLE radio_profiles (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    station_id      TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    profile_index   INTEGER NOT NULL,               -- 0-based hardware profile index
    name            TEXT NOT NULL,
    frequency_hz    INTEGER NOT NULL,               -- Hz (not kHz/MHz) for precision; INTEGER = 64-bit in SQLite
    mode            TEXT NOT NULL
                    CHECK (mode IN ('USB', 'LSB', 'CW', 'AM', 'FM', 'DIGITAL')),
    volume          INTEGER NOT NULL DEFAULT 50     CHECK (volume BETWEEN 0 AND 100),
    bfo_hz          INTEGER NOT NULL DEFAULT 0,
    digital_voice   INTEGER NOT NULL DEFAULT 0,     -- SQLite has no BOOLEAN; 0/1 used
    power_level     INTEGER,                        -- NULL = default
    is_active       INTEGER NOT NULL DEFAULT 0,     -- SQLite: 0 = false, 1 = true
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    UNIQUE (station_id, profile_index)
);
```

#### `radio_sessions`

Records when the radio was active and its aggregate stats. Useful for diagnostics, billing, and audit.

```sql
CREATE TABLE radio_sessions (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    station_id      TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    profile_id      TEXT REFERENCES radio_profiles (id) ON DELETE SET NULL,
    started_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    ended_at        TEXT,                           -- ISO 8601 UTC
    bytes_tx        INTEGER NOT NULL DEFAULT 0,
    bytes_rx        INTEGER NOT NULL DEFAULT 0,
    metadata        TEXT NOT NULL DEFAULT '{}'      -- JSON stored as TEXT
);

CREATE INDEX idx_radio_sessions_station ON radio_sessions (station_id, started_at DESC);
```

#### `radio_telemetry` (Time-Series via Application-Level Sharding)

High-frequency telemetry data. Stored in a **separate SQLite database file** (`telemetry.db`) to avoid write contention with the main database. Data is organized into daily-sharded tables via application-level partition management.

```sql
-- In telemetry.db — template table, cloned per day as telemetry_20260717, etc.
CREATE TABLE telemetry_20260717 (
    time            TEXT NOT NULL,                  -- ISO 8601 UTC
    station_id      TEXT NOT NULL,
    frequency_hz    INTEGER,
    mode            TEXT,
    tx              INTEGER,                        -- 0/1
    rx              INTEGER,                        -- 0/1
    snr             INTEGER,
    bitrate         INTEGER,
    bytes_tx        INTEGER,
    bytes_rx        INTEGER,
    led_ok          INTEGER,                        -- 0/1
    connected       INTEGER,                        -- 0/1
    protection      INTEGER,                        -- 0/1
    power_level     INTEGER,
    profile_idx     INTEGER,
    timeout_counter INTEGER,
    metadata        TEXT                            -- JSON stored as TEXT
);

CREATE INDEX idx_telemetry_station_time ON telemetry_20260717 (station_id, time DESC);
```

**Partitioning strategy:**
- The application creates daily tables named `telemetry_YYYYMMDD` on startup (creates today's table if it doesn't exist)
- A periodic cleanup job drops tables older than 90 days
- Queries spanning multiple days use `UNION ALL` across the relevant tables
- At ~1 row/second, a single day's table holds ~86,400 rows — trivially small for SQLite

**Retention**: 90 days by default, configurable. Old daily tables are dropped via scheduled cleanup.

---

### 4.6 Frequencies & Scheduling

#### `frequencies`

Known frequency presets. `is_gateway` marks frequencies that connect to internet-accessible gateways.

```sql
CREATE TABLE frequencies (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    alias           TEXT NOT NULL UNIQUE,
    frequency_hz    INTEGER NOT NULL,
    mode            TEXT NOT NULL DEFAULT 'USB'
                    CHECK (mode IN ('USB', 'LSB', 'CW', 'AM', 'FM', 'DIGITAL')),
    description     TEXT,
    is_gateway      INTEGER NOT NULL DEFAULT 0,     -- 0/1
    region          TEXT,
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_frequencies_alias ON frequencies (alias);
CREATE INDEX idx_frequencies_gateway ON frequencies (is_gateway) WHERE is_gateway = 1;
```

#### `connection_schedules`

Replaces the legacy `/caller` endpoint. Represents UUCP/radio call schedules with recurrence rules.

```sql
CREATE TABLE connection_schedules (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    target_callsign TEXT NOT NULL,
    frequency_id    TEXT REFERENCES frequencies (id) ON DELETE SET NULL,
    scheduled_at    TEXT NOT NULL,                  -- ISO 8601 UTC
    recurrence      TEXT,                           -- JSON: NULL = one-time
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    last_run_at     TEXT,                           -- ISO 8601 UTC
    next_run_at     TEXT,                           -- ISO 8601 UTC
    created_by      TEXT REFERENCES users (id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_schedules_next_run ON connection_schedules (next_run_at)
    WHERE status IN ('pending', 'running');
```

**Recurrence format** (JSON stored as TEXT — RRULE-like):
```json
{
  "freq": "DAILY",
  "byhour": [12, 18],
  "byday": ["MO", "WE", "FR"]
}
```

---

### 4.7 Geolocation

#### `gps_readings` (Time-Series via Application-Level Sharding)

Time-series GPS coordinates per station. Stored in a **separate SQLite database file** (`gps.db`) with daily table sharding — same pattern as radio telemetry.

```sql
-- In gps.db — template table, cloned per day as gps_20260717, etc.
CREATE TABLE gps_20260717 (
    time            TEXT NOT NULL,                  -- ISO 8601 UTC
    station_id      TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    altitude_m      REAL,
    accuracy_m      REAL,
    speed_kmh       REAL,
    heading_deg     REAL,
    source          TEXT DEFAULT 'gps'
                    CHECK (source IN ('gps', 'manual', 'estimated')),
    metadata        TEXT                            -- JSON stored as TEXT
);

CREATE INDEX idx_gps_station_time ON gps_20260717 (station_id, time DESC);
```

**Retention**: 365 days by default. Old daily tables dropped via scheduled cleanup.

---

### 4.8 Job Queue (SQLite-Backed)

In-memory priority queue with SQLite persistence for job durability across process restarts. Replaces BullMQ/Redis.

```sql
CREATE TABLE jobs (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    type            TEXT NOT NULL,                  -- Job type: 'radio_command', 'send_message', 'process_attachment', etc.
    payload         TEXT NOT NULL,                  -- JSON: job-specific data
    priority        INTEGER NOT NULL DEFAULT 5,     -- 1=highest, 10=lowest
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    attempts        INTEGER NOT NULL DEFAULT 0,
    scheduled_at    TEXT,                           -- ISO 8601 UTC — for delayed jobs
    started_at      TEXT,                           -- ISO 8601 UTC
    completed_at    TEXT,                           -- ISO 8601 UTC
    failed_at       TEXT,                           -- ISO 8601 UTC
    error           TEXT,
    created_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_jobs_status_priority ON jobs (status, priority, created_at)
    WHERE status IN ('queued', 'failed');
CREATE INDEX idx_jobs_scheduled ON jobs (scheduled_at)
    WHERE status = 'queued' AND scheduled_at IS NOT NULL;
```

**Architecture**:
- Jobs are managed by an in-memory priority queue for low-latency processing
- On enqueue, jobs are also written to the `jobs` table for durability
- On dequeue + complete, the row is updated (not deleted — kept for audit)
- On process restart, the queue is rehydrated from `jobs WHERE status IN ('queued', 'running')`
- Running jobs at restart time are treated as failed (no partial execution)

**Important**: Job persistence to SQLite is mandatory, not best-effort. The HTTP response must not be acknowledged until the job row is written with `status=queued`. On recovery, all `queued` jobs are re-queued for execution.

---

### 4.9 Audit Logs

Immutable audit trail. Never updated or deleted. Records all significant state changes across the platform.

```sql
CREATE TABLE audit_logs (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID
    actor_id        TEXT REFERENCES users (id) ON DELETE SET NULL,
    action          TEXT NOT NULL,                  -- e.g., 'message.created', 'radio.freq_changed'
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    old_value       TEXT,                           -- JSON stored as TEXT
    new_value       TEXT,                           -- JSON stored as TEXT
    ip_address      TEXT,                           -- Stored as string
    user_agent      TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',     -- JSON stored as TEXT
    locale          TEXT NOT NULL DEFAULT 'en',     -- Actor's locale at time of action (for i18n audit descriptions)
    created_at      TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX idx_audit_actor ON audit_logs (actor_id, created_at DESC);
CREATE INDEX idx_audit_entity ON audit_logs (entity_type, entity_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs (action, created_at DESC);
```

**Audited actions:**

| Action | Description |
|--------|-------------|
| `auth.login` | Successful login |
| `auth.login_failed` | Failed login attempt |
| `auth.logout` | Session revocation |
| `user.created` | New user created |
| `user.updated` | User modified |
| `user.deleted` | User soft-deleted |
| `user.role_changed` | Role escalation/demotion |
| `message.deleted` | Message soft-deleted |
| `conversation.archived` | Conversation archived |
| `radio.frequency_changed` | Frequency modified |
| `radio.ptt_activated` | PTT enabled |
| `radio.protection_reset` | SWR protection reset |
| `system.config_changed` | System configuration modified |
| `system.reboot` | System reboot initiated |
| `system.shutdown` | Shutdown initiated |
| `system.clock_set` | Manual clock adjustment |
| `auth.unauthorized_access` | RBAC violation attempt |
| `attachment.deleted` | Attachment removed |

---

## 5. Indexing Strategy

| Table | Primary Query Pattern | Index |
|-------|----------------------|-------|
| `messages` | Paginate by conversation + time | `(conversation_id, created_at DESC)` partial WHERE deleted_at IS NULL |
| `messages` | Lookup by client_message_id (dedup) | `(client_message_id)` UNIQUE, partial WHERE client_message_id IS NOT NULL |
| `message_deliveries` | Pending deliveries for retry | `(recipient_id, status)` partial |
| `conversation_participants` | Active conversations for user | `(user_id)` WHERE `left_at IS NULL` |
| `radio_telemetry_*` | Station telemetry by time range | `(station_id, time DESC)` per daily table |
| `gps_*` | Station GPS history | `(station_id, time DESC)` per daily table |
| `audit_logs` | Entity audit trail | `(entity_type, entity_id, created_at)` |
| `conversations` | Sort by last activity | `(last_activity_at DESC)` |
| `user_sessions` | Token lookup | `(token_hash)` UNIQUE |
| `connection_schedules` | Next scheduled runs | `(next_run_at)` partial |
| `jobs` | Queued/failed jobs by priority | `(status, priority, created_at)` partial |
| `user_sessions` | Cleanup expired | `(expires_at)` partial WHERE revoked_at IS NULL |

---

## 6. Critical Query: Conversation List with Unread Counts

This is the most performance-critical query in the system — loaded on every client session start. Adapted for SQLite:

```sql
SELECT 
  c.id,
  c.type,
  c.title,
  c.last_activity_at,
  SUBSTR(lm.content, 1, 200) AS content_preview,  -- First 200 chars only
  lm.created_at AS last_message_at,
  u.callsign AS last_sender_callsign,
  (
    SELECT COUNT(*)
    FROM messages msgs
    WHERE msgs.conversation_id = c.id
      AND msgs.created_at > COALESCE(cp.last_read_at, '1970-01-01T00:00:00Z')
      AND msgs.sender_id != :userId
      AND msgs.deleted_at IS NULL
  ) AS unread_count
FROM conversation_participants cp
JOIN conversations c ON c.id = cp.conversation_id
LEFT JOIN messages lm ON lm.id = (
  SELECT id FROM messages m2
  WHERE m2.conversation_id = c.id
    AND m2.deleted_at IS NULL
  ORDER BY m2.created_at DESC
  LIMIT 1
)
LEFT JOIN users u ON u.id = lm.sender_id
WHERE cp.user_id = :userId
  AND cp.left_at IS NULL
  AND (c.archived_at IS NULL OR :includeArchived = 1)
ORDER BY c.last_activity_at DESC
LIMIT 50;
```

**Key differences from PostgreSQL version:**
- Uses `SUBSTR(lm.content, 1, 200)` instead of `LEFT(content, 200)` — SQLite syntax
- Uses correlated subquery for `last_message_id` instead of `LEFT JOIN LATERAL` (SQLite has no `LATERAL`)
- Uses `COALESCE(cp.last_read_at, '1970-01-01T00:00:00Z')` for unread count baseline
- Returns `content_preview` (first 200 characters) instead of full `content` to prevent large messages from bloating the list response

---

## 7. Migration Strategy

- All migrations managed by **Drizzle ORM** via `drizzle-kit` with the SQLite driver
- Migrations are **versioned, sequential**, and checked into version control
- **SQLite migration limitations**:
  - SQLite does not support `ALTER TABLE ... DROP COLUMN` (prior to 3.35) or `ALTER COLUMN` — Drizzle handles this by creating a new table, copying data, dropping old table, renaming
  - Indexes cannot be created `CONCURRENTLY` (no such concept in SQLite — the database is locked during writes anyway)
  - For large tables, migrations that require table rebuilds should be run during maintenance windows
- Migration **rollback scripts** written for every migration
- Daily sharded tables (telemetry, GPS) are managed by application code, not Drizzle migrations

### Migration Commands

```bash
# Generate migration from schema changes
npm run db:generate

# Apply migrations
npm run db:migrate

# Rollback last migration
npm run db:rollback
```

---

## 8. Retention & Archival

| Table | Retention | Strategy |
|-------|-----------|----------|
| `radio_telemetry_*` (daily tables) | 90 days | Drop daily tables older than retention period via scheduled cleanup |
| `gps_*` (daily tables) | 365 days | Drop daily tables older than retention period via scheduled cleanup |
| `audit_logs` | 2 years | DELETE by `created_at` in batches (avoid long locks) |
| `messages` (deleted) | 90 days | DELETE `WHERE deleted_at IS NOT NULL AND deleted_at < 90 days` |
| `user_sessions` (expired) | 7 days after expiry | DELETE `WHERE expires_at < now - 7 days OR revoked_at IS NOT NULL` |
| `jobs` (completed) | 30 days | DELETE `WHERE status IN ('completed', 'cancelled') AND completed_at < 30 days` |

---

## 9. Drizzle ORM Schema Mapping (TypeScript)

The above SQL is mirrored in `src/db/schema/` using Drizzle ORM's SQLite adapter. Schema-as-TypeScript means the schema definition IS the type definition — no code generation step, no drift between schema and types.

```typescript
// src/db/schema/messages.ts
import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core'
import { conversations } from './conversations'
import { users } from './users'

export const messages = sqliteTable('messages', {
  id: text('id').primaryKey(),                        // Application-generated UUID
  conversationId: text('conversation_id')
    .notNull()
    .references(() => conversations.id, { onDelete: 'cascade' }),
  senderId: text('sender_id')
    .notNull()
    .references(() => users.id, { onDelete: 'restrict' }),
  clientMessageId: text('client_message_id').unique(),
  content: text('content'),                            // Max 64 KB, enforced in app layer
  contentType: text('content_type').notNull().default('text'),
  replyToMessageId: text('reply_to_message_id'),
  subject: text('subject'),
  status: text('status').notNull().default('sending'),
  editedAt: text('edited_at'),
  deletedAt: text('deleted_at'),
  metadata: text('metadata').notNull().default('{}'),  // JSON stored as TEXT
  createdAt: text('created_at').notNull(),
  updatedAt: text('updated_at').notNull(),
})

export type Message = typeof messages.$inferSelect
export type NewMessage = typeof messages.$inferInsert
```

**SQLite adapter differences from PostgreSQL:**
- `pgTable` → `sqliteTable`, `pg-core` → `sqlite-core`
- `uuid('id').primaryKey().defaultRandom()` → `text('id').primaryKey()` (UUIDs generated in application)
- `timestamp('created_at', { withTimezone: true }).defaultNow()` → `text('created_at').notNull()` (ISO 8601 strings)
- `jsonb('metadata').notNull().default({})` → `text('metadata').notNull().default('{}')` (JSON as TEXT)
- `boolean('is_active')` → `integer('is_active', { mode: 'boolean' })` (0/1)

---

## 10. Database Adapter Interface

The repository layer abstracts the database backend behind a `DatabaseAdapter` interface:

```typescript
// src/db/adapter.ts
export interface DatabaseAdapter {
  // Conversation repository
  findConversationById(id: string): Promise<Conversation | null>
  listUserConversations(userId: string, opts: PaginationOpts): Promise<PaginatedResult<Conversation>>
  createConversation(data: CreateConversationInput): Promise<Conversation>
  
  // Message repository
  findMessageById(id: string): Promise<Message | null>
  listMessages(conversationId: string, opts: CursorPagination): Promise<PaginatedResult<Message>>
  createMessage(data: CreateMessageInput): Promise<Message>
  softDeleteMessage(id: string, userId: string): Promise<void>
  
  // ... all repository methods

  // Health
  healthCheck(): Promise<{ ok: boolean; latencyMs: number }>
}
```

**Implementations:**
- `SQLiteAdapter` — Default for sBitx v2 single-station deployments (uses `better-sqlite3` or `@libsql/client`)
- `PostgresAdapter` — For multi-station server deployments (uses `postgres` or `pg`)

The adapter is selected at startup:

```bash
# sBitx v2 field station (default)
DB_ADAPTER=sqlite DB_PATH=/var/lib/hermes/hermes.db

# Multi-station server deployment
DB_ADAPTER=postgres DB_URL=postgresql://user:pass@host:5432/hermes
```

---

## 11. Legacy Migration: From hermes-api SQLite to New Schema

The legacy `hermes-api` already uses SQLite. The migration to the new schema involves:

1. **Export**: Dump existing SQLite data as JSON via legacy API
2. **Transform**: Map data to new normalized schema (inbox/outbox → conversations)
3. **Load**: Bulk-insert into new SQLite database via Drizzle seed scripts
4. **Validate**: Row counts and checksum comparisons between old and new
5. **Run in parallel**: Both database files accessible during transition (different paths)
6. **Decommission**: Old database file removed after validation period

**Schema transformation:**

| Legacy (hermes-api SQLite) | New (SQLite) |
|----------------------------|--------------|
| `messages` table (inbox/outbox folders) | `conversations` + `messages` (conversation-native) |
| `files` table (separate FileController) | `attachments` (linked to messages) |
| Flat radio profile struct | `radio_profiles` (normalized) |
| No delivery tracking | `message_deliveries` (per-recipient, per-channel) |
| No sync support | N/A — clients fetch current state via REST on reconnect |
| No audit logging | `audit_logs` (immutable) |
| No job queue persistence | `jobs` table |

---

## 12. Power-Loss & Recovery Strategy

### 12.1 Filesystem Configuration

| Setting | Recommendation | Rationale |
|---------|---------------|-----------|
| Filesystem | **ext4** with `data=ordered` or **f2fs** (flash-friendly) | ext4 is battle-tested on Raspberry Pi; f2fs is optimized for SD cards |
| Mount options | `noatime,nodiratime` | Reduces write amplification on SD cards |
| Journal mode | ext4 `data=ordered` (default) | Metadata journaling; f2fs is already flash-optimized |
| Swap | **Disabled** on SD card | Swap on SD card causes excessive wear and is too slow to be useful on Pi 4 with 4 GB RAM |

### 12.2 SQLite Power-Loss Configuration

```sql
-- Set on every database connection open
PRAGMA journal_mode = WAL;           -- Write-Ahead Logging: atomic commits, concurrent reads
PRAGMA synchronous = NORMAL;         -- Safe in WAL mode; FULL would double writes to SD card
PRAGMA foreign_keys = ON;            -- Enforce referential integrity
PRAGMA busy_timeout = 5000;          -- Wait up to 5s if database is locked
PRAGMA cache_size = -8000;           -- 8 MB page cache (reasonable for Pi 4)
PRAGMA mmap_size = 268435456;        -- 256 MB memory-mapped I/O
PRAGMA wal_autocheckpoint = 1000;    -- Checkpoint WAL every 1000 pages (~4 MB)
PRAGMA journal_size_limit = 4194304; -- Limit WAL file to 4 MB (force checkpoint if exceeded)
```

**What happens on power loss with WAL + NORMAL:**
- Committed transactions are safe (WAL contains the commit record)
- Uncommitted transactions in the WAL are discarded on next open
- The WAL file is automatically checkpointed on next database open
- **No manual recovery needed** — SQLite handles this automatically
- Worst case: lose the last uncommitted transaction (in-flight at power loss)
- Crash recovery time: < 1 second (WAL file typically < 4 MB)

### 12.3 Graceful Shutdown Sequence

On low-battery signal (GPIO trigger) or `systemctl stop`:

```
1. GPIO low-battery interrupt / systemd stop signal
2. Stop accepting new WebSocket connections
3. Drain in-flight HTTP requests (5-second grace period)
4. Flush in-memory job queue to SQLite jobs table
5. Complete in-flight database transactions
6. PRAGMA wal_checkpoint(TRUNCATE)  -- Force WAL checkpoint to main DB file
7. Write current system clock to /var/lib/hermes/last_known_time
8. Close SQLite database connection
9. Stop Node.js process
10. systemd: ExecStop completes → system shutdown
```

### 12.4 Boot-Time Recovery Sequence

```
1. System boots → systemd starts hermes-backend
2. Filesystem check: ext4 journal replay (automatic) or f2fs recovery
3. SQLite database opens:
   - WAL auto-recovery: uncommitted frames discarded
   - committed frames checkpointed to main DB
   - Database is immediately usable
4. Clock initialization (see §13 below)
5. Rehydrate in-memory job queue from jobs table WHERE status IN ('queued', 'running')
   - Mark 'running' jobs as 'failed' (they were interrupted)
   - Re-queue 'queued' jobs
6. Rehydrate rate limit counters from SQLite (if persistent rate limiting is enabled)
7. Re-establish WebSocket bridge to radio daemon
8. API begins accepting requests
9. Total recovery time: < 10 seconds from service start
```

### 12.5 SD Card Wear Management

| Strategy | Implementation |
|----------|---------------|
| Mount with `noatime` | Avoids write on every file read |
| WAL mode | Append-only writes to WAL; reduces random writes to main DB |
| Batch writes | Application batches multiple INSERTs into transactions |
| Log to tmpfs | Pino logs written to `/var/log/hermes` on SD card, rotated to tmpfs for debug logging |
| Metrics disabled by default | Prometheus metrics generate constant writes; disabled on Pi 4 |
| Separate telemetry DB | `telemetry.db` and `gps.db` in separate files to isolate high-write tables from the main DB |

---

## 13. Clock Synchronization Strategy

### 13.1 Problem Statement

Air-gapped sBitx v2 stations may have no NTP server. The Raspberry Pi 4 has no RTC battery by default — the system clock resets to epoch (1970-01-01) on every power cycle. This means:
- `created_at` timestamps will be nonsensical until the clock is set
- Message ordering by timestamp will be incorrect

### 13.2 Clock Initialization Sequence

On boot, the system initializes the clock in this priority order:

```
1. SAVED TIMESTAMP: Read /var/lib/hermes/last_known_time
   → If file exists and timestamp > 2024-01-01: set system clock to saved time
   → This provides approximate time from last graceful shutdown

2. GPS (if available): Read NMEA sentences from GPS device
   → Parse $GPRMC or $GPGGA sentence for UTC time
   → If valid GPS time: set system clock to GPS time (accurate)
   → Set clock_synced = true, source = 'gps'

3. MANUAL FALLBACK: Prompt operator to set time
   → API endpoint POST /api/v1/system/clock/sync { "iso8601": "2026-07-17T12:00:00Z" }
   → Set system clock to manual time
   → Set clock_synced = true, source = 'manual'

4. UNKNOWN TIME: If none of the above succeed
   → System clock remains at epoch or whatever the kernel boot time is
   → API responds with clock_synced: false in health endpoint
   → created_at is stamped with current system time (may be epoch); messages are ordered by insertion order in conversation queries
   → IMPORTANT: created_at is NEVER mutated after insertion. When the clock syncs, new messages get correct timestamps. Old messages retain their original created_at. Clients sort messages by created_at within a conversation — during the unknown-time window, this means epoch-stamped messages appear at the top, then correct timestamps appear after sync. This is an acceptable UX tradeoff for field-deployed stations without reliable timekeeping.
```

### 13.3 Clock Status API

```json
// GET /api/v1/system/clock — Response 200
{
  "synced": true,
  "source": "gps",                    // "gps" | "manual" | "saved" | "unknown"
  "currentTime": "2026-07-17T12:00:00Z",
  "lastSyncAt": "2026-07-17T11:59:45Z",
  "driftSeconds": 0.1                 // Drift since last sync (from GPS only)
}

// When clock is not synced:
{
  "synced": false,
  "source": "unknown",
  "currentTime": "1970-01-01T00:00:15Z",
  "lastSyncAt": null,
  "driftSeconds": null
}
```

### 13.4 Periodic Clock Sync

| Source | Sync Interval | Notes |
|--------|:---:|-------|
| GPS | Every 30 seconds | GPS NMEA sentences include UTC time |
| Manual | On-demand (`POST /system/clock/sync`) | Operator sets via setup wizard or settings page |
| Saved | On graceful shutdown only | `last_known_time` written during shutdown sequence |

### 13.5 Client Clock Synchronization

The WebSocket `AUTHENTICATED` response includes `serverTime` so clients can calculate clock offset:

```json
{
  "type": "AUTHENTICATED",
  "payload": {
    "userId": "uuid",
    "callsign": "XA1ABC",
    "role": "operator",
    "sessionId": "uuid",
    "serverTime": "2026-07-17T12:00:00Z"
  }
}
```

The client calculates: `clockOffset = serverTime - localTime` and adjusts displayed timestamps accordingly.

---

## 14. Comparison: Old Model vs New Model

| Feature | Legacy (hermes-api SQLite) | New (SQLite — sBitx v2) |
|---------|---------------------------|--------------------------|
| Message container | inbox / outbox | conversation |
| Message format | HMP (.tar.gz) | JSON + optional envelope |
| Delivery tracking | none | per-recipient, per-channel |
| Threading | none | flat reply chains |
| Reactions | none | emoji reactions |
| Message editing | none | `edited_at` timestamp |
| Message deletion | hard delete | soft delete (`deleted_at`) |
| Attachments | separate FileController | linked to messages |
| Multi-device | none | multiple browser tabs share same DB state via REST + WebSocket |
| Email compat | native only | optional envelope abstraction |
| Group messages | none | group conversations |
| Time-series | none | daily-sharded tables in separate DB files |
| Audit trail | none | `audit_logs` immutable table |
| Job durability | none | `jobs` table for queue persistence |
| Power-loss resilience | none | WAL mode + graceful shutdown sequence |
| Clock sync | none | GPS/manual/saved timestamp initialization |

---

## Related Documents

- [REST API](api.md) — Full API endpoint documentation with request/response schemas
- [Architecture Audit](../audits/sbitx-v2.md) — Critical risks, memory budget, and hardware feasibility assessment
- [hermes-backend Architecture](https://github.com/Rhizomatica/hermes-backend) — Upstream architecture