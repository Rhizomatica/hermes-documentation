# Deployment Guide — Hermes Backend on sBitx v2 (Raspberry Pi 4)

## Target Hardware

| Component | Specification |
|-----------|---------------|
| Board | Raspberry Pi 4 Model B |
| RAM | 4 GB |
| Storage | 32 GB+ microSD card (UHS-I U1 minimum) |
| OS | Raspberry Pi OS (Bookworm, 64-bit, Lite recommended) |
| Radio | sBitx v2 HF transceiver (3–30 MHz) |
| Connectivity | Wi-Fi hotspot (station LAN), optional Ethernet |

## Prerequisites

```bash
# System dependencies on Raspberry Pi OS
sudo apt update
sudo apt install -y \
  nodejs npm \
  sqlite3 \
  git \
  build-essential \
  python3

# Verify versions
node --version  # Should be ≥ 22
npm --version   # Should be ≥ 10
sqlite3 --version # Should be ≥ 3.45
```

## Installation

```bash
# 1. Create application directory
sudo mkdir -p /opt/hermes-backend
sudo chown pi:pi /opt/hermes-backend

# 2. Clone repository
cd /opt/hermes-backend
git clone https://github.com/Rhizomatica/hermes-backend.git .

# 3. Install dependencies
npm ci --omit=dev

# 4. Build TypeScript
npm run build

# 5. Create data directories
mkdir -p data/attachments data/keys certs logs

# 6. Configure environment
cp .env.example .env
nano .env  # Edit: NODE_ENV=production, RADIO_DRIVER=sbitx-cli, TLS_ENABLED=true

# 7. Generate RSA keys for JWT
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
chmod 600 keys/private.pem

# 8. Generate self-signed TLS certificate (or use Let's Encrypt)
openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem \
  -days 365 -nodes -subj "/CN=sbitx.local"

# 9. Run database migrations
npm run db:migrate

# 10. Start the server to verify
npm start
```

## Systemd Service

Create `/etc/systemd/system/hermes-backend.service`:

```ini
[Unit]
Description=Hermes Backend
Documentation=https://github.com/Rhizomatica/hermes-backend
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/hermes-backend
Environment=NODE_ENV=production
ExecStart=/usr/bin/node --max-old-space-size=384 /opt/hermes-backend/dist/server.js
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hermes-backend

# Memory limits
MemoryMax=500M
MemoryHigh=450M

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/hermes-backend/data /opt/hermes-backend/logs /tmp
ReadOnlyPaths=/opt/hermes-backend

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-backend
sudo systemctl start hermes-backend
sudo systemctl status hermes-backend

# View logs
sudo journalctl -u hermes-backend -f
```

## SD Card Optimization

```bash
# Disable swap (SD card wear prevention)
sudo dphys-swapfile swapoff
sudo dphys-swapfile uninstall
sudo update-rc.d dphys-swapfile remove

# Move logs to tmpfs (RAM)
echo "tmpfs /var/log tmpfs defaults,noatime,nosuid,size=64m 0 0" | sudo tee -a /etc/fstab

# Noatime on data partition
# Add 'noatime' to /etc/fstab mount options for the root partition
```

## Health Verification

```bash
# Health check
curl -k https://localhost:3000/health
# Expected: { "status": "ok", "uptime": 123, "version": "0.1.0" }

# Deep health (includes DB + radio status)
curl -k https://localhost:3000/health/deep
# Expected: { "status": "ok", "database": "connected", "radio": { "connected": true } }
```

## First-Time Setup

On first boot, access the setup web interface:

1. Connect to the sBitx Wi-Fi hotspot
2. Navigate to `https://sbitx.local:3000/setup`
3. Complete the setup wizard:
   - Station callsign and location
   - Admin user (callsign + password)
   - GPS configuration (if connected)
   - Frequency presets
   - Clock synchronization

Or via API:

```bash
curl -k -X POST https://localhost:3000/setup \
  -H "Content-Type: application/json" \
  -d '{
    "stationCallsign": "SBTX01",
    "adminUser": { "callsign": "ADMIN", "password": "change-me-now" },
    "location": { "latitude": -15.78, "longitude": -47.93 }
  }'
```

## Backup & Restore

```bash
# Backup (while server is running)
sqlite3 /opt/hermes-backend/data/hermes.sqlite ".backup /mnt/backup/hermes-$(date +%Y%m%d).sqlite"

# Restore
sudo systemctl stop hermes-backend
cp /mnt/backup/hermes-YYYYMMDD.sqlite /opt/hermes-backend/data/hermes.sqlite
sudo systemctl start hermes-backend
```

## Upgrades

```bash
cd /opt/hermes-backend
git pull
npm ci --omit=dev
npm run build
npm run db:migrate
sudo systemctl restart hermes-backend
```

## Power-Loss Preparation

- SQLite WAL auto-recovers on next boot (no manual intervention)
- `last_known_time` file written on graceful shutdown; used for clock initialization on boot
- Schedule runner re-checks `next_run_at` on boot; missed schedules are skipped (not replayed)

## Monitoring

```bash
# Memory usage
ps aux | grep node

# Database size
ls -lh /opt/hermes-backend/data/hermes.sqlite*

# Logs (structured JSON via journald)
sudo journalctl -u hermes-backend --since "1 hour ago" -o json

# Metrics (if METRICS_ENABLED=true)
curl http://localhost:9090/metrics