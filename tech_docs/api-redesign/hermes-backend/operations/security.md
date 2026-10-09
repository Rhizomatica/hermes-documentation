# Security Model — Hermes Backend

## Threat Model

The Hermes Backend operates in **field conditions** — remote locations with unreliable infrastructure. The threat model considers:

| Threat Actor | Capability | Motivation |
|-------------|------------|------------|
| **Unauthorized local user** | Physical access to the Pi 4, no credentials | Intercept communications, tamper with station config |
| **Remote attacker on LAN** | Network access to the station's Wi-Fi/hotspot | Exploit unpatched vulnerabilities, brute-force credentials |
| **HF eavesdropper** | Receiving HF radio signals (3–30 MHz) | Intercept radio traffic (inherent to HF — not preventable at this layer) |
| **Compromised client device** | Stolen or infected laptop/phone with valid credentials | Exfiltrate messages, impersonate legitimate operator |

### What We Don't Protect Against

- **HF radio eavesdropping**: HF is a shared medium. Encryption at the transport layer is out of scope for the backend. Future work: application-layer E2E encryption (Signal Protocol) for sensitive messages.
- **Physical tampering with sBitx hardware**: The Pi 4 SD card can be removed and read. Future work: full-disk encryption (LUKS) on the SD card.
- **Side-channel attacks**: Power analysis, timing attacks on the Pi 4 are out of scope for a field-deployed humanitarian communication tool.

## Authentication & Authorization

### JWT RS256 (Asymmetric)

| Parameter | Value |
|-----------|-------|
| Algorithm | RS256 (RSA 2048-bit keys) |
| Access token lifetime | 15 minutes |
| Refresh token lifetime | 7 days |
| Token claims | `sub` (userId), `callsign`, `role`, `locale`, `sessionId`, `iat`, `exp` |
| Token storage | Refresh token **SHA-256 hashes** in SQLite `user_sessions` |
| Token transmission | `Authorization: Bearer <token>` header over HTTPS |

The `locale` claim (`en`, `es`, or `pt-BR`) is embedded in the JWT to avoid database queries on every request for language preference. Changing the user's locale via `PATCH /users/me` invalidates all existing tokens (they carry the old locale) — the client must re-authenticate.

See [ADR-004](adr/adr-004-jwt-rs256-token-rotation.md) for the full token rotation and reuse detection design.

### Password Policy

| Requirement | Value |
|-------------|-------|
| Hashing algorithm | bcrypt |
| Cost factor | ≥ 12 |
| Minimum length | 8 characters |
| Brute-force protection | Rate-limited: 5 attempts/minute per IP on `/auth/login` |

### RBAC Roles

| Role | Permissions |
|------|------------|
| `admin` | Full system access: user management, radio control, system config, all messages |
| `operator` | Radio control, send/receive messages, view telemetry |
| `viewer` | Read-only: view messages, telemetry; cannot send or control radio |

## Transport Security

### TLS

| Requirement | Value |
|-------------|-------|
| Minimum version | TLS 1.2 (TLS 1.0/1.1 rejected) |
| Cipher preference | Server-side |
| Certificate | Self-signed acceptable for LAN-only deployments; Let's Encrypt if internet available |
| HSTS | Enabled in production (`Strict-Transport-Security: max-age=31536000`) |

### CORS

```typescript
// Default CORS policy
const corsOptions = {
  origin: process.env.CORS_ORIGINS.split(","),  // e.g., "http://localhost:5173,http://sbitx.local:3001"
  methods: ["GET", "POST", "PATCH", "DELETE"],
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true,
  maxAge: 86400, // 24 hours
};
```

### HTTP Security Headers (Helmet)

Fastify Helmet enables:

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | `default-src 'self'` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `0` (deprecated, CSP handles this) |
| `Referrer-Policy` | `no-referrer` |
| `X-DNS-Prefetch-Control` | `off` |

## Rate Limiting

All limits are implemented as **in-memory counters** (no Redis). Counters reset on process restart — acceptable for single-station Pi 4 deployment.

| Endpoint | Limit | Window |
|----------|:---:|:---:|
| `POST /auth/login` | 5 | 1 minute per IP |
| `POST /auth/refresh` | 10 | 1 minute per user |
| `POST /users` (user creation) | 3 | 1 hour per IP |
| `POST /conversations/:id/messages` | 30 | 1 minute per user |
| WebSocket connections | 10 | Concurrent (hard cap) |
| Global (all other endpoints) | 100 | 1 minute per IP |

Rate limit responses return `429 Too Many Requests` with `Retry-After` header.

## Input Validation

### Request Validation

All request bodies are validated against **JSON Schema** via Fastify's built-in AJV validator:

```typescript
// Example: POST /conversations/:id/messages schema
const createMessageSchema = {
  body: {
    type: "object",
    required: ["content"],
    properties: {
      content: { type: "string", maxLength: 65536 },   // 64 KB
      clientMessageId: { type: "string", maxLength: 64 },
      attachments: { type: "array", maxItems: 10 },
    },
  },
};
```

### String Length Constraints

All string fields have `maxLength` enforced at the schema level. See `docs/api.md` for per-endpoint limits.

### File Upload Validation

| Constraint | Value |
|------------|-------|
| Max file size | 50 MB (streaming, not buffered in memory) |
| Allowed MIME types | Configurable allowlist |
| SHA-256 checksum | Computed on upload; deduplicates identical files |
| Malware scanning | Not performed (field deployment, no AV available for Pi 4 ARM) |

## SQL Injection Prevention

**All database queries use Drizzle ORM's parameterized query builder.** No raw SQL strings with interpolation.

```typescript
// ✅ Safe: Drizzle parameterized query
const user = await db.select().from(users).where(eq(users.callsign, inputCallsign));

// ❌ Forbidden: Raw SQL with interpolation
const user = await db.run(`SELECT * FROM users WHERE callsign = '${inputCallsign}'`);
```

Raw SQL is only permitted in Drizzle migration files (auto-generated, not user-facing).

## CLI Command Injection Prevention (HAL)

All sBitx CLI commands use `child_process.execFile` with **argument arrays** — never string interpolation:

```typescript
// ✅ Safe: argument array (no shell)
import { execFile } from "node:child_process";
execFile("/usr/local/bin/sbitx", ["set-frequency", "7100"], { timeout: 5000 });

// ❌ Forbidden: string with shell interpolation
exec(`/usr/local/bin/sbitx set-frequency ${userInput}`);
```

## Dependency Management

- `npm audit` runs nightly in CI (see [docs/ci-cd.md](ci-cd.md))
- High/Critical vulnerabilities block releases
- Dependencies are pinned to exact versions in `package-lock.json`
- Native modules (`better-sqlite3`, `bcrypt`) are built from source on the Pi 4

## Audit Logging

All security-relevant events are written to the `audit_logs` table:

| Event | Logged Fields |
|-------|---------------|
| `auth_login_success` | user_id, ip_address |
| `auth_login_failure` | callsign, ip_address, reason |
| `auth_token_refresh` | user_id, session_id |
| `auth_token_reuse_detected` | user_id, session_id (all sessions revoked) |
| `user_created` | created_by, new_user_id |
| `user_role_changed` | changed_by, user_id, old_role, new_role |
| `radio_command` | user_id, command, frequency, power |
| `system_config_changed` | user_id, key, old_value_hash, new_value_hash |

Audit logs are **immutable, append-only**. No deletions. Retention: 2 years (configurable via `RETENTION_AUDIT_DAYS`).

## Key Management

### RSA Key Pair

- Generated on first run if `JWT_PRIVATE_KEY_PATH` doesn't exist
- Stored as PEM files at configured paths
- Private key: `chmod 600`, owned by the hermes-backend process user
- Public key: readable by the process, can be distributed for federation

### TLS Certificates

- Development: self-signed certificate generated on first run
- Production (LAN): self-signed or CA-signed certificate
- Production (internet-connected): Let's Encrypt via certbot

## Incident Response

In the event of a security incident:

1. **Token theft detected**: Refresh token reuse automatically revokes all user sessions (ADR-004)
2. **Compromised credential**: Admin changes user password and revokes all sessions via `POST /users/:id/revoke-sessions`
3. **Physical breach**: SD card can be removed — full-disk encryption is a future hardening item
4. **Suspicious activity**: Audit logs queryable via admin endpoints; exportable for offline analysis

## Security Checklist (Pre-Deployment)

- [ ] RSA key pair generated and private key permission set to `600`
- [ ] TLS certificate installed (even self-signed for LAN)
- [ ] Default admin password changed from any initial setup default
- [ ] CORS origins restricted to known clients
- [ ] Rate limits configured for Pi 4 capacity
- [ ] `NODE_ENV=production` set (disables stack traces in error responses)
- [ ] Helmet enabled with appropriate CSP
- [ ] Audit logging enabled and retention policy set
- [ ] `npm audit` shows zero high/critical vulnerabilities