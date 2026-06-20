#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$REPO_ROOT/logs"

stop_pid() {
  local name="$1"
  local pidfile="$LOGS/${name}.pid"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name (pid $pid)..."
      kill -TERM "$pid" 2>/dev/null || true
      sleep 1
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    else
      echo "$name not running."
    fi
    rm -f "$pidfile"
  else
    echo "No pid file for $name — may not be running."
  fi
}

stop_pid "ari-api"
stop_pid "ari-hub"

echo "Stopping Postgres..."
cd "$REPO_ROOT"
docker compose stop postgres

echo "ARI stack stopped."
