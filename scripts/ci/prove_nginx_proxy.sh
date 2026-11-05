#!/usr/bin/env bash
# =============================================================================
# prove_nginx_proxy.sh — end-to-end proof of deploy/nginx/telegram-auto-publisher.conf
#
# Starts the real nginx with the shipped site config (temporary self-contained
# prefix, no system state touched), rebuilds the production frontend bundle,
# and asserts: SPA index, deep link, hashed asset + Cache-Control, API proxy,
# security headers, gzip, and the /assets duplicate-header regression.
#
# Usage: bash scripts/ci/prove_nginx_proxy.sh
# Requires: nginx installed, frontend/node_modules present, backend on :8000.
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFIX=/tmp/tap-nginx
SITE="$PREFIX/conf/nginx.conf"
DOCROOT=/opt/tap/app/frontend/dist
PORT=8080
FAILS=0

ok()   { printf 'PASS | %s\n' "$1"; }
bad()  { printf 'FAIL | %s\n' "$1"; FAILS=$((FAILS + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1 ($2)"; else bad "$1 (expected $3, got $2)"; fi; }

echo "# nginx proxy proof — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# nginx: $(/usr/sbin/nginx -v 2>&1)"

banner() { printf '\n=== %s ===\n' "$1"; }

banner "0) prerequisites"
command -v nginx >/dev/null 2>&1 || NGINX=/usr/sbin/nginx
NGINX=${NGINX:-nginx}
curl -fsS -m 5 "http://127.0.0.1:8000/api/v1/health" >/dev/null && ok "backend is up on :8000" || { bad "backend not reachable on :8000"; exit 1; }

banner "1) build the production frontend bundle"
if [ ! -d "$REPO_ROOT/frontend/dist" ]; then
  ( cd "$REPO_ROOT/frontend" && npm run build >/tmp/vite-build.log 2>&1 ) \
    && ok "vite build completed" || { bad "vite build failed (see /tmp/vite-build.log)"; exit 1; }
else
  ok "frontend/dist already present (reused)"
fi

banner "2) publish the bundle where nginx can read it (www-data must traverse the path)"
sudo rm -rf "$DOCROOT"
sudo mkdir -p /opt/tap/app/frontend
sudo cp -r "$REPO_ROOT/frontend/dist" "$DOCROOT"
sudo chown -R www-data:www-data "$DOCROOT"
sudo chmod -R a+rX "$DOCROOT"
sudo -u www-data test -r "$DOCROOT/index.html" && ok "www-data can read $DOCROOT/index.html" || bad "www-data cannot read the bundle"

banner "3) render the shipped site config into a throwaway prefix and validate it"
sudo rm -rf "$PREFIX"
sudo mkdir -p "$PREFIX/logs" "$PREFIX/conf" "$PREFIX/tmp"
sudo python3 - "$REPO_ROOT/deploy/nginx/telegram-auto-publisher.conf" "$SITE" <<'PY'
import sys, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
s = src.read_text()
s = s.replace("listen 80;", "listen 8080;").replace("listen [::]:80;", "listen [::]:8080;")
s = s.replace("server_name _;", "server_name localhost;")
s = s.replace("/var/log/nginx/", "/tmp/tap-nginx/logs/")
s = s.replace("include /etc/nginx/", "include /tmp/tap-nginx/conf/")
text = """worker_processes 1;
pid {prefix}/nginx.pid;
error_log {prefix}/logs/error.log warn;
events {{ worker_connections 256; }}
http {{
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    access_log    {prefix}/logs/access.log;
    client_body_temp_path {prefix}/tmp/body;
    proxy_temp_path       {prefix}/tmp/proxy;
    fastcgi_temp_path     {prefix}/tmp/fastcgi;
    uwsgi_temp_path       {prefix}/tmp/uwsgi;
    scgi_temp_path        {prefix}/tmp/scgi;
    sendfile on;
    keepalive_timeout 30;
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
{body}
}}
""".format(prefix="/tmp/tap-nginx", body="\n".join("    " + ln for ln in s.splitlines()))
dst.write_text(text)
print("rendered:", dst)
PY
sudo "$NGINX" -t -c "$SITE" 2>&1 | tail -3
sudo "$NGINX" -t -c "$SITE" >/dev/null 2>&1 && ok "nginx -t on the shipped config" || { bad "nginx -t failed"; exit 1; }

banner "4) start nginx on :$PORT"
sudo "$NGINX" -c "$SITE" || { bad "nginx failed to start"; sudo tail -5 "$PREFIX/logs/error.log"; exit 1; }
sleep 1
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")
check "GET / (SPA index)" "$code" 200

code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/routes")
check "GET /routes (client-side deep link)" "$code" 200

asset=$(ls "$DOCROOT/assets" | grep -E '\.js$' | head -1)
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/assets/$asset")
check "GET /assets/$asset (hashed bundle)" "$code" 200

cc=$(curl -s -m 5 -D - -o /dev/null "http://127.0.0.1:$PORT/assets/$asset" | grep -ci '^cache-control: public, max-age=2592000, immutable')
check "Cache-Control on /assets (exactly one immutable header)" "$cc" 1

sec=$(curl -s -m 5 -D - -o /dev/null "http://127.0.0.1:$PORT/" | grep -ciE '^x-(content-type-options|frame-options):|^referrer-policy:|^content-security-policy:|^permissions-policy:')
[ "$sec" -ge 4 ] && ok "security headers present ($sec headers)" || bad "security headers missing (found $sec)"

banner "5) API through the proxy"
health=$(curl -s -m 5 "http://127.0.0.1:$PORT/api/v1/health")
echo "$health" | grep -q '"status":"ok"' && ok "GET /api/v1/health via nginx -> status ok" || bad "health via nginx failed: $health"
echo "$health" | grep -q '"journal_mode":"wal"' && ok "WAL journal mode reported through the proxy" || bad "WAL not reported"

paths=$(curl -s -m 5 "http://127.0.0.1:$PORT/openapi.json" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['paths']))" 2>/dev/null || echo 0)
[ "$paths" -ge 40 ] && ok "OpenAPI reachable through nginx ($paths paths)" || bad "OpenAPI not proxied (paths=$paths)"

if [ -n "${TAP_ADMIN_USERNAME:-}" ] && [ -n "${TAP_ADMIN_PASSWORD:-}" ]; then
  tok=$(curl -s -m 8 -X POST "http://127.0.0.1:$PORT/api/v1/auth/login" -H 'Content-Type: application/json' \
        -d "{\"username\":\"$TAP_ADMIN_USERNAME\",\"password\":\"$TAP_ADMIN_PASSWORD\"}" \
        | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
  [ -n "$tok" ] && ok "login through nginx returned a JWT" || bad "login through nginx failed"
  ov=$(curl -s -m 8 "http://127.0.0.1:$PORT/api/v1/dashboard/overview" -H "Authorization: Bearer $tok" | head -c 120)
  echo "$ov" | grep -q 'telegram_connected' && ok "authenticated dashboard call through nginx" || bad "dashboard call through nginx failed: $ov"
else
  echo "SKIP | login-through-nginx (set TAP_ADMIN_USERNAME / TAP_ADMIN_PASSWORD to enable)"
fi

banner "6) stop nginx and summarise"
sudo "$NGINX" -c "$SITE" -s quit 2>/dev/null
sleep 1
if [ "$FAILS" -eq 0 ]; then echo "ALL NGINX CHECKS PASSED"; else echo "$FAILS NGINX CHECK(S) FAILED"; fi
exit "$FAILS"
