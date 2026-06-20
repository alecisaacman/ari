#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
LOGS="$REPO_ROOT/logs"

mkdir -p "$LOGS"

if [[ ! -d "$VENV" ]]; then
  echo "ERROR: .venv not found at $VENV — run: python3.12 -m venv .venv && pip install -e '.[dev]'"
  exit 1
fi

source "$VENV/bin/activate"
export PYTHONPATH="$REPO_ROOT/packages/ari-state/src:$REPO_ROOT/packages/ari-memory/src:$REPO_ROOT/packages/ari-events/src:$REPO_ROOT/packages/ari-routines/src:$REPO_ROOT/packages/ari-signals/src:$REPO_ROOT/packages/ari-cli/src:$REPO_ROOT/services/ari-core/src:$REPO_ROOT/services/ari-api/src:$REPO_ROOT/services/ari-hub/src"

echo "Starting Postgres..."
cd "$REPO_ROOT"
docker compose up -d postgres

echo "Waiting for Postgres to be ready..."
for i in $(seq 1 15); do
  if docker compose exec -T postgres pg_isready -U ari -d ari -q 2>/dev/null; then
    echo "Postgres ready."
    break
  fi
  if [[ $i -eq 15 ]]; then
    echo "ERROR: Postgres did not become ready in time."
    exit 1
  fi
  sleep 1
done

echo "Running migrations..."
alembic upgrade head

echo "Starting ari-api on :8000..."
uvicorn ari_api.main:app --host 127.0.0.1 --port 8000 \
  --log-level warning \
  > "$LOGS/ari-api.log" 2>&1 &
echo $! > "$LOGS/ari-api.pid"

echo "Starting ari-hub on :8001..."
uvicorn ari_hub.main:app --host 127.0.0.1 --port 8001 \
  --log-level warning \
  > "$LOGS/ari-hub.log" 2>&1 &
echo $! > "$LOGS/ari-hub.pid"

sleep 1

API_PID=$(cat "$LOGS/ari-api.pid")
HUB_PID=$(cat "$LOGS/ari-hub.pid")

if kill -0 "$API_PID" 2>/dev/null && kill -0 "$HUB_PID" 2>/dev/null; then
  echo ""
  echo "ARI stack running."
  echo "  Hub:  http://localhost:8001"
  echo "  API:  http://localhost:8000"
  echo "  Logs: $LOGS/"
  open http://localhost:8001
else
  echo "ERROR: One or more services failed to start. Check logs in $LOGS/"
  exit 1
fi
