# Sourced by automation scripts. Ensures Postgres is up before proceeding,
# starting it automatically if it's down — reduces manual intervention for
# scheduled/unattended runs. Requires REPO_ROOT to already be set.

_ensure_postgres() {
  if docker compose -f "$REPO_ROOT/compose.yaml" exec -T postgres pg_isready -U ari -d ari -q 2>/dev/null; then
    return 0
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [_ensure_postgres] Postgres not ready, attempting to start it."
  if ! docker info >/dev/null 2>&1; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [_ensure_postgres] Docker daemon isn't running — cannot auto-start Postgres. Open Docker Desktop manually."
    return 1
  fi

  (cd "$REPO_ROOT" && docker compose up -d postgres) >/dev/null 2>&1

  for i in $(seq 1 15); do
    if docker compose -f "$REPO_ROOT/compose.yaml" exec -T postgres pg_isready -U ari -d ari -q 2>/dev/null; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [_ensure_postgres] Postgres is now ready."
      return 0
    fi
    sleep 1
  done

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [_ensure_postgres] Postgres did not become ready within 15s."
  return 1
}
