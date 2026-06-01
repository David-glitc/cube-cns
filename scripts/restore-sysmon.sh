#!/usr/bin/env bash
# Restore SysMon for VPS monitoring (separate from TheBox on :8780).
set -euo pipefail
SYSMON_ROOT="${SYSMON_ROOT:-/home/david/sysmon}"
MONITOR_HOST="${MONITOR_HOST:-monitor.chessonchain.online}"

cd "$SYSMON_ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

fuser -k 8765/tcp 2>/dev/null || true
sleep 1
nohup ./start.sh >> sysmon.log 2>&1 &
sleep 2

MONITOR_HOST="$MONITOR_HOST" ./install-traefik-route.sh
echo "SysMon: https://${MONITOR_HOST}/ (port 8765)"
