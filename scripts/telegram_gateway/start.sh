#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$REPO_ROOT/.venv312/bin/python"
GATEWAY="$REPO_ROOT/.venv312/bin/ari-telegram-gateway"
LOG_DIR="$REPO_ROOT/data/telegram/logs"
RUN_DIR="$REPO_ROOT/data/telegram/run"
LOG_FILE="$LOG_DIR/gateway.log"
PID_FILE="$RUN_DIR/gateway.pid"

cd "$REPO_ROOT"
mkdir -p "$LOG_DIR" "$RUN_DIR" data/telegram/state data/telegram/events data/telegram/inbox

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "$existing_pid" =~ ^[0-9]+$ ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "ARI Telegram Gateway is already running with PID $existing_pid."
    exit 0
  fi
  echo "Removing stale PID file: $PID_FILE"
  rm -f "$PID_FILE"
fi

existing_gateway_pid="$(
  pgrep -f "$REPO_ROOT/.venv312/bin/ari-telegram-gateway" 2>/dev/null | head -n 1 || true
)"
if [[ -z "$existing_gateway_pid" ]]; then
  existing_gateway_pid="$(
    pgrep -f "ari_telegram_gateway.polling" 2>/dev/null | head -n 1 || true
  )"
fi
if [[ "$existing_gateway_pid" =~ ^[0-9]+$ ]]; then
  echo "ARI Telegram Gateway already appears to be running with PID $existing_gateway_pid."
  echo "Refusing to start a duplicate process."
  exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing Python runtime: $PYTHON"
  echo "Create or refresh .venv312 before starting the gateway."
  exit 1
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] refreshing editable install" >> "$LOG_FILE"
if ! "$PYTHON" -m pip install -q -e "$REPO_ROOT" --no-build-isolation >> "$LOG_FILE" 2>&1; then
  echo "Editable install failed. See $LOG_FILE."
  echo "Manual command: ./.venv312/bin/pip install -e . --no-build-isolation"
  exit 1
fi

if [[ ! -x "$GATEWAY" ]]; then
  echo "Missing gateway executable after editable install: $GATEWAY"
  echo "Try: ./.venv312/bin/pip install -e . --no-build-isolation"
  exit 1
fi

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "Missing local .env. Configure TELEGRAM_BOT_TOKEN and gateway env vars first."
  exit 1
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] starting ARI Telegram Gateway" >> "$LOG_FILE"
nohup "$GATEWAY" >> "$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" > "$PID_FILE"
sleep 1

if kill -0 "$pid" 2>/dev/null; then
  echo "ARI Telegram Gateway started with PID $pid."
  echo "Log: $LOG_FILE"
else
  rm -f "$PID_FILE"
  echo "ARI Telegram Gateway failed to stay running. See $LOG_FILE."
  exit 1
fi
