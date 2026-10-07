# Hermes Backend — Development Guide

## Prerequisites

| Tool | Minimum Version | Notes |
|------|:---:|-------|
| Node.js | 20 LTS (20.19) | Required for ESM, `node:test` runner compatibility; matches Debian 13 Trixie |
| npm | 10+ | Ships with Node.js 20 |
| Git | 2.40+ | |
| SQLite | 3.45+ | For WAL mode support; ships with most Linux distros |

### Raspberry Pi 4 Hardware (Optional)

For on-device testing with the sBitx v2:
- Raspberry Pi 4 (4 GB RAM)
- Raspberry Pi OS (Bookworm, 64-bit)
- sBitx v2 hardware connected

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Rhizomatica/hermes-backend.git
cd hermes-backend

# 2. Install dependencies
npm install

# 3. Generate JWT RS256 key pair (required for authentication)
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem

# 4. Set up environment
cp .env.example .env
# Edit .env — adjust DATABASE_PATH, RADIO_DRIVER=simulated, etc.

# 5. Run database migrations
npm run db:migrate

# 6. Start development server (hot-reload)
npm run dev

# 7. Verify the server is running
curl http://localhost:3000/health
```

## Project Structure

```
hermes-backend/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
├── package.json
├── tsconfig.json
├── eslint.config.js
├── vitest.config.ts
├── .prettierrc
│
├── docs/
│   ├── api.md                    # REST API specification
│   ├── architecture/api.md
│   ├── architecture/database.md
│   ├── architecture/erd.md
│   ├── architecture/websocket.md
│   ├── architecture/hardware-integration.md
│   ├── audits/sbitx-v2.md
│   ├── adr/                      # Architecture Decision Records
│   ├── development/setup.md
│   ├── development/ci-cd.md
│   ├── development/testing.md
│   ├── operations/security.md
│   ├── operations/deployment.md
│   ├── architecture/websocket.md
│   ├── architecture/hardware-integration.md
│   └── operations/observability.md
│
├── prompts/                      # AI agent prompt templates
│
├── src/
│   ├── server.ts                 # Fastify entry point
│   ├── api/                      # HTTP routes & controllers
│   │   └── v1/
│   │       ├── auth/
│   │       ├── radio/
│   │       ├── conversations/
│   │       ├── messages/
│   │       ├── users/
│   │       ├── devices/
│   │       ├── system/
│   │       ├── geolocation/
│   │       ├── frequencies/
│   │       ├── schedules/
│   │       └── attachments/
│   ├── gateway/                  # WebSocket gateway
│   ├── hal/                      # Hardware Abstraction Layer
│   ├── messaging/                # Messaging domain logic
│   ├── events/                   # In-process event bus
│   ├── jobs/                     # Job queue
│   ├── db/                       # Database layer (Drizzle ORM)
│   │   ├── schema/
│   │   ├── migrations/
│   │   └── repositories/
│   ├── auth/                     # JWT, RBAC, sessions
│   ├── clock/                    # Clock sync
│   ├── resilience/               # Power-loss, shutdown, recovery
│   └── shared/                   # Shared types, errors, utilities
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── infrastructure/
    ├── scripts/
    └── observability/
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start dev server with hot-reload via `tsx watch` |
| `npm run build` | Compile TypeScript to `dist/` |
| `npm start` | Run compiled server with `--max-old-space-size=384` |
| `npm test` | Run all tests once (`vitest run`) |
| `npm run test:watch` | Run tests in watch mode |
| `npm run test:coverage` | Run tests with coverage report |
| `npm run lint` | Run ESLint on `src/` and `tests/` |
| `npm run lint:fix` | Auto-fix lint issues |
| `npm run format` | Format code with Prettier |
| `npm run format:check` | Check formatting without writing |
| `npm run db:generate` | Generate Drizzle migration |
| `npm run db:migrate` | Apply Drizzle migrations |
| `npm run db:rollback` | Drop all tables (Drizzle drop) |
| `npm run db:studio` | Open Drizzle Studio (GUI) |

## Environment Variables

See `.env.example` for the full list. Key variables for development:

```bash
NODE_ENV=development
RADIO_DRIVER=simulated           # Use simulated radio for dev
METRICS_ENABLED=false            # Disable Prometheus in dev
LOG_LEVEL=debug                  # Verbose logging for development
```

## Testing

```bash
# All tests
npm test

# Specific test file
npx vitest run tests/unit/auth/password.test.ts

# Watch mode for TDD
npm run test:watch

# Coverage report
npm run test:coverage
# Open coverage/index.html in browser
```

See [docs/development/testing.md](testing.md) for detailed testing guidelines.

## Database

The project uses **SQLite in WAL mode** via Drizzle ORM. During development, the database file is at the path specified by `DATABASE_PATH` (default: `./data/hermes.sqlite`).

```bash
# Create a new migration after schema changes
npm run db:generate

# Apply migrations
npm run db:migrate

# Open Drizzle Studio to browse data
npm run db:studio

# Inspect database directly
sqlite3 data/hermes.sqlite
sqlite> .tables
sqlite> .schema conversations
```

## JWT Authentication Keys

The server requires an **RSA 2048-bit key pair** for JWT RS256 token signing and verification. These are generated per station and **never committed** to the repository.

### Key File Locations

| File | Purpose | Security |
|------|---------|----------|
| `keys/private.pem` | Signs JWT access and refresh tokens | 🔒 Must stay on the server — never commit, never share |
| `keys/public.pem` | Verifies JWT tokens on every API request | ✅ Can be freely distributed |

### Generation

```bash
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

### Key Rotation

To rotate keys (invalidating all existing tokens per ADR-004):

```bash
# 1. Generate new keys
openssl genrsa -out keys/private.pem.new 2048
openssl rsa -in keys/private.pem.new -pubout -out keys/public.pem.new

# 2. Replace old keys
mv keys/private.pem.new keys/private.pem
mv keys/public.pem.new keys/public.pem

# 3. Restart the server
npm run dev
```

All previously issued JWT tokens become invalid — clients must re-authenticate.

### How They Work

```
┌─────────────────┐                    ┌─────────────────┐
│  POST /auth/login │                   │  GET /users/me   │
│  (private.pem)   │                   │  (public.pem)    │
└────────┬────────┘                   └────────┬────────┘
         │ Sign JWT                             │ Verify JWT
         ▼                                      ▼
┌─────────────────┐                   ┌─────────────────┐
│ accessToken:     │                  │ Authorization:    │
│ eyJhbGciOiJSU... │ ───────────────► │ Bearer <token>    │
└─────────────────┘                   └─────────────────┘
```

See `src/auth/token.ts` for the `TokenService` implementation and ADR-004 for the token rotation architecture.

## Simulated Radio Driver

Set `RADIO_DRIVER=simulated` in `.env` to develop without physical sBitx hardware. The simulated driver:

- Responds to all CLI commands with plausible fake data
- Generates synthetic telemetry (frequency, power, SWR, temperature)
- Logs all commands for debugging
- Mimics connection/disconnection events

```bash
# Example: start server with simulated radio
RADIO_DRIVER=simulated npm run dev
```

## Debugging

### Node.js Inspector

```bash
# Start with debugger enabled
node --inspect --import tsx src/server.ts

# Or via npm (add to package.json scripts):
# "dev:debug": "node --inspect --import tsx src/server.ts"
```

Then open `chrome://inspect` in Chrome, or attach via VS Code's "Attach to Node Process".

### Logging

Pino structured logging is configured via `LOG_LEVEL`:

```bash
LOG_LEVEL=trace npm run dev    # Most verbose
LOG_LEVEL=fatal npm start      # Errors only (production)
```

For pretty-printed logs in development, use `pino-pretty`:

```bash
npm run dev | npx pino-pretty --colorize
```

## Internationalization (i18n)

The project supports three languages: English (`en`), Spanish (`es`), and Portuguese Brazil (`pt-BR`). Translation resources are plain JSON files loaded at startup (~60 KB total overhead).

### Resource Structure

```
src/i18n/resources/
├── en/
│   ├── errors.json         # API error messages
│   ├── validation.json     # Schema validation messages
│   ├── system.json         # System notifications
│   ├── auth.json           # Authentication messages
│   ├── audit.json          # Audit log descriptions
│   └── email.json          # Email templates
├── es/
│   └── ... (same structure)
└── pt-BR/
    └── ... (same structure)
```

### Adding a New Language

1. Copy `src/i18n/resources/en/` to `src/i18n/resources/<locale>/`
2. Translate all JSON values (keep keys identical)
3. Add the locale to the `CHECK` constraint in the database migration
4. Add the locale to the `Locale` type in `src/i18n/types.ts`
5. Run `npm run i18n:check` to verify all keys match

### Scripts

| Script | Description |
|--------|-------------|
| `npm run i18n:check` | Verify all locales have the same keys as `en/` |

### Locale Resolution

1. User preference (`users.locale` in database, embedded in JWT `locale` claim)
2. `Accept-Language` HTTP header (e.g., `es-MX, es;q=0.9`)
3. Fallback: `en`

### Testing i18n

```bash
# Run i18n-specific tests
npx vitest run tests/unit/i18n/

# Test API with different languages
curl -H "Accept-Language: es" http://localhost:3000/health
```

See [docs/development/i18n.md](../development/i18n.md) for the full internationalization strategy.

---

## Code Quality

Before committing:

```bash
npm run lint          # Check for lint errors
npm run format:check  # Check formatting
npm test              # Run tests
```

CI will also run these checks on every PR (see [docs/ci-cd.md](ci-cd.md)).
