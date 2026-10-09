# ADR-004: JWT RS256 with Refresh Token Rotation and Reuse Detection

## Status

**Accepted** (July 2026)

## Context

The Hermes Backend authenticates users (radio operators, station managers, administrators) who access the system from a browser UI, mobile device, or CLI tool. The authentication mechanism must:

- Work **offline** (no third-party OAuth providers — the station may be air-gapped)
- Support **token expiration** (15-minute access tokens, 7-day refresh tokens)
- Detect **token theft** (if a refresh token is stolen and reused, the legitimate user must be alerted)
- Operate with **minimal database load** (no Redis for session storage — SQLite `user_sessions` table)
- Support **role-based access control** (admin, operator, viewer roles encoded in JWT claims)
- Work over **HTTPS only** in production (TLS 1.2+ required)

## Decision

**JWT RS256 (RSA SHA-256) with refresh token rotation and reuse detection.**

### Token Architecture

```
┌──────────────┐                     ┌──────────────┐
│   Client     │                     │   Server     │
│  (browser)   │                     │  (Fastify)   │
└──────┬───────┘                     └──────┬───────┘
       │                                    │
       │  POST /auth/login                  │
       │  { callsign, password }            │
       │──────────────────────────────────▶ │
       │                                    │ Verify bcrypt hash
       │                                    │ Generate RSA key pair (if first run)
       │                                    │ Create user_sessions row
       │                                    │ Sign access token (RS256, 15m)
       │                                    │ Sign refresh token (RS256, 7d)
       │  { accessToken, refreshToken,      │ Store refresh token hash in DB
       │    expiresIn }                     │
       │◀────────────────────────────────── │
       │                                    │
       │  API request                       │
       │  Authorization: Bearer <access>    │
       │──────────────────────────────────▶ │
       │                                    │ Verify RS256 signature
       │                                    │ Check expiry
       │                                    │ Check RBAC claim
       │  { data }                         │
       │◀────────────────────────────────── │
       │                                    │
       │  (15 min later: access expired)    │
       │                                    │
       │  POST /auth/refresh                │
       │  { refreshToken }                  │
       │──────────────────────────────────▶ │
       │                                    │ Hash provided token
       │                                    │ Look up hash in user_sessions
       │                                    │ Check not revoked, not expired
       │                                    │ Mark old refresh as used
       │                                    │ Issue new access + refresh pair
       │                                    │ Store new refresh hash
       │  { accessToken, refreshToken,      │
       │    expiresIn }                     │
       │◀────────────────────────────────── │
```

### Refresh Token Rotation

Every `POST /auth/refresh` call:
1. Validates the provided refresh token (RS256 signature, expiry, not revoked)
2. **Marks the old refresh token as used** (one-time use)
3. Issues a **new** access token (15 min) and a **new** refresh token (7 days)
4. Stores the new refresh token hash in `user_sessions`

This means each refresh token can be used **exactly once**. If an attacker steals a refresh token and uses it, the legitimate user's next refresh attempt will fail (the old token is already marked as used). This triggers **reuse detection**.

### Reuse Detection

```typescript
// src/auth/refresh.ts
async function refreshSession(refreshToken: string): Promise<TokenPair> {
  const tokenHash = sha256(refreshToken);
  const session = await db.findSessionByRefreshHash(tokenHash);

  if (!session) {
    throw new AuthError("invalid_refresh_token");
  }

  // REUSE DETECTION: if this token was already used (replaced by a newer one)
  if (session.refresh_replaced_by) {
    // This is a stolen token! Revoke ALL sessions for this user.
    await db.revokeAllUserSessions(session.user_id);
    await auditLog.warn("refresh_token_reuse_detected", { userId: session.user_id });
    throw new AuthError("token_reuse_detected"); // 401
  }

  if (session.revoked_at || new Date(session.expires_at) < new Date()) {
    throw new AuthError("token_expired_or_revoked");
  }

  // Issue new pair
  const newAccessToken = signAccessToken({ sub: session.user_id, role: session.role });
  const newRefreshToken = signRefreshToken({ sub: session.user_id, jti: crypto.randomUUID() });
  const newRefreshHash = sha256(newRefreshToken);

  // Atomic update: mark old as replaced, insert new
  await db.transaction(async (tx) => {
    await tx.updateSession(session.id, { refresh_replaced_by: newRefreshHash });
    await tx.insertSession({
      user_id: session.user_id,
      refresh_token_hash: newRefreshHash,
      expires_at: addDays(new Date(), 7),
    });
  });

  return { accessToken: newAccessToken, refreshToken: newRefreshToken, expiresIn: 900 };
}
```

### Why RS256 (Asymmetric)

| Feature | RS256 (asymmetric) | HS256 (symmetric) |
|---------|:---:|:---:|
| Key distribution | Only public key needs to be shared | Shared secret must be distributed to all verifiers |
| Key rotation | Rotate key pair; public key can be published | Rotate secret; all services must be updated atomically |
| Future multi-station federation | Station A can verify Station B's tokens with B's public key | Requires shared secrets between stations |
| CPU cost | Higher (RSA signature verification) | Lower (HMAC) |
| **Verdict** | **Choose RS256** — enables future federation without shared secrets | |

RSA verification on a Raspberry Pi 4 (~5 million verifications/sec on Cortex-A72) is not a bottleneck. A single JWT verification takes < 1ms.

### Session Store in SQLite

```sql
CREATE TABLE user_sessions (
  id TEXT PRIMARY KEY,                  -- UUID
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash TEXT NOT NULL,     -- SHA-256 of the refresh token (never store plaintext)
  refresh_replaced_by TEXT,             -- Hash of the replacement refresh token (for reuse detection)
  device_info TEXT,                     -- JSON: user agent, IP, device name
  created_at TEXT NOT NULL,             -- ISO 8601
  expires_at TEXT NOT NULL,             -- ISO 8601
  revoked_at TEXT,                      -- NULL = active, set = manually revoked
  UNIQUE(refresh_token_hash)
);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_hash ON user_sessions(refresh_token_hash);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at);
```

### RBAC Claims in JWT

> **Correction (September 2026) — this section did not match the implementation.** The claims shown below (`permissions`, `station`) are **not issued**, and two claims that *are* issued (`callsign`, `locale`) were missing. `src/auth/token.ts` defines the real contract:
>
> | Token | Claims actually issued (`TokenPayload` / `RefreshTokenPayload`) |
> |---|---|
> | Access | `sub`, `callsign`, `role`, `locale`, `iss`, `iat`, `exp` |
> | Refresh | `sub`, `type`, `jti`, `iss`, `iat`, `exp` |
>
> `locale` is load-bearing — it is how a client learns the user's language without a second request. The decision in this ADR (RS256, rotation, reuse detection) is unchanged; only the documented claim set was wrong. Found during the Go port's re-validation (`go-migration.md` §R-6.1), where a port written against this section would have produced tokens the current UI cannot read.

```json
{
  "sub": "user-uuid-123",
  "role": "operator",
  "permissions": ["radio:control", "messages:read", "messages:write"],
  "station": "sbitx-v2-001",
  "iat": 1722000000,
  "exp": 1722000900,
  "iss": "hermes-backend"
}
```

## Consequences

### Positive

- **Offline-capable**: No external auth provider needed
- **Token theft detection**: Refresh token reuse immediately revokes all sessions
- **Stateless access tokens**: No DB lookup needed for API requests (verify signature + claims)
- **Future federation**: Asymmetric keys enable cross-station token verification
- **No Redis dependency**: Sessions stored in SQLite, acceptable for 2–3 concurrent users

### Negative

- **RSA key management**: RSA key pairs must be generated and securely stored
- **Token size**: RS256 JWTs are ~400 bytes (larger than HS256 ~200 bytes), transmitted in HTTP headers — negligible
- **Rotation complexity**: Refresh token rotation with reuse detection requires careful transaction handling
- **SQLite write load**: Each refresh creates a session row; sessions older than 7 days are cleaned up by retention

## Alternatives Considered

### HS256 (HMAC with shared secret)
Rejected: Requires shared secrets for multi-station verification in future federation. Key rotation is harder.

### OAuth 2.0 / OpenID Connect
Rejected: Requires an external identity provider. The station must operate air-gapped.

### API Keys (no expiration, no rotation)
Rejected: No expiry, no theft detection, poor security posture for a system deployed in adversarial environments.

### PASETO (Platform-Agnostic Security Tokens)
Considered but rejected: RS256 JWTs have broader ecosystem support (libraries, debugging tools). PASETO is worth revisiting if JWT-specific vulnerabilities (e.g., `alg: none` attacks) become a concern. All JWT libraries in use (`jsonwebtoken` with explicit `algorithms: ["RS256"]`) prevent these attacks.

## References

- [RFC 7519 — JSON Web Token](https://datatracker.ietf.org/doc/html/rfc7519)
- [Refresh Token Rotation](https://auth0.com/blog/refresh-tokens-what-are-they-and-when-to-use-them/)
- [docs/api.md](../architecture/api.md) §3 — Authentication endpoints
- [docs/database.md](../architecture/database.md) §3 — `users` and `user_sessions` tables