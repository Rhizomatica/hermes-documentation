# ADR-001: SQLite (WAL Mode) as Primary Database for sBitx v2 Raspberry Pi 4 Deployments

## Status

**Accepted** (July 2026)

Supersedes the original ADR-002 from [hermes-backend](https://github.com/Rhizomatica/hermes-backend) which selected PostgreSQL for server deployments.

**Go port note (September 2026):** [ADR-006](adr-006-go-rewrite-and-station-consolidation.md) re-expresses this decision for a Go implementation. The single-writer guarantee relied on in footnote ¹ is no longer provided by the Node.js event loop; it must be enforced by a dedicated single write connection — see [go-migration.md §R-1](../development/go-migration.md).

## Context

The hermes-backend targets the **sBitx v2** hardware platform — a Raspberry Pi 4 with 4 GB RAM running a single HF radio transceiver. The original hermes-backend architecture chose PostgreSQL 17 for concurrent writes, JSONB indexing, full-text search, TimescaleDB time-series, and row-level security. These are correct for a **multi-station server deployment** but not for a **single-station field device**.

### Hardware Constraints

| Constraint | Value |
|------------|-------|
| Total RAM | 4 GB (shared across OS, Node.js, database, radio daemon) |
| Storage | SD card (limited write endurance, single I/O bus) |
| Clients | 2–3 concurrent (1 browser UI + 1 mobile + 0–1 remote station) |
| Writers | Single Node.js process (event loop serializes all writes) |
| Tenancy | Single-tenant (one station, no row-level security needed) |
| Power | Unreliable; hard shutdowns are expected |

## Decision

**SQLite in WAL (Write-Ahead Logging) mode** is the primary production database for sBitx v2 deployments. PostgreSQL remains an available option for multi-station server deployments via the `DatabaseAdapter` interface.

### Why SQLite Wins on Pi 4

| Criteria | SQLite (WAL) | PostgreSQL 17 | Winner |
|----------|:---:|:---:|:---:|
| Memory footprint | **2–5 MB** | 300–800 MB (shared_buffers, workers, autovacuum) | SQLite |
| Daemon process | **None** (in-process) | Required (postgres daemon) | SQLite |
| Crash recovery | **Near-instant** WAL replay | WAL replay (minutes on Pi 4 SD card) | SQLite |
| SD card wear | **Minimal** (WAL append-only, no VACUUM) | High (autovacuum generates heavy random I/O) | SQLite |
| Backup | **Single-file copy** (`sqlite3 .backup`) | `pg_dump` or WAL archiving | SQLite |
| Concurrent reads | Excellent (WAL mode) | Excellent | Tie |
| Concurrent writes | Single-writer, queued via busy_timeout | Multi-writer MVCC | **Tie on Pi 4¹** |
| JSON querying | `json_extract()`, `json_each()` | JSONB with GIN indexes | PostgreSQL² |
| Time-series | Application-level daily table sharding | TimescaleDB extension | PostgreSQL² |

¹ The "single-writer" limitation is irrelevant: all writes go through a single Node.js process (the event loop serializes them). At most 2–3 client requests contend for the write lock — SQLite's `busy_timeout=5000` handles this transparently.

² JSON querying and time-series features are less critical on a single-station Pi 4. JSON metadata queries are infrequent. Time-series data (telemetry, GPS) is simple append-and-query-by-time-range — application-level table sharding handles this efficiently.

## Consequences

### Positive

- **Zero daemon overhead**: No background process consuming RAM
- **Simplified deployment**: No PostgreSQL installation, configuration, or tuning required
- **Instant crash recovery**: WAL replays on next open; no `pg_resetwal` drama after power loss
- **Trivial backup**: Copy the `.sqlite` file while the database is running
- **Single-file management**: One file per database, easy to archive and transfer
- **Drizzle ORM compatibility**: Same TypeScript schema, same repository code

### Negative

- **No multi-process scaling**: If the system needs to scale beyond a single Node.js process, SQLite's single-writer becomes a bottleneck. Migration path: swap to PostgreSQL via the `DatabaseAdapter` interface.
- **No built-in replication**: For multi-station federation (Phase 4+), PostgreSQL's logical replication is superior. SQLite requires application-level sync.
- **No row-level security**: Not needed for single-tenant deployment.
- **Limited concurrent write throughput**: Not an issue at 2–3 clients, but would be problematic at 100+ concurrent writers.

## Implementation

### SQLite Configuration

```sql
PRAGMA journal_mode = WAL;          -- Write-Ahead Logging
PRAGMA synchronous = NORMAL;        -- Safe for WAL mode, better performance than FULL
PRAGMA foreign_keys = ON;           -- Enforce referential integrity
PRAGMA busy_timeout = 5000;         -- Wait 5s for write lock
PRAGMA cache_size = -64000;         -- 64 MB page cache
PRAGMA temp_store = MEMORY;         -- Temp tables in memory
PRAGMA mmap_size = 268435456;       -- 256 MB memory-mapped I/O
```

### DatabaseAdapter Interface

```typescript
// src/db/adapter.ts
interface DatabaseAdapter {
  findConversationById(id: string): Promise<Conversation | null>;
  listUserConversations(userId: string, opts: PaginationOpts): Promise<PaginatedResult<Conversation>>;
  createMessage(data: CreateMessageInput): Promise<Message>;
  // ... all repository methods
}

class SQLiteAdapter implements DatabaseAdapter { /* Drizzle ORM */ }
class PostgresAdapter implements DatabaseAdapter { /* Future — same interface */ }
```

### Dual-Database Strategy

- **sBitx v2 (Pi 4)**: `SQLiteAdapter` — single-file database, WAL mode, in-process
- **Server (future)**: `PostgresAdapter` — same `DatabaseAdapter` interface, different implementation

The adapter is selected at startup via environment variable:

```bash
DB_ADAPTER=sqlite     # Default for sBitx v2
# DB_ADAPTER=postgres  # Future server deployments
```

## Alternatives Considered

### SQLite without WAL (rollback journal)
Rejected: No concurrent reads during writes. WAL mode is required for the read-heavy telemetry + message query workload.

### DuckDB
Rejected: Optimized for analytical queries, not OLTP. Lacks the mature ORM ecosystem (Drizzle, Prisma). Better suited for data analysis, not operational workloads.

### libSQL (Turso fork of SQLite)
Rejected: Adds complexity (replication, HTTP interface) not needed for single-station deployments. Standard SQLite is sufficient and has a larger ecosystem.

## References

- [hermes-backend ADR-002](https://github.com/Rhizomatica/hermes-backend) — Original PostgreSQL decision
- [SQLite WAL Mode Documentation](https://www.sqlite.org/wal.html)
- [docs/architecture-audit-sbitx-v2.md](../audits/sbitx-v2.md) — Full hardware feasibility audit
- [docs/database.md](../architecture/database.md) — Complete schema design