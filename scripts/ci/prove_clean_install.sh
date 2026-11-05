#!/usr/bin/env bash
# =============================================================================
# prove_clean_install.sh — from-zero installation proof.
#
# Copies the working tree into an empty directory (no .env, no runtime/, no
# virtualenv), installs the pinned requirements into a brand-new virtualenv,
# runs the migrations, seeds the bootstrap admin, and runs the backend tests.
#
# Usage:  bash scripts/ci/prove_clean_install.sh [target_dir]
# Exit:   0 = every stage succeeded, non-zero = the failing stage.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-/tmp/tap-clean-install}"
STAGE="start"

banner() { printf '\n=== %s ===\n' "$1"; }
fail() {
  printf '\nFAILED at stage: %s\n' "$STAGE" >&2
  exit 1
}
trap fail ERR

printf '# Clean-install proof — %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '# host: %s · python: %s · target: %s\n' "$(uname -srm)" "$(python3 -V 2>&1)" "$TARGET"

STAGE="copy tree"
banner "1) copy the tree into an empty directory (no .env / runtime / venv / node_modules)"
rm -rf "$TARGET"
mkdir -p "$TARGET"
tar -C "$REPO_ROOT" \
    --exclude=./.git --exclude=./.env --exclude=./runtime \
    --exclude=./.venv --exclude='./frontend/node_modules' --exclude='./frontend/dist' \
    -cf - . | tar -C "$TARGET" -xf -
ls -a "$TARGET" | tr '\n' ' '
echo

STAGE="generate .env"
banner "2) .env from .env.example with freshly generated secrets"
cd "$TARGET"
cp .env.example .env
python3 "$REPO_ROOT/scripts/ci/generate_env_secrets.py" .env
grep -E '^(DATABASE_URL|BACKUP_DIR|MEDIA_CACHE_DIR|LOG_DIR)=' .env

STAGE="install dependencies"
banner "3) brand-new virtualenv + pinned requirements"
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r backend/requirements.txt
echo "pip install -r backend/requirements.txt: OK ($(./.venv/bin/pip list --format=freeze | wc -l) packages installed)"
./.venv/bin/pip check

STAGE="migrate"
banner "4) alembic upgrade head"
cd backend
PYTHONPATH=. ../.venv/bin/python -c "
from alembic.config import Config
from alembic import command
command.upgrade(Config('alembic.ini'), 'head')
print('alembic upgrade head: OK')
"

STAGE="inspect schema"
banner "5) tables created in sqlite_master"
PYTHONPATH=. ../.venv/bin/python -c "
import sqlite3
from app.core.config import get_settings
db = get_settings().resolved_database_path()
rows = [r[0] for r in sqlite3.connect(db).execute(\"select name from sqlite_master where type='table' order by name\")]
print('db file:', db)
print(len(rows), 'tables ->', ', '.join(rows))
print('business tables:', len([r for r in rows if r != 'alembic_version']), '+ alembic_version')
"

STAGE="seed"
banner "6) seed the bootstrap admin (idempotent)"
PYTHONPATH=. ../.venv/bin/python -c "

from app.database.init_db import init_database
init_database()
print('init_database(): bootstrap admin seeded')
"
PYTHONPATH=. ../.venv/bin/python -c "
from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models.user import User
s = get_settings()
db = SessionLocal()
u = db.query(User).filter(User.username == s.INITIAL_ADMIN_USERNAME).one()
print('admin user:', u.username, '| role:', u.role, '| active:', u.is_active)
"

STAGE="tests"
banner "7) backend test-suite on this clean tree"
PYTHONPATH=. timeout 600 ../.venv/bin/python -m pytest -q 2>&1 | tail -3

STAGE="done"
banner "8) result"
echo "ALL STAGES PASSED — a fresh machine with python3 + git can reproduce this."
