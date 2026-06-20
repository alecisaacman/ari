#!/usr/bin/env bash
# Immediately halt all autonomous ARI behavior.
#
# Two layers, both applied:
#   1. Creates state/PAUSED, which every ARI automation entry point checks
#      first and exits on — defense in depth even if step 2 fails.
#   2. Unloads every com.ari.* launchd agent, stopping scheduled execution
#      outright.
#
# Reverse with scripts/ari-resume.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAUSED_FILE="$REPO_ROOT/state/PAUSED"

mkdir -p "$REPO_ROOT/state"
{
  echo "paused_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "reason: ${1:-manual killswitch}"
} > "$PAUSED_FILE"
echo "Wrote $PAUSED_FILE"

echo "Unloading ARI launchd agents..."
for plist in ~/Library/LaunchAgents/com.ari.*.plist; do
  [[ -e "$plist" ]] || continue
  label=$(basename "$plist" .plist)
  if launchctl list | grep -q "$label"; then
    launchctl unload "$plist" && echo "  unloaded $label"
  else
    echo "  $label not loaded"
  fi
done

echo ""
echo "ARI is paused. Nothing scheduled will run, and any script that does run will exit immediately."
echo "Resume with: scripts/ari-resume.sh"
