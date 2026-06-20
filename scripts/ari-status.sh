#!/usr/bin/env bash
# One-stop health check for the whole ARI system: pause state, launchd
# agents, service reachability, and the tail of each automation log.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAUSED_FILE="$REPO_ROOT/state/PAUSED"
LOGS="$REPO_ROOT/logs"

echo "========================================"
echo " ARI Status — $(date)"
echo "========================================"
echo ""

echo "--- Pause state ---"
if [[ -f "$PAUSED_FILE" ]]; then
  echo "PAUSED:"
  sed 's/^/  /' "$PAUSED_FILE"
else
  echo "Not paused."
fi
echo ""

echo "--- launchd agents ---"
for plist in ~/Library/LaunchAgents/com.ari.*.plist; do
  [[ -e "$plist" ]] || continue
  label=$(basename "$plist" .plist)
  status=$(launchctl list | grep "$label" || echo "NOT LOADED")
  echo "  $label: $status"
done
echo ""

echo "--- Services ---"
for entry in "ari-api:8000" "ari-hub:8001"; do
  name="${entry%%:*}"
  port="${entry##*:}"
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/" --max-time 2 2>/dev/null || echo "down")
  echo "  $name (:$port): $code"
done
docker compose -f "$REPO_ROOT/compose.yaml" ps postgres 2>/dev/null | tail -n +2 | sed 's/^/  postgres: /' || echo "  postgres: unknown (docker not reachable)"
echo ""

echo "--- Recent log activity ---"
for log in imessage-poll.log daily-orchestration.log notify-alerts.log; do
  path="$LOGS/$log"
  if [[ -f "$path" ]]; then
    echo "  $log (last 3 lines):"
    tail -n 3 "$path" | sed 's/^/    /'
  else
    echo "  $log: not found"
  fi
done
echo ""

echo "--- iMessage cursor ---"
if [[ -f "$REPO_ROOT/state/imessage-cursor.txt" ]]; then
  echo "  last processed rowid: $(cat "$REPO_ROOT/state/imessage-cursor.txt")"
else
  echo "  no cursor file yet"
fi
