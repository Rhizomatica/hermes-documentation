# Testing Strategy — Hermes Backend

## Philosophy

Testing is mandatory, not optional. All code merged into `main` must have corresponding tests. We target **≥ 80% line coverage** across the entire codebase, enforced in CI.

The testing strategy follows the **testing trophy** model (integration-heavy) rather than the testing pyramid, because Hermes is a data-intensive application where most complexity lives at the API ↔ database boundary.

```
        ╱ E2E ╲               Critical user flows only
       ╱───────╲              (auth → message → WebSocket)
      ╱         ╲
     ╱ Integration ╲          All API endpoints + DB queries
    ╱───────────────╲         (SQLite in-memory, simulated HAL)
   ╱                 ╲
  ╱    Unit Tests      ╲      Pure logic, utilities, validation
 ╱───────────────────────╲    (no I/O, no database)
```

## Test Types

### 1. Unit Tests (`tests/unit/`)

**What they test**: Pure functions with no side effects. No database, no file system, no network.

**Examples**:
- Password hashing/verification (bcrypt)
- JWT sign/verify utilities
- Input validation (Zod schemas, `maxLength` enforcement)
- Idempotency key logic (`client_message_id`)
- Clock sync strategy logic
- GPS NMEA sentence parsing
- Retention policy date calculations

**Mocking**: None needed — these are pure functions.

**Runner**: Vitest with default isolation.

```typescript
// tests/unit/auth/password.test.ts
import { describe, it, expect } from "vitest";
import { hashPassword, verifyPassword } from "../../src/auth/password.js";

describe("Password Hashing", () => {
  it("should hash and verify a password", async () => {
    const hash = await hashPassword("secure-password");
    expect(hash).not.toBe("secure-password");
    expect(await verifyPassword("secure-password", hash)).toBe(true);
  });

  it("should reject incorrect password", async () => {
    const hash = await hashPassword("correct");
    expect(await verifyPassword("wrong", hash)).toBe(false);
  });

  it("should enforce bcrypt cost >= 12", async () => {
    const hash = await hashPassword("test");
    // bcrypt cost 12 hashes start with $2b$12$
    expect(hash.startsWith("$2b$12$")).toBe(true);
  });
});
```

### 2. Integration Tests (`tests/integration/`)

**What they test**: API endpoints with a real SQLite in-memory database and a real Fastify server instance — but no network, no real radio.

**Examples**:
- `POST /auth/login` → returns JWT tokens
- `POST /auth/refresh` → token rotation with reuse detection
- `GET /conversations` → paginated list with unread counts
- `POST /conversations/:id/messages` → idempotent message creation
- `DELETE /conversations/:id/messages/:msgId` → soft delete
- WebSocket `AUTHENTICATE` → `AUTHENTICATED` handshake
- Rate limiting enforcement on auth routes

**Infrastructure**:
- SQLite `:memory:` database (no disk I/O)
- Real Drizzle ORM + migrations (applied per-test or per-suite)
- Fastify instance built via `app.build()`
- Requests sent via `app.inject()` (Fastify's built-in test utility — no Supertest needed for most cases)
- `SimulatedRadioDriver` for HAL-dependent endpoints

```typescript
// tests/integration/auth/login.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import type { FastifyInstance } from "fastify";

describe("POST /auth/login", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = await buildApp({ database: ":memory:", radioDriver: "simulated" });
    await app.ready();
    // Seed test user
    await app.inject({
      method: "POST",
      url: "/users",
      payload: { callsign: "TEST1", password: "secure-password" },
    });
  });

  afterAll(async () => {
    await app.close();
  });

  it("should return JWT tokens for valid credentials", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/auth/login",
      payload: { callsign: "TEST1", password: "secure-password" },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body).toHaveProperty("accessToken");
    expect(body).toHaveProperty("refreshToken");
    expect(body).toHaveProperty("expiresIn");
  });

  it("should return 401 for invalid password", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/auth/login",
      payload: { callsign: "TEST1", password: "wrong" },
    });
    expect(res.statusCode).toBe(401);
  });

  it("should be rate-limited after 5 consecutive failures", async () => {
    for (let i = 0; i < 5; i++) {
      await app.inject({
        method: "POST",
        url: "/auth/login",
        payload: { callsign: "TEST1", password: "wrong" },
      });
    }
    const res = await app.inject({
      method: "POST",
      url: "/auth/login",
      payload: { callsign: "TEST1", password: "secure-password" },
    });
    expect(res.statusCode).toBe(429);
  });
});
```

### 3. End-to-End Tests (`tests/e2e/`)

**What they test**: Multi-step user flows across HTTP + WebSocket. These tests spin up a real server on a random port and connect via WebSocket.

**Examples**:
- Full auth flow: register → login → refresh → logout → reuse detection
- Message flow: create conversation → send message → WebSocket receives `MESSAGE_NEW` → edit → WebSocket receives `MESSAGE_EDITED` → delete
- Offline sync: disconnect WebSocket → send messages → reconnect → receive `SYNC_DELTA` batch

**Infrastructure**:
- Real Fastify `app.listen()` on a random port
- Real WebSocket client (`ws` library)
- SQLite file database (not in-memory, to verify file-based behavior)
- `SimulatedRadioDriver`

```typescript
// tests/e2e/message-flow.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import WebSocket from "ws";

describe("Message Flow E2E", () => {
  let serverUrl: string;
  let accessToken: string;
  let conversationId: string;

  beforeAll(async () => {
    // Start server, create user, login, create conversation
  });

  it("should deliver new message via WebSocket", async () => {
    const ws = new WebSocket(`${serverUrl}/gateway`, ["hermes-v1"]);
    const wsMessages: unknown[] = [];

    ws.on("message", (data) => {
      wsMessages.push(JSON.parse(data.toString()));
    });

    // Authenticate WebSocket
    ws.send(JSON.stringify({ type: "AUTHENTICATE", token: accessToken }));

    // Subscribe to conversation
    ws.send(JSON.stringify({ type: "SUBSCRIBE", topics: [`conversation:${conversationId}`] }));

    // Send message via HTTP
    await fetch(`${serverUrl}/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ content: "Hello from E2E!" }),
    });

    // Wait for WebSocket event
    await new Promise((r) => setTimeout(r, 200));
    expect(wsMessages).toContainEqual(
      expect.objectContaining({ type: "MESSAGE_NEW" }),
    );
  });
});
```

## Test Database Strategy

| Test Type | Database | Rationale |
|-----------|----------|-----------|
| **Unit** | None | No database access |
| **Integration** | SQLite `:memory:` | Fastest; no filesystem; fresh per test |
| **E2E** | SQLite file (`/tmp/test-*.sqlite`) | Verifies WAL behavior, file persistence |

For integration tests, migrations are applied once per test file (`beforeAll`) and the database is discarded in `afterAll`. This is fast enough for SQLite (migrations take < 100ms).

```typescript
// tests/helpers/db.ts
import { migrate } from "drizzle-orm/better-sqlite3/migrator";
import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";

export function createTestDb() {
  const sqlite = new Database(":memory:");
  sqlite.pragma("journal_mode=WAL");
  sqlite.pragma("foreign_keys=ON");
  const db = drizzle(sqlite);
  migrate(db, { migrationsFolder: "./drizzle" });
  return { sqlite, db };
}
```

## Simulated HAL for Testing

All HAL-dependent tests use `SimulatedRadioDriver`:

```typescript
// tests/helpers/hal.ts
import { SimulatedRadioDriver } from "../../src/hal/simulated-driver.js";

export function createSimulatedRadio(overrides?: Partial<RadioState>) {
  return new SimulatedRadioDriver({
    frequency: 7100,     // kHz (40m band)
    power: 10,           // watts
    swr: 1.2,
    temperature: 35,     // °C
    connected: true,
    ...overrides,
  });
}
```

## Coverage Targets

| Module | Target | Enforced |
|--------|:---:|:---:|
| `src/auth/` | ≥ 85% | CI |
| `src/db/repositories/` | ≥ 80% | CI |
| `src/api/v1/` | ≥ 80% | CI |
| `src/messaging/` | ≥ 80% | CI |
| `src/hal/` | ≥ 85% | CI |
| `src/clock/` | ≥ 85% | CI |
| `src/resilience/` | ≥ 80% | CI |
| **Overall** | **≥ 80%** | **CI** |

Excluded from coverage:
- `src/server.ts` (entry point)
- `src/db/migrations/` (auto-generated by Drizzle)

## Running Tests

```bash
# All tests (unit + integration + e2e)
npm test

# Unit tests only (fastest)
npx vitest run tests/unit/

# Integration tests only
npx vitest run tests/integration/

# E2E tests only (slowest)
npx vitest run tests/e2e/

# Watch mode for TDD
npm run test:watch

# Coverage report
npm run test:coverage
# Open coverage/index.html in browser
```

## Testing Patterns

### Idempotency Tests

Every write endpoint with a `client_message_id` must have an idempotency test:

```typescript
it("should return same result for repeated client_message_id", async () => {
  const payload = { content: "Hello", clientMessageId: "abc-123" };
  const res1 = await app.inject({
    method: "POST", url: "/conversations/conv-1/messages", payload,
  });
  const res2 = await app.inject({
    method: "POST", url: "/conversations/conv-1/messages", payload,
  });
  expect(res2.statusCode).toBe(200);       // Not 409
  expect(res2.json().id).toBe(res1.json().id); // Same message ID
});
```

### Boundary Tests

All string fields with `maxLength` constraints must be tested:

```typescript
it("should reject messages exceeding 64 KB", async () => {
  const hugeMessage = "x".repeat(65537); // 64 KB + 1 byte
  const res = await app.inject({
    method: "POST",
    url: `/conversations/conv-1/messages`,
    payload: { content: hugeMessage },
  });
  expect(res.statusCode).toBe(400);
});

it("should accept messages at exactly 64 KB", async () => {
  const maxMessage = "x".repeat(65536); // Exactly 64 KB
  const res = await app.inject({
    method: "POST",
    url: `/conversations/conv-1/messages`,
    payload: { content: maxMessage },
  });
  expect(res.statusCode).toBe(200);
});
```

### Participant Limit Enforcement

```typescript
it("should enforce 50-participant limit on group conversations", async () => {
  // Create group conversation, add 50 participants
  // Attempt to add 51st
  const res = await app.inject({
    method: "POST",
    url: `/conversations/${groupId}/participants`,
    payload: { callsign: "USER51" },
  });
  expect(res.statusCode).toBe(400);
});
```

### Token Rotation & Reuse Detection

```typescript
it("should detect refresh token reuse and revoke all sessions", async () => {
  const { refreshToken } = await login("USER1", "password");
  const refresh1 = await refreshSession(refreshToken);   // Valid
  const refresh2 = await refreshSession(refreshToken);   // Reuse detected
  expect(refresh2.statusCode).toBe(401);
  expect(refresh2.json().error).toBe("token_reuse_detected");

  // Verify all sessions revoked — even refresh1's new token is invalid
  const refresh3 = await refreshSession(refresh1.refreshToken);
  expect(refresh3.statusCode).toBe(401);
});
```

## Performance Tests

Performance tests verify that critical operations meet latency targets on Pi 4:

| Operation | Target Latency | Test Method |
|-----------|:---:|---|
| Conversation list (100 convos, 50 messages each) | < 50ms | Integration with seeded data |
| Message send with delivery tracking | < 30ms | Integration |
| Telemetry query (24h range, 1 Hz data) | < 100ms | Integration with seeded telemetry |
| WebSocket event delivery latency | < 50ms p99 | E2E |

## CI Integration

Tests run on every PR and push to `main`/`develop`. See [docs/ci-cd.md](ci-cd.md) for pipeline details.

All test types run in CI. E2E tests that require a real filesystem use SQLite with a temporary file in the CI runner's `/tmp`.