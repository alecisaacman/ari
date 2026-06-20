#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
TODAY=$(date +%Y-%m-%d)

source "$REPO_ROOT/scripts/_rotate-logs.sh"
_rotate_log_if_large "$REPO_ROOT/logs/daily-orchestration.log"

if [[ -f "$REPO_ROOT/state/PAUSED" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [daily-check] PAUSED — exiting without action."
  exit 0
fi

if [[ ! -d "$VENV" ]]; then
  echo "ERROR: ARI venv not found. Run start-ari.sh first."
  exit 1
fi

source "$VENV/bin/activate"
export PYTHONPATH="$REPO_ROOT/packages/ari-state/src:$REPO_ROOT/packages/ari-memory/src:$REPO_ROOT/packages/ari-events/src:$REPO_ROOT/packages/ari-routines/src:$REPO_ROOT/packages/ari-signals/src:$REPO_ROOT/packages/ari-cli/src:$REPO_ROOT/services/ari-core/src:$REPO_ROOT/services/ari-api/src:$REPO_ROOT/services/ari-hub/src"

cd "$REPO_ROOT"
source "$REPO_ROOT/scripts/_ensure-postgres.sh"
_ensure_postgres || echo "WARNING: proceeding without confirmed Postgres — orchestration will likely fail."

echo "========================================"
echo " ARI Daily Check — $TODAY"
echo "========================================"
echo ""

echo "--- Current State ---"
ari today read --state-date "$TODAY" || echo "(no daily state recorded yet — open the hub to set it)"
echo ""

echo "--- Open Loops ---"
ari loops read || echo "(no open loops)"
echo ""

echo "--- Running Orchestration ---"
if ari orchestration run --state-date "$TODAY"; then
  echo ""
  echo "--- Sending notifications for elevated/interruptive alerts ---"
  python "$REPO_ROOT/scripts/notify-alerts.py" --state-date "$TODAY" || true
  echo ""
  echo "--- Orchestration complete. Open hub for full detail: http://localhost:8001 ---"
else
  echo "Orchestration failed. Is the database running? (docker compose up -d postgres)"
fi

echo ""
echo "========================================"
