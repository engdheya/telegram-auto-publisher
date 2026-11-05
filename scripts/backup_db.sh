#!/usr/bin/env bash
# =============================================================================
# Telegram Auto Publisher — Online SQLite backup (WAL-safe, verified)
# Usage: ./scripts/backup_db.sh [label]
# Requires: python3 (uses sqlite3.Connection.backup — safe while the app is live)
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load .env if present (DATABASE_URL, BACKUP_DIR)
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
LABEL="${1:-manual}"

mkdir -p "$BACKUP_DIR"

python3 - "$DB_PATH" "$BACKUP_DIR" "$LABEL" <<'PY'
import hashlib, os, sqlite3, sys, datetime, pathlib

db_path, backup_dir, label = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(db_path):
    sys.exit(f"ERROR: database not found at {db_path}")

safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)[:32]
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
dest = os.path.join(backup_dir, f"tap_backup_{ts}_{safe_label}.db")

src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15.0)
dst = sqlite3.connect(dest, timeout=15.0)
try:
    with dst:
        src.backup(dst, pages=250, sleep=0.01)
finally:
    dst.close()
    src.close()

# integrity verification of the produced snapshot
conn = sqlite3.connect(dest)
try:
    result = conn.execute("PRAGMA integrity_check;").fetchall()
    tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table';").fetchone()[0]
finally:
    conn.close()
if result != [("ok",)] or tables < 13:
    os.remove(dest)
    sys.exit(f"ERROR: backup failed verification (integrity={result}, tables={tables})")

os.chmod(dest, 0o600)
digest = hashlib.sha256(pathlib.Path(dest).read_bytes()).hexdigest()
sha_file = dest + ".sha256"
pathlib.Path(sha_file).write_text(f"{digest}  {os.path.basename(dest)}\n", encoding="utf-8")
os.chmod(sha_file, 0o600)

size = os.path.getsize(dest)
print(f"OK  {os.path.basename(dest)}  {size} bytes  tables={tables}")
print(f"    sha256={digest}")
PY

# Retention: keep the 30 most recent 0700 snapshots
python3 - "$BACKUP_DIR" <<'PY'
import os, sys, glob
backup_dir = sys.argv[1]
files = sorted(glob.glob(os.path.join(backup_dir, "tap_backup_*.db")), key=os.path.getmtime, reverse=True)
for old in files[30:]:
    for suffix in ("", ".sha256"):
        try:
            os.remove(old + suffix)
        except FileNotFoundError:
            pass
    print(f"    pruned {os.path.basename(old)}")
PY
