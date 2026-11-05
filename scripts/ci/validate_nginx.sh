#!/usr/bin/env bash
# Validate the production Nginx site config in an isolated nginx install.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

sudo cp "$ROOT_DIR/deploy/nginx/telegram-auto-publisher.conf" /etc/nginx/sites-available/tap.conf
sudo ln -sf /etc/nginx/sites-available/tap.conf /etc/nginx/sites-enabled/tap.conf
sudo rm -f /etc/nginx/sites-enabled/default

# The site references /opt/tap/app/frontend/dist (the documented install path).
sudo mkdir -p /opt/tap/app/frontend/dist
echo "<!doctype html><title>ci</title>" | sudo tee /opt/tap/app/frontend/dist/index.html >/dev/null

sudo nginx -t
echo "nginx configuration OK"
