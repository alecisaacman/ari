#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$REPO_ROOT/data/telegram/logs/gateway.log"

cd "$REPO_ROOT"
mkdir -p "$(dirname "$LOG_FILE")"

if [[ ! -f "$LOG_FILE" ]]; then
  echo "No gateway log file found yet: $LOG_FILE"
  exit 0
fi

tail -f "$LOG_FILE"
