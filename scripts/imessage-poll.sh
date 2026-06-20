#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"

source "$REPO_ROOT/scripts/_rotate-logs.sh"
_rotate_log_if_large "$REPO_ROOT/logs/imessage-poll.log"

if [[ -f "$REPO_ROOT/state/PAUSED" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [imessage-poll] PAUSED — exiting without action."
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
_ensure_postgres || { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [imessage-poll] Postgres unavailable — skipping this cycle."; exit 0; }

python scripts/imessage-ingest.py
