#!/usr/bin/env bash
# =============================================================================
# Telegram Auto Publisher — systemd installation (Ubuntu 22.04/24.04)
# Usage (as a sudo-capable user):
#   sudo ./scripts/setup_systemd.sh [install_dir] [service_user]
# Defaults: install_dir=/opt/tap/app  service_user=tap
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${1:-/opt/tap/app}"
SERVICE_USER="${2:-tap}"
RUNTIME_DIR="$(dirname "$INSTALL_DIR")/runtime"
VENV_DIR="$(dirname "$INSTALL_DIR")/venv"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root (sudo $0)"; exit 1
fi

echo "==> Ensuring service user '$SERVICE_USER'"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd -r -m -d "/home/$SERVICE_USER" -s /bin/bash "$SERVICE_USER"
fi

echo "==> Runtime directories: $RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"/{backups,logs,media_cache}
chown -R "$SERVICE_USER:$SERVICE_USER" "$RUNTIME_DIR"
chmod 750 "$RUNTIME_DIR"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  echo "ERROR: $INSTALL_DIR/.env not found. Copy .env.example, fill in secrets, chmod 600."; exit 1
fi
chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "ERROR: virtualenv not found at $VENV_DIR (create it and pip install -r backend/requirements.txt)"; exit 1
fi

echo "==> Writing systemd units"
cat >/etc/systemd/system/tap-backend.service <<UNIT
[Unit]
Description=Telegram Auto Publisher — FastAPI backend
Documentation=file://${INSTALL_DIR}/docs/INSTALLATION.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}/backend
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3
LimitNOFILE=65535
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ReadWritePaths=${RUNTIME_DIR}

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/tap-worker.service <<UNIT
[Unit]
Description=Telegram Auto Publisher — publishing worker (SINGLE INSTANCE ONLY)
Documentation=file://${INSTALL_DIR}/docs/DEPLOYMENT.md
After=network-online.target tap-backend.service
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}/backend
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${VENV_DIR}/bin/python -m app.workers.runner
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ReadWritePaths=${RUNTIME_DIR}

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/tap-backup.service <<UNIT
[Unit]
Description=Telegram Auto Publisher — verified SQLite online backup

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/scripts/backup_db.sh scheduled
UNIT

cat >/etc/systemd/system/tap-backup.timer <<'UNIT'
[Unit]
Description=Daily Telegram Auto Publisher backup (03:30)

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now tap-backend.service tap-worker.service tap-backup.timer

echo
echo "==> Status"
systemctl --no-pager --lines=5 status tap-backend.service || true
systemctl --no-pager --lines=5 status tap-worker.service || true
systemctl list-timers tap-backup.timer --no-pager || true

cat <<'DONE'

Next steps:
  1. Install the Nginx site:  sudo cp deploy/nginx/telegram-auto-publisher.conf /etc/nginx/sites-available/tap.conf
                              sudo ln -sf /etc/nginx/sites-available/tap.conf /etc/nginx/sites-enabled/tap.conf
                              sudo nginx -t && sudo systemctl reload nginx
  2. Enable TLS:              sudo certbot --nginx -d your-domain.com
  3. Verify health:           curl -s http://127.0.0.1:8000/api/v1/health | python3 -m json.tool
  4. Open the dashboard and change the bootstrap admin password.

IMPORTANT: never start a second tap-worker instance — SQLite allows a single writer.
DONE
