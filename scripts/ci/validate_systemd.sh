#!/usr/bin/env bash
# Validate the systemd units shipped in deploy/systemd/ without enabling them.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for unit in "$ROOT_DIR"/deploy/systemd/*.service "$ROOT_DIR"/deploy/systemd/*.timer; do
  echo "==> $unit"
  # systemd-analyze verify requires the referenced binaries to exist; create stubs so we
  # validate the *unit syntax* rather than the host layout.
  sudo mkdir -p /opt/tap/app/backend /opt/tap/venv/bin
  sudo cp "$unit" "/etc/systemd/system/$(basename "$unit")"

  python - "$unit" <<'PY'
import configparser, sys
path = sys.argv[1]
cp = configparser.ConfigParser(strict=False, interpolation=None)
cp.optionxform = str
cp.read(path)
# timers have no [Service]; oneshot helper units (backup) have no [Install]
required = {"Unit": ["Description"]}
if path.endswith(".timer"):
    required["Timer"] = ["OnCalendar"]
    required["Install"] = ["WantedBy"]
else:
    required["Service"] = ["ExecStart", "User", "WorkingDirectory"]
    if path.endswith(("tap-backend.service", "tap-worker.service")):
        required["Install"] = ["WantedBy"]
for section, keys in required.items():
    assert cp.has_section(section), f"{path}: missing [{section}]"
    for key in keys:
        assert cp.has_option(section, key), f"{path}: missing {section}.{key}"
if cp.has_section("Service"):
    exec_start = cp.get("Service", "ExecStart")
    assert "/opt/tap/" in exec_start, f"{path}: ExecStart must reference the documented install path"
if path.endswith("tap-worker.service"):
    assert "app.workers.runner" in exec_start, "worker unit must run the worker orchestrator"
    assert cp.get("Service", "Restart") == "always", "worker must restart automatically (Restart=always)"
print(f"    syntax OK (sections: {', '.join(cp.sections())})")
PY
  sudo systemctl daemon-reload
  systemctl cat "$(basename "$unit")" >/dev/null && echo "    loaded by systemd OK"
done

sudo systemctl daemon-reload
echo "systemd units OK"
