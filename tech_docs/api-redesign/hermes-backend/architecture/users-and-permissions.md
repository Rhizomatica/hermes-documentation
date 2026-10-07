# Users & Permissions — Hermes Backend

**Project**: hermes-backend
**Status**: Architecture Design — sBitx v2 (Raspberry Pi 4)
**Related Documents**: [API](./api.md), [Database](./database.md), [Security](../operations/security.md), [ADR-004](../adr/adr-004-jwt-rs256-token-rotation.md)

---

## 1. Overview

The Hermes Backend authenticates users (radio operators, station managers, administrators) who access the system from a browser UI, mobile device, or CLI tool. Authentication uses **JWT RS256 with refresh token rotation**, and authorization uses **Role-Based Access Control (RBAC)** with four roles.

The system is designed for **air-gapped field stations** — no external OAuth providers, no Redis, no PostgreSQL. All auth state lives in SQLite tables (`users`, `user_sessions`, `user_devices`).

---

## 2. User Model

### 2.1 Database Schema

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,               -- Application-generated UUID (v4 or v7)
    callsign        TEXT NOT NULL UNIQUE,           -- Amateur radio callsign or station ID (e.g., "XA1ABC")
    display_name    TEXT NOT NULL,
    email           TEXT UNIQUE,                    -- Optional: for email/SMTP interoperability
    password_hash   TEXT,                           -- bcrypt hash; NULL for remote-only station users (no local login)
    role            TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('admin', 'operator', 'user', 'readonly')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'pending')),
    avatar_path     TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',     -- JSON: extensible user metadata
    locale          TEXT NOT NULL DEFAULT 'en'
                    CHECK (locale IN ('en', 'es', 'pt-BR')),
    created_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    last_seen_at    TEXT                             -- ISO 8601 UTC
);

CREATE INDEX idx_users_callsign ON users (callsign);
CREATE INDEX idx_users_role ON users (role);
CREATE INDEX idx_users_status ON users (status);
```

### 2.2 Column Reference

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | Application-generated UUID |
| `callsign` | TEXT UNIQUE | Amateur radio callsign (e.g., `XA1ABC`). Also serves as the login identifier. |
| `display_name` | TEXT | Human-readable name (e.g., "Base Station Alpha") |
| `email` | TEXT UNIQUE | Optional email address for SMTP interop. Not used for login. |
| `password_hash` | TEXT | bcrypt hash (cost ≥ 12). NULL for remote-only station users managed via federation. |
| `role` | TEXT | `admin`, `operator`, `user`, or `readonly` (see §3) |
| `status` | TEXT | `active`, `suspended`, or `pending` |
| `avatar_path` | TEXT | Relative path to avatar image |
| `metadata` | TEXT | JSON extensible metadata blob |
| `locale` | TEXT | User's preferred language (`en`, `es`, `pt-BR`). Embedded in JWT to avoid DB query. |
| `created_at` | TEXT | ISO 8601 UTC timestamp |
| `updated_at` | TEXT | ISO 8601 UTC timestamp |
| `last_seen_at` | TEXT | ISO 8601 UTC — last activity timestamp |

### 2.3 User Status Lifecycle

```
pending → active
              ↘ suspended → active (admin reinstatement)
```

| Status | Meaning |
|--------|---------|
| `pending` | Account created but not yet activated (e.g., awaiting admin approval) |
| `active` | Normal operating state — can authenticate and use the system |
| `suspended` | Account disabled by admin. Login rejected. Existing sessions revoked. |

---

## 3. Roles & RBAC

### 3.1 Role Definitions

| Role | Description | Typical User |
|------|-------------|-------------|
| `admin` | Full system access — user management, radio control, system configuration, audit logs, reboot/shutdown | Station administrator, IT manager |
| `operator` | Radio control, send/receive messages, manage schedules and frequencies, view telemetry | Licensed radio operator, dispatcher |
| `user` | Send/receive messages, read radio status and telemetry, view schedules | Field personnel, community members |
| `readonly` | Read-only access to messages, radio status, and telemetry | Observers, auditors, trainees |

### 3.2 Complete Permission Matrix

| Feature / Endpoint | admin | operator | user | readonly |
|--------------------|:-----:|:--------:|:----:|:--------:|
| **Authentication** |||||
| Login | ✓ | ✓ | ✓ | ✓ |
| Logout (own sessions) | ✓ | ✓ | ✓ | ✓ |
| View own sessions | ✓ | ✓ | ✓ | ✓ |
| Revoke own session | ✓ | ✓ | ✓ | ✓ |
| **User Management** |||||
| List all users | ✓ | — | — | — |
| Create user | ✓ | — | — | — |
| View any user details | ✓ | — | — | — |
| Update any user | ✓ | — | — | — |
| Delete (soft-delete) any user | ✓ | — | — | — |
| View own profile (`GET /users/me`) | ✓ | ✓ | ✓ | ✓ |
| Update own profile (`PATCH /users/me`) | ✓ | ✓ | ✓ | ✓ |
| Change own locale | ✓ | ✓ | ✓ | ✓ |
| **Messaging** |||||
| Send messages | ✓ | ✓ | ✓ | — |
| Edit own messages | ✓ | ✓ | ✓ | — |
| Soft-delete own messages | ✓ | ✓ | ✓ | — |
| Delete any message | ✓ | — | — | — |
| Read conversations (participant) | ✓ | ✓ | ✓ | ✓ |
| Create conversations | ✓ | ✓ | ✓ | — |
| Add/remove participants (conversation owner) | ✓ | ✓ | ✓ | — |
| Archive conversations | ✓ | ✓ | ✓ | ✓ |
| React to messages | ✓ | ✓ | ✓ | — |
| View message delivery status | ✓ | ✓ | ✓ | ✓ |
| **Attachments** |||||
| Upload attachments | ✓ | ✓ | ✓ | — |
| Download attachments (participant) | ✓ | ✓ | ✓ | ✓ |
| Delete own attachments | ✓ | ✓ | ✓ | — |
| Delete any attachment | ✓ | — | — | — |
| **Radio Control** |||||
| View radio status | ✓ | ✓ | ✓ | ✓ |
| View radio telemetry | ✓ | ✓ | ✓ | ✓ |
| Set frequency | ✓ | ✓ | — | — |
| Set operating mode | ✓ | ✓ | — | — |
| Set volume | ✓ | ✓ | — | — |
| Switch active profile | ✓ | ✓ | — | — |
| Push-to-talk (PTT) | ✓ | ✓ | — | — |
| Stop transmission | ✓ | ✓ | — | — |
| Reset SWR protection | ✓ | ✓ | — | — |
| View radio session history | ✓ | ✓ | ✓ | ✓ |
| **Frequencies & Schedules** |||||
| List frequency presets | ✓ | ✓ | ✓ | ✓ |
| Create/update/delete frequency presets | ✓ | ✓ | — | — |
| List connection schedules | ✓ | ✓ | ✓ | ✓ |
| Create/update/delete schedules | ✓ | ✓ | — | — |
| Cancel scheduled connection | ✓ | ✓ | — | — |
| **Geolocation** |||||
| View current GPS position | ✓ | ✓ | ✓ | ✓ |
| View GPS history | ✓ | ✓ | ✓ | ✓ |
| Report GPS position | ✓ | ✓ | ✓ | — |
| **System Management** |||||
| View system configuration | ✓ | ✓ | — | — |
| Modify system configuration | ✓ | — | — | — |
| Reboot station | ✓ | — | — | — |
| Shutdown station | ✓ | — | — | — |
| Erase SD card | ✓ | — | — | — |
| View clock sync status | ✓ | ✓ | ✓ | ✓ |
| Manually set system clock | ✓ | — | — | — |
| First-time setup wizard | ✓ (one-time, no auth) | — | — | — |
| **Applications** |||||
| List installed applications | ✓ | ✓ | ✓ | ✓ |
| Install/remove/update applications | ✓ | — | — | — |
| **Audit & Monitoring** |||||
| Access audit logs | ✓ | — | — | — |
| View health endpoints | ✓ (all) | (public) | (public) | (public) |
| View Prometheus metrics | ✓ (all) | (public) | (public) | (public) |
| View `/health/stats` | ✓ | ✓ | — | — |
| View `/system/alerts` | ✓ | ✓ | — | — |
| **WebSocket** |||||
| Subscribe to `radio.telemetry` | ✓ | ✓ | ✓ | ✓ |
| Subscribe to `radio.state` | ✓ | ✓ | ✓ | ✓ |
| Subscribe to `radio.commands` | ✓ | ✓ | — | — |
| Subscribe to conversation topics | ✓ | ✓ | ✓ | ✓ |
| Subscribe to `admin.*` | ✓ | — | — | — |

---

## 4. Authentication

### 4.1 JWT Token Architecture

| Parameter | Value |
|-----------|-------|
| Algorithm | **RS256** (RSA 2048-bit keys, asymmetric) |
| Access token lifetime | **15 minutes** |
| Refresh token lifetime | **7 days** |
| Access token payload | `sub` (userId), `callsign`, `role`, `locale`, `sessionId`, `iat`, `exp`, `iss` |
| Refresh token storage | **SHA-256 hash** in `user_sessions` table (never plaintext) |
| Token transmission | `Authorization: Bearer <token>` header over HTTPS |

**Why RS256**: Asymmetric keys enable future multi-station federation — Station A can verify Station B's tokens using B's public key, with no shared secrets. RSA verification on a Raspberry Pi 4 takes < 1ms (not a bottleneck).

### 4.2 Login Flow

```
POST /api/v1/auth/login
  Body: { callsign, password }

  1. Lookup user by callsign (constant-time comparison, via Drizzle parameterized query)
  2. Verify password with bcrypt (cost factor ≥ 12)
  3. Generate access token: JWT RS256, 15 min expiry
  4. Generate refresh token: crypto.randomBytes(48) → opaque random string
  5. Store SHA-256(refreshToken) in user_sessions table (SQLite)
  6. Log audit event: auth.login
  7. Return: { accessToken, refreshToken, expiresIn: 900 }
```

**Rate limit**: 5 requests per 15 minutes per IP address.

**Failed login handling**:
- After 5 failed attempts from the same IP → 429 Too Many Requests
- Each failure logged to `audit_logs` as `auth.login_failed`
- bcrypt constant-time comparison prevents timing attacks on callsign enumeration

### 4.3 Password Policy

| Requirement | Value |
|-------------|-------|
| Hashing algorithm | bcrypt |
| Cost factor | ≥ 12 |
| Minimum length | 8 characters |
| Callsign check | Password must **not** contain the user's callsign (case-insensitive substring) |
| Common passwords | Denied: "password", "hamradio", "sbitx", "hermes", and standard blocklist |
| Complexity | Mixed case + digits + symbols **recommended** (not enforced — balances security with usability in field conditions) |

### 4.4 Token Refresh Flow

```
POST /api/v1/auth/refresh
  Body: { refreshToken }

  1. Compute SHA-256(refreshToken)
  2. Look up hash in user_sessions table
  3. Verify session not expired (expires_at > now)
  4. Verify session not revoked (revoked_at IS NULL)
  5. Check reuse detection (see §4.5)
  6. Mark old refresh token as used (set refresh_replaced_by)
  7. Issue new access token (15 min) + new refresh token (7 days)
  8. Store new refresh token SHA-256 hash in user_sessions
  9. Return: { accessToken, refreshToken, expiresIn: 900 }
```

**Rate limit**: 20 requests per hour per user.

### 4.5 Token Reuse Detection

Refresh token reuse is a signal of **token theft**. The detection mechanism works as follows:

```
Normal flow:
  Token A → refresh → Token B (A.replaced_by = B) ✓

Theft scenario:
  Token A → stolen, used by attacker → Token B issued (A.replaced_by = B)
  Legitimate user tries Token A → DB sees A.replaced_by IS NOT NULL → REUSE DETECTED

On reuse detection:
  1. Revoke ALL sessions for the user (set revoked_at on all rows)
  2. Log audit event: auth.token_reuse_detected (WARN level)
  3. Return 401 with code "token_reuse_detected"
  4. Legitimate user must re-authenticate with password
```

### 4.6 Logout Flow

```
POST /api/v1/auth/logout
  Authorization: Bearer <accessToken>

  1. Extract sessionId from JWT claims
  2. Set revoked_at = now() on the session row
  3. Log audit event: auth.logout
  4. Return 204 No Content
```

### 4.7 Session Store

```sql
CREATE TABLE user_sessions (
    id                  TEXT PRIMARY KEY,           -- Application-generated UUID
    user_id             TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    refresh_token_hash  TEXT NOT NULL UNIQUE,       -- SHA-256 of refresh token (never plaintext)
    refresh_replaced_by TEXT,                       -- Hash of the replacement refresh token (for reuse detection)
    device_id           TEXT,                       -- Links to user_devices if known
    ip_address          TEXT,
    user_agent          TEXT,
    expires_at          TEXT NOT NULL,              -- ISO 8601 UTC
    revoked_at          TEXT,                       -- ISO 8601 UTC; NULL = active
    created_at          TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE INDEX idx_user_sessions_user_id ON user_sessions (user_id);
CREATE INDEX idx_user_sessions_token_hash ON user_sessions (refresh_token_hash);
CREATE INDEX idx_user_sessions_expires_active ON user_sessions (expires_at)
    WHERE revoked_at IS NULL;
```

**Retention**: Sessions older than 7 days (expired) are cleaned up by the retention cron job. Expired sessions count toward the cleanup window; revoked sessions are retained for audit purposes.

---

## 5. Authorization

### 5.1 Middleware Chain

Every authenticated request passes through this middleware pipeline:

```
Request
  → CORS (configured allowlist, credentials enabled)
  → Helmet (security headers: CSP, XSS filter, no-sniff, referrer policy)
  → Rate Limiter (in-memory, per-IP / per-user counters)
  → JWT Verifier (extract + validate RS256 access token)
  → Locale Detector (extract locale from JWT claims → set on AsyncLocalStorage)
  → RBAC Guard (check role claim against required roles for the route)
  → Schema Validator (AJV request + response validation)
  → Controller
  → Service
  → Repository
```

### 5.2 JWT Verifier

The JWT verifier performs these checks on every request:

| Check | Failure Response |
|-------|-----------------|
| Token present in `Authorization: Bearer` header | 401 `UNAUTHENTICATED` |
| Token is a valid RS256 JWT (signature verifies with public key) | 401 `UNAUTHENTICATED` |
| Token is not expired (`exp` > now with 30s clock skew tolerance) | 401 `TOKEN_EXPIRED` |
| Token issuer is `hermes-backend` | 401 `UNAUTHENTICATED` |
| User exists and is `active` | 401 `UNAUTHENTICATED` |

### 5.3 RBAC Guard

The RBAC guard checks the `role` claim from the JWT against the route's required roles:

```
Route config: { requiredRoles: ["admin", "operator"] }

User with role "operator" → allowed ✓
User with role "user" → 403 FORBIDDEN ✗
User with role "readonly" → 403 FORBIDDEN ✗
```

**Implementation**: Routes declare required roles via Fastify schema or route options. The RBAC guard checks `requiredRoles.includes(jwtPayload.role)`. Role hierarchy is **flat** — there is no inheritance (e.g., `admin` does not automatically have `operator` permissions; `admin` is explicitly included in every permission set).

### 5.4 Error Responses

| HTTP Status | Code | Meaning |
|:---:|------|---------|
| 401 | `UNAUTHENTICATED` | Missing or invalid access token |
| 401 | `TOKEN_EXPIRED` | Access token has expired (client should refresh) |
| 401 | `TOKEN_REUSE_DETECTED` | Refresh token was stolen and reused — all sessions revoked |
| 403 | `FORBIDDEN` | User's role does not permit this operation |
| 429 | `RATE_LIMITED` | Too many requests (see rate limiting) |

**RFC 7807 Response Format**:

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

> **Localization**: The `message` field (and `details[].message`) are localized based on the user's `locale`. The `code` field is a machine-readable identifier (never translated). The `title` field stays in English (RFC 7807 convention).

---

## 6. API Endpoints (User & Auth)

### 6.1 Authentication Endpoints — `/api/v1/auth`

| Method | Path | Description | Auth Required | Rate Limit |
|--------|------|-------------|:---:|:---:|
| `POST` | `/auth/login` | Login with callsign + password | No | 5 / 15 min / IP |
| `POST` | `/auth/refresh` | Refresh access token | No | 20 / hour / user |
| `POST` | `/auth/logout` | Revoke current session | Yes | — |
| `GET` | `/auth/sessions` | List active sessions for current user | Yes | — |
| `DELETE` | `/auth/sessions/:id` | Revoke a specific session | Yes | — |

### 6.2 User Endpoints — `/api/v1/users`

| Method | Path | Description | Required Role |
|--------|------|-------------|:---:|
| `GET` | `/users` | List users (paginated) | admin |
| `POST` | `/users` | Create user | admin |
| `GET` | `/users/:id` | Get user details | admin, or self |
| `PATCH` | `/users/:id` | Update user | admin, or self |
| `DELETE` | `/users/:id` | Soft-delete user | admin |
| `GET` | `/users/me` | Get current user profile | All authenticated |

**Request/Response examples**:

```json
// POST /api/v1/users — Request
{
  "callsign": "XA1DEF",
  "displayName": "Station Delta",
  "email": "delta@example.com",
  "password": "secure-password",
  "role": "user",
  "locale": "es"
}

// GET /api/v1/users/me — Response 200
{
  "id": "uuid",
  "callsign": "XA1ABC",
  "displayName": "Base Station Alpha",
  "email": "alpha@example.com",
  "role": "operator",
  "status": "active",
  "locale": "en",
  "lastSeenAt": "2026-07-17T12:00:00Z",
  "createdAt": "2026-01-01T00:00:00Z"
}

// PATCH /api/v1/users/me — Request (locale change)
{
  "locale": "es"
}
// Note: Changing locale invalidates all existing JWTs (tokens carry old locale).
// Client must re-authenticate with new locale.
```

---

## 7. Devices

### 7.1 Device Tracking

The `user_devices` table tracks registered devices per user for push notifications and session management:

```sql
CREATE TABLE user_devices (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    device_name     TEXT NOT NULL,
    device_type     TEXT NOT NULL
                    CHECK (device_type IN ('mobile', 'desktop', 'station', 'browser')),
    push_token      TEXT,                           -- FCM/APNs token for push notifications
    platform        TEXT,                           -- ios | android | web | linux
    last_seen_at    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX idx_user_devices_user_id ON user_devices (user_id);
```

### 7.2 Device Endpoints — `/api/v1/devices`

| Method | Path | Description | Required Role |
|--------|------|-------------|:---:|
| `GET` | `/devices` | List current user's devices | All |
| `POST` | `/devices` | Register a device | All |
| `PATCH` | `/devices/:id` | Update device (e.g., push token) | Device owner |
| `DELETE` | `/devices/:id` | Remove device | Device owner |

---

## 8. Audit Logging

All security-relevant user actions are written to the immutable, append-only `audit_logs` table:

```sql
CREATE TABLE audit_logs (
    id              TEXT PRIMARY KEY,
    actor_id        TEXT REFERENCES users (id) ON DELETE SET NULL,
    action          TEXT NOT NULL,                  -- e.g., 'auth.login', 'user.role_changed'
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    old_value       TEXT,                           -- JSON
    new_value       TEXT,                           -- JSON
    ip_address      TEXT,
    user_agent      TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',
    locale          TEXT NOT NULL DEFAULT 'en',
    created_at      TEXT NOT NULL
);
```

### Audited Actions

| Action | Description | Logged Fields |
|--------|-------------|---------------|
| `auth.login` | Successful login | user_id, ip_address, user_agent |
| `auth.login_failed` | Failed login attempt | callsign (attempted), ip_address, reason |
| `auth.logout` | Session revoked | user_id, session_id |
| `auth.token_refresh` | Token rotation performed | user_id, session_id |
| `auth.token_reuse_detected` | Stolen token detected — all sessions revoked | user_id, all affected session_ids |
| `auth.unauthorized_access` | RBAC violation — user attempted restricted operation | user_id, attempted_endpoint, required_role |
| `user.created` | New user created | created_by, new_user_id, role |
| `user.updated` | User modified | changed_by, user_id, changed_fields |
| `user.deleted` | User soft-deleted | changed_by, user_id |
| `user.role_changed` | Role escalation or demotion | changed_by, user_id, old_role → new_role |

**Access**: Audit logs are accessible only to `admin` users. Retention: 2 years (configurable via `RETENTION_AUDIT_DAYS`).

---

## 9. Rate Limiting

All rate limits are implemented as **in-memory counters** (no Redis). Counters reset on process restart — an acceptable tradeoff for single-station Pi 4 deployments.

| Endpoint | Limit | Window | Scope |
|----------|:---:|:---:|-------|
| `POST /auth/login` | 5 | 15 min | Per IP |
| `POST /auth/refresh` | 20 | 1 hour | Per user |
| `POST /users` (user creation) | 3 | 1 hour | Per IP (admin) |
| REST API (general) | 300 | 1 min | Per user |
| REST API (radio commands) | 60 | 1 min | Per user |
| File upload | 20 | 1 hour | Per user |
| WebSocket messages | 60 | 1 min | Per connection |
| WebSocket `TYPING_START` | 1 | 2 sec | Per conversation per connection |

Rate limit responses return `429 Too Many Requests` with `Retry-After` header.

---

## 10. Locale & Internationalization

### 10.1 Locale Resolution

User language preference is determined by this fallback chain:

1. **JWT `locale` claim** — user's persisted preference (set via `PATCH /users/me`)
2. **`Accept-Language` HTTP header** — browser preference for unauthenticated requests
3. **Fallback**: `en` (English)

### 10.2 Supported Languages

| Code | Language | Priority |
|------|----------|:---:|
| `en` | English | P0 (fallback) |
| `es` | Español | P0 |
| `pt-BR` | Português (Brasil) | P1 |

### 10.3 Locale in JWT

The `locale` claim is embedded in the JWT to avoid a database query on every request for language preference:

```json
{
  "sub": "user-uuid-123",
  "callsign": "XA1ABC",
  "role": "operator",
  "locale": "es",
  "sessionId": "session-uuid",
  "iat": 1722000000,
  "exp": 1722000900,
  "iss": "hermes-backend"
}
```

**Important**: When a user changes their locale via `PATCH /users/me`, all existing JWTs are invalidated (they carry the old locale). The client must re-authenticate to receive tokens with the new locale.

---

## 11. Key Management

### 11.1 RSA Key Pair

| Aspect | Detail |
|--------|--------|
| Generation | Automatically on first run if `JWT_PRIVATE_KEY_PATH` doesn't exist |
| Algorithm | RSA 2048-bit |
| Storage | PEM files at configured paths (`JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`) |
| Private key permissions | `chmod 600`, owned by the hermes-backend process user |
| Public key | Readable by the process; can be distributed for federation |
| Rotation | Key rotation supported — new key pair invalidates all existing tokens; clients re-auth |

### 11.2 JWT Verification

```typescript
// All JWT libraries configured with explicit algorithm restriction:
jwt.verify(token, publicKey, {
  algorithms: ["RS256"],         // Only RS256 accepted
  issuer: "hermes-backend",
  clockTolerance: 30,            // 30-second clock skew tolerance
});
```

---

## 12. First-Time Setup

### 12.1 Setup Wizard

The initial setup creates the admin user and configures the station:

```
POST /api/v1/setup  (no auth required — one-time only)

Request:
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
    "password": "secure-admin-password",
    "locale": "es"
  },
  "networkSettings": {
    "hostname": "hermes-alpha",
    "dhcp": true
  }
}
```

- After successful setup, the endpoint returns 201 and subsequent calls return 409 `CONFLICT`
- The admin user is created with `role=admin` and `status=active`
- Locale is detected from `Accept-Language` header for the wizard UI; admin user's locale is set explicitly in the payload

### 12.2 Setup Status Check

```
GET /api/v1/setup/status  (no auth)

Response 200 (not set up):
{ "configured": false }

Response 200 (already configured):
{ "configured": true, "setupCompletedAt": "2026-07-17T12:00:00Z" }
```

---

## 13. Security Considerations

### 13.1 Authentication

- **bcrypt cost ≥ 12**: Slows brute-force attempts on Pi 4 (~300ms per hash)
- **Constant-time callsign lookup**: Prevents timing-based user enumeration
- **Refresh tokens never stored as plaintext**: Only SHA-256 hashes in the database
- **No session IDs in URLs**: All auth via `Authorization` header or secure httpOnly cookies

### 13.2 Authorization

- **Flat role hierarchy**: No implicit inheritance — each endpoint explicitly lists allowed roles
- **RBAC at middleware level**: Authorization happens before any business logic executes
- **Audit on violation**: Every 403 `FORBIDDEN` response logs an `auth.unauthorized_access` event
- **Role changes invalidate sessions**: When an admin changes a user's role, all active sessions for that user are revoked

### 13.3 Session Management

- **Token rotation**: Each refresh invalidates the previous refresh token
- **Reuse detection**: Stolen refresh token triggers full session revocation
- **Session listing**: Users can view and revoke their own sessions
- **Automatic expiry**: Sessions older than 7 days are cleaned up

### 13.4 Input Validation

| Field | Constraint | Enforcement |
|-------|------------|-------------|
| `callsign` | max 20 chars | JSON Schema / AJV |
| `displayName` | max 100 chars | JSON Schema / AJV |
| `password` | min 8 chars, must not contain callsign, deny common passwords | Application logic |
| `email` | valid email format if provided | JSON Schema / AJV |
| `locale` | must be `en`, `es`, or `pt-BR` | JSON Schema / AJV + DB CHECK |
| `role` (on create) | must be `admin`, `operator`, `user`, or `readonly` | JSON Schema / AJV + DB CHECK |

### 13.5 SQL Injection Prevention

All user lookup and session queries use **Drizzle ORM parameterized queries**. No raw SQL with string interpolation is used in application code.

```typescript
// ✅ Safe: parameterized query
const user = await db.select().from(users).where(eq(users.callsign, inputCallsign));

// ❌ Forbidden
const user = await db.run(`SELECT * FROM users WHERE callsign = '${inputCallsign}'`);
```

---

## 14. Implementation Notes

### 14.1 Files (Phase 1 — to be implemented)

```
src/
├── api/
│   └── v1/
│       ├── auth/
│       │   ├── login.ts              # POST /auth/login
│       │   ├── login.schema.ts       # JSON Schema for login
│       │   ├── refresh.ts            # POST /auth/refresh
│       │   ├── logout.ts             # POST /auth/logout
│       │   └── sessions.ts           # GET/DELETE /auth/sessions
│       └── users/
│           ├── list.ts               # GET /users (admin)
│           ├── create.ts             # POST /users (admin)
│           ├── get.ts                # GET /users/:id
│           ├── update.ts             # PATCH /users/:id
│           ├── delete.ts             # DELETE /users/:id
│           └── me.ts                 # GET /users/me, PATCH /users/me
├── auth/
│   ├── password.ts                   # bcrypt hash/verify, password validation
│   ├── token.ts                      # JWT sign/verify (RS256)
│   ├── refresh.ts                    # Refresh token rotation + reuse detection
│   └── middleware/
│       ├── jwt-verifier.ts           # JWT extraction + validation
│       └── rbac-guard.ts             # Role check against required roles
├── db/
│   └── repositories/
│       ├── users.repository.ts       # User CRUD
│       ├── sessions.repository.ts    # Session CRUD + revocation
│       └── devices.repository.ts     # Device CRUD
└── i18n/
    ├── index.ts                      # Locale detector, t() function
    └── resources/
        ├── en/
        │   └── errors.json           # English error messages
        ├── es/
        │   └── errors.json           # Spanish error messages
        └── pt-BR/
            └── errors.json           # Portuguese (Brazil) error messages
```

### 14.2 Key Dependencies

| Package | Purpose |
|---------|---------|
| `@fastify/jwt` | JWT sign/verify with RS256 |
| `bcrypt` | Password hashing (cost ≥ 12) |
| `drizzle-orm` | Parameterized SQLite queries |
| `@fastify/cors` | CORS configuration |
| `@fastify/helmet` | Security headers |
| `@fastify/rate-limit` | In-memory rate limiting |

### 14.3 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_PRIVATE_KEY_PATH` | Path to RSA private key PEM file | `./keys/private.pem` |
| `JWT_PUBLIC_KEY_PATH` | Path to RSA public key PEM file | `./keys/public.pem` |
| `JWT_ACCESS_EXPIRES_IN` | Access token lifetime in seconds | `900` (15 min) |
| `JWT_REFRESH_EXPIRES_IN` | Refresh token lifetime in seconds | `604800` (7 days) |
| `BCRYPT_COST` | bcrypt cost factor | `12` |
| `RATE_LIMIT_LOGIN_MAX` | Max login attempts per window | `5` |
| `RATE_LIMIT_LOGIN_WINDOW_MS` | Login rate limit window | `900000` (15 min) |

---

## Related Documents

- [API Reference](./api.md) — Full REST API endpoint documentation
- [Database Schema](./database.md) — Complete SQLite schema with all tables
- [Security Model](../operations/security.md) — Threat model, TLS, input validation
- [ADR-004: JWT RS256 Token Rotation](../adr/adr-004-jwt-rs256-token-rotation.md) — Full design decision record
- [Development Plan](../development/plan.md) — Phase 1 implementation tasks
- [Internationalization](../development/i18n.md) — Full i18n strategy