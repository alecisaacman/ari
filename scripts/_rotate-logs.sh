# Sourced by automation scripts. Keeps launchd-redirected log files from
# growing unbounded under continuous polling — macOS's own newsyslog only
# rotates files registered in /etc/newsyslog.d, and ARI's logs intentionally
# stay inside the repo, so rotation has to be self-contained here instead.
# Requires REPO_ROOT to already be set.

ARI_LOG_MAX_BYTES=$((5 * 1024 * 1024))  # 5MB
ARI_LOG_KEEP=5

_rotate_log_if_large() {
  local log_path="$1"
  [[ -f "$log_path" ]] || return 0

  local size
  size=$(stat -f%z "$log_path" 2>/dev/null || echo 0)
  [[ "$size" -lt "$ARI_LOG_MAX_BYTES" ]] && return 0

  for i in $(seq $((ARI_LOG_KEEP - 1)) -1 1); do
    [[ -f "${log_path}.${i}.gz" ]] && mv "${log_path}.${i}.gz" "${log_path}.$((i + 1)).gz"
  done
  rm -f "${log_path}.${ARI_LOG_KEEP}.gz"

  gzip -c "$log_path" > "${log_path}.1.gz"
  : > "$log_path"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [_rotate_log_if_large] rotated $log_path (was ${size} bytes)"
}
