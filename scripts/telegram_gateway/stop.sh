#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_FILE="$REPO_ROOT/data/telegram/run/gateway.pid"

cd "$REPO_ROOT"

if [[ ! -f "$PID_FILE" ]]; then
  echo "ARI Telegram Gateway is not running: no PID file."
  exit 0
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  echo "Removing invalid PID file: $PID_FILE"
  rm -f "$PID_FILE"
  exit 0
fi

if ! kill -0 "$pid" 2>/dev/null; then
  echo "Removing stale PID file for non-running PID $pid."
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping ARI Telegram Gateway PID $pid..."
kill "$pid"

for _ in {1..20}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "ARI Telegram Gateway stopped."
    exit 0
  fi
  sleep 0.5
done

echo "Gateway did not stop after SIGTERM; sending SIGKILL."
kill -9 "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "ARI Telegram Gateway stopped."
