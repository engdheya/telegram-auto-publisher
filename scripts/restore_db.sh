#!/usr/bin/env bash
# =============================================================================
# Telegram Auto Publisher — verified restore from an online backup
# Usage: ./scripts/restore_db.sh <tap_backup_YYYYmmdd_HHMMSS_label.db>
# Safety: verifies SHA-256, keeps the current DB as a pre-restore snapshot,
#         refuses to run while the worker is active unless --force is passed.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

DB_PATH="${DATABASE_URL:-sqlite:///$ROOT_DIR/runtime/tap.db}"
DB_PATH="${DB_PATH#sqlite:///}"
DB_PATH="${DB_PATH#sqlite://}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/runtime/backups}"

FILENAME="${1:-}"
FORCE="${2:-}"
if [[ -z "$FILENAME" ]]; then
  echo "Usage: $0 <backup_filename> [--force]"
  echo
  echo "Available backups:"
  ls -1t "$BACKUP_DIR"/tap_backup_*.db 2>/dev/null | head -10 || echo "  (none found in $BACKUP_DIR)"
  exit 1
fi

SRC="$BACKUP_DIR/$(basename "$FILENAME")"
[[ -f "$SRC" ]] || { echo "ERROR: backup not found: $SRC"; exit 1; }

if [[ "$FORCE" != "--force" ]] && pgrep -f "app.workers.runner" >/dev/null 2>&1; then
  echo "ERROR: the publishing worker is running. Stop it first:"
  echo "       sudo systemctl stop tap-worker   # or: pkill -f app.workers.runner"
  echo "       Then re-run with --force to confirm."
  exit 1
fi

echo "==> Verifying checksum"
python3 - "$SRC" <<'PY'
import hashlib, pathlib, sys
src = pathlib.Path(sys.argv[1])
sha_file = pathlib.Path(str(src) + ".sha256")
actual = hashlib.sha256(src.read_bytes()).hexdigest()
if sha_file.exists():
    expected = sha_file.read_text().split()[0]
    if actual != expected:
        sys.exit(f"ERROR: SHA-256 mismatch!\n  expected={expected}\n  actual  ={actual}")
    print(f"    sha256 OK ({actual[:16]}…)")
else:
    print(f"    WARNING: no .sha256 file; computed={actual[:16]}…")
PY

echo "==> Verifying restored snapshot integrity"
python3 - "$SRC" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    rows = conn.execute("PRAGMA integrity_check;").fetchall()
    tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table';").fetchone()[0]
finally:
    conn.close()
if rows != [("ok",)] or tables < 13:
    sys.exit(f"ERROR: snapshot failed integrity check: {rows} (tables={tables})")
print(f"    integrity_check=ok, tables={tables}")
PY

echo "==> Creating pre-restore safety snapshot"
"$ROOT_DIR/scripts/backup_db.sh" "prerestore"

echo "==> Restoring"
python3 - "$SRC" "$DB_PATH" <<'PY'
import os, shutil, sqlite3, sys, pathlib
src, db_path = sys.argv[1], sys.argv[2]

# checkpoint and remove WAL/SHM sidecars of the live database
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except sqlite3.Error:
        pass
    finally:
        conn.close()

tmp = db_path + ".restore.tmp"
shutil.copy2(src, tmp)
os.chmod(tmp, 0o600)
os.replace(tmp, db_path)          # atomic swap

for sidecar in (db_path + "-wal", db_path + "-shm"):
    if os.path.exists(sidecar):
        os.remove(sidecar)

conn = sqlite3.connect(db_path)
try:
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table';").fetchone()[0]
finally:
    conn.close()
print(f"    restored → {db_path} (journal_mode={mode}, tables={tables})")
PY

echo
echo "Restore complete. Now restart the services:"
echo "  sudo systemctl start tap-backend tap-worker"
echo "  curl -s http://127.0.0.1:8000/api/v1/health | python3 -m json.tool"
