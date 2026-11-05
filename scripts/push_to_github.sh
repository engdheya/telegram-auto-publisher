#!/usr/bin/env bash
# =============================================================================
# Telegram Auto Publisher — one-command push to GitHub
# Usage: ./scripts/push_to_github.sh <git@github.com:user/repo.git | https://...>
# Safety: refuses to push if any secret-looking file is tracked.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_URL="${1:-}"
if [[ -z "$REMOTE_URL" ]]; then
  echo "Usage: $0 <remote-url>"; exit 1
fi

echo "==> Secret / artefact guard"
FORBIDDEN=$(git ls-files | grep -E '(^|/)(\.env$|\.env\.(?!example)|.*\.session|.*\.db$|.*\.db-wal$|.*\.sha256|node_modules/|dist/|__pycache__/|runtime/)' -P || true)
if [[ -n "$FORBIDDEN" ]]; then
  echo "ERROR: the following sensitive/derived files are tracked — remove them first:"
  echo "$FORBIDDEN"
  exit 1
fi
echo "    clean: no .env, sessions, databases, or build artefacts are tracked"

echo "==> Current commits"
git log --oneline | head -10

if git remote get-url origin >/dev/null 2>&1; then
  echo "==> Updating existing origin remote"
  git remote set-url origin "$REMOTE_URL"
else
  echo "==> Adding origin remote"
  git remote add origin "$REMOTE_URL"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Pushing branch '$BRANCH'"
git push -u origin "$BRANCH"

cat <<'DONE'

Done. Recommended repository settings:
  • Branch protection on main (require PR + CI green)
  • Enable Actions (the CI workflow builds, lints, and runs the test suites)
  • Add repo secrets only if you extend CI (never commit them)
DONE
