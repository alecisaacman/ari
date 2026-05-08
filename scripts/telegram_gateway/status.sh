#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_FILE="$REPO_ROOT/data/telegram/run/gateway.pid"
LOG_FILE="$REPO_ROOT/data/telegram/logs/gateway.log"
STATE_FILE="${ARI_TELEGRAM_POLLING_STATE_FILE:-$REPO_ROOT/data/telegram/state/ari_command_polling_state.json}"

cd "$REPO_ROOT"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    echo "ARI Telegram Gateway: running"
    echo "PID: $pid"
  else
    echo "ARI Telegram Gateway: not running"
    echo "Stale PID file: $PID_FILE"
  fi
else
  discovered_pid="$(
    pgrep -f "$REPO_ROOT/.venv312/bin/ari-telegram-gateway" 2>/dev/null | head -n 1 || true
  )"
  if [[ -z "$discovered_pid" ]]; then
    discovered_pid="$(
      pgrep -f "ari_telegram_gateway.polling" 2>/dev/null | head -n 1 || true
    )"
  fi
  if [[ "$discovered_pid" =~ ^[0-9]+$ ]]; then
    echo "ARI Telegram Gateway: running without PID file"
    echo "PID: $discovered_pid"
  else
    echo "ARI Telegram Gateway: not running"
  fi
fi

echo
echo "Polling state:"
if [[ -f "$STATE_FILE" ]]; then
  "$REPO_ROOT/.venv312/bin/python" - "$STATE_FILE" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"Could not read {path}: {exc}")
else:
    print(f"File: {path}")
    print(f"bot_identity: {state.get('bot_identity', '')}")
    print(f"last_processed_update_id: {state.get('last_processed_update_id', '')}")
    print(f"updated_at: {state.get('updated_at', '')}")
PY
else
  echo "No polling state file found at $STATE_FILE"
fi

echo
echo "Latest log lines:"
if [[ -f "$LOG_FILE" ]]; then
  tail -n 20 "$LOG_FILE"
else
  echo "No log file found at $LOG_FILE"
fi
