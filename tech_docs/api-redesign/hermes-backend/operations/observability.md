# Observability Guide — Hermes Backend

## Overview

The Hermes Backend implements a **lightweight observability stack** optimized for Raspberry Pi 4 field deployments. By default, only structured logging is active. Metrics and tracing are opt-in to conserve limited RAM.

| Pillar | Technology | Default | Pi 4 Overhead |
|--------|-----------|:---:|:---:|
| **Logging** | Pino (structured JSON) | **Enabled** | < 5 MB |
| **Metrics** | Prometheus endpoint (`/metrics`) | **Disabled** | ~10–20 MB |
| **Tracing** | Out of scope for Pi 4 | N/A | — |
| **Health Checks** | Built-in Fastify endpoints | **Enabled** | Negligible |

## Logging

### Format

Pino produces structured JSON logs for machine consumption:

```json
{
  "level": 30,
  "time": "2026-07-27T15:30:00.000Z",
  "pid": 1234,
  "hostname": "sbitx-v2-001",
  "msg": "Radio connected on 7100 kHz",
  "radio": {
    "frequency": 7100,
    "mode": "USB",
    "power": 10
  }
}
```

### Log Levels

| Level | Value | Usage |
|-------|:---:|-------|
| `trace` | 10 | Detailed debugging (request/response bodies) |
| `debug` | 20 | Development diagnostics |
| `info` | 30 | Operational events (startup, shutdown, radio connect) |
| `warn` | 40 | Degraded conditions (SWR high, stale telemetry, rate limit hit) |
| `error` | 50 | Recoverable errors (DB query failed, retrying) |
| `fatal` | 60 | Unrecoverable errors (process exiting) |

### Configuration

```bash
# .env
LOG_LEVEL=info         # Production: info. Development: debug
```

For pretty-printed logs in development:

```bash
npm run dev | npx pino-pretty --colorize --translateTime
```

### What We Log

| Event | Level | Fields |
|-------|:---:|--------|
| Server startup | `info` | port, nodeEnv, nodeVersion |
| Server shutdown | `info` | reason (SIGTERM, SIGINT) |
| Database connected | `info` | path, journalMode, pageCount |
| Migration applied | `info` | migrationName, duration |
| User login success | `info` | userId (not password) |
| User login failure | `warn` | callsign (not password), reason, ip |
| Token reuse detected | `warn` | userId (security event) |
| Radio connected | `info` | frequency, mode |
| Radio disconnected | `warn` | reason |
| SWR protection triggered | `warn` | swr, frequency |
| Message sent | `debug` | conversationId, messageLength (not content) |
| Rate limit hit | `warn` | endpoint, ip, limit |
| Database query slow (> 100ms) | `warn` | query, duration |
| File upload started/completed | `info` | attachmentId, size, mimeType |
| Retention cleanup run | `info` | deletedRows, duration |
| Graceful shutdown started | `info` | signal |
| Unhandled rejection | `fatal` | error, stack |
| Uncaught exception | `fatal` | error, stack |

### What We NEVER Log

- Message content (body text)
- Passwords or password hashes
- JWT tokens (full value)
- GPS coordinates (privacy)
- File contents

## Metrics (Prometheus)

Metrics are **disabled by default** on Pi 4 (`METRICS_ENABLED=false`). When enabled, they are exposed at `/metrics` on a separate port (`METRICS_PORT=9090`).

### Available Metrics

#### HTTP Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `hermes_http_requests_total` | Counter | method, route, status_code |
| `hermes_http_request_duration_ms` | Histogram | method, route |
| `hermes_http_request_size_bytes` | Summary | method, route |

#### WebSocket Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `hermes_ws_connections_active` | Gauge | — |
| `hermes_ws_connections_total` | Counter | — |
| `hermes_ws_messages_sent_total` | Counter | type |
| `hermes_ws_messages_received_total` | Counter | type |

#### Database Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `hermes_db_query_duration_ms` | Histogram | operation, table |
| `hermes_db_connections_active` | Gauge | — |
| `hermes_db_size_bytes` | Gauge | — |

#### Radio Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `hermes_radio_connected` | Gauge | — (1=connected, 0=disconnected) |
| `hermes_radio_frequency_khz` | Gauge | — |
| `hermes_radio_power_watts` | Gauge | — |
| `hermes_radio_swr` | Gauge | — |
| `hermes_radio_temperature_celsius` | Gauge | — |
| `hermes_radio_ptt_active` | Gauge | — (1=TX, 0=RX) |
| `hermes_radio_voltage` | Gauge | — |
| `hermes_radio_current_amps` | Gauge | — |

#### Application Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `hermes_messages_total` | Counter | type (sent, received, delivered) |
| `hermes_conversations_total` | Counter | type (direct, group, broadcast) |
| `hermes_users_active` | Gauge | — |
| `hermes_sessions_active` | Gauge | — |
| `hermes_jobs_queued` | Gauge | queue |
| `hermes_jobs_completed_total` | Counter | queue, status |
| `hermes_attachments_size_bytes` | Gauge | — |
| `hermes_attachments_total` | Counter | — |
| `hermes_clock_synced` | Gauge | — (1=synced, 0=unsynced) |
| `hermes_memory_heap_bytes` | Gauge | — |
| `hermes_memory_rss_bytes` | Gauge | — |
| `hermes_event_loop_lag_seconds` | Gauge | — |

### Grafana Dashboard

When metrics are enabled, a ready-to-use Grafana dashboard JSON is provided in `infrastructure/observability/grafana-dashboard.json`.

Suggested panels:

1. **HTTP Overview**: Request rate, latency p50/p95/p99, error rate
2. **Radio Telemetry**: Frequency, power, SWR, temperature over time
3. **Messaging**: Messages sent/received rate, active conversations
4. **Database**: Query latency p95, database size growth
5. **System**: Heap memory, RSS, event loop lag
6. **WebSocket**: Active connections, message throughput

## Health Checks

### `GET /health`

Lightweight liveness check. Returns immediately without checking dependencies.

```json
{
  "status": "ok",
  "uptime": 123456,
  "version": "0.1.0",
  "timestamp": "2026-07-27T15:30:00.000Z"
}
```

**HTTP Status**: `200` (healthy) | `503` (unhealthy — server shutting down)

### `GET /health/deep`

Full readiness check. Verifies database connectivity and radio status.

```json
{
  "status": "ok",
  "uptime": 123456,
  "version": "0.1.0",
  "timestamp": "2026-07-27T15:30:00.000Z",
  "checks": {
    "database": {
      "status": "ok",
      "type": "sqlite",
      "responseMs": 2
    },
    "radio": {
      "status": "ok",
      "connected": true,
      "frequency": 7100,
      "mode": "USB"
    },
    "clock": {
      "status": "ok",
      "synced": true,
      "source": "gps",
      "lastSync": "2026-07-27T14:00:00.000Z"
    }
  }
}
```

**HTTP Status**: `200` (all checks pass) | `503` (one or more checks failing)

### Health Check Usage

- **Kubernetes/Docker**: `GET /health` as liveness probe (every 10s)
- **Systemd**: `ExecStartPost` can curl `GET /health/deep` to verify startup
- **Monitoring**: Alert if `/health/deep` returns non-200
- **Frontend**: Display connection status based on `/health` response

## Error Tracking

There is no external error tracking service (Sentry, Datadog) in field-deployed stations (air-gapped). Instead:

1. **Fatal errors** are logged at `fatal` level and trigger a graceful shutdown
2. **Recoverable errors** are logged at `error` level with context
3. **All errors** include a correlation ID for tracing through logs
4. **Audit logs** capture security-relevant errors (auth failures, token reuse)

Error correlation flow:

```
Client request → correlationId generated → attached to all log lines for that request
→ returned in X-Correlation-ID response header
→ client includes in error report
```

## Performance Monitoring

### V8 Heap Limits

The Node.js process runs with `--max-old-space-size=384` (384 MB V8 heap).

```bash
# Check current heap usage
node -e "console.log(v8.getHeapStatistics())"
```

Monitor via:
- Prometheus: `hermes_memory_heap_bytes`, `hermes_memory_rss_bytes`
- CLI: `ps aux | grep node`

### Event Loop Lag

Monitored via Prometheus (`hermes_event_loop_lag_seconds`). Lag > 100ms indicates:
- Blocking synchronous operation
- Heavy GC pause
- SD card I/O contention

### Query Performance

Drizzle ORM queries can be instrumented with a duration logger. Queries taking > 100ms are logged at `warn` level.

## Retention & Rotation

### Log Retention

Logs are written to `stdout`/`stderr` and captured by journald (systemd). Journald configuration:

```ini
# /etc/systemd/journald.conf
SystemMaxUse=100M
MaxFileSec=7day
```

### Metric Retention

Prometheus TSDB retention is not configured (metrics are disabled by default on Pi 4). If enabled, the Prometheus server on a separate machine handles retention.

## Debugging in the Field

Since field stations are often air-gapped:

1. **Log export**: `sudo journalctl -u hermes-backend --since "24h ago" -o json > logs.json`
2. **Database inspection**: `sqlite3 /opt/hermes-backend/data/hermes.sqlite`
3. **Health snapshot**: `curl -k https://localhost:3000/health/deep`
4. **Memory snapshot**: `ps aux | grep node`
5. **Config dump**: `GET /system/config` (admin-only endpoint)

All of these can be performed via SSH over the station's Wi-Fi hotspot — no internet required.