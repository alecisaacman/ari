#!/usr/bin/env bash
# Reverse scripts/ari-killswitch.sh: remove the PAUSED flag and reload every
# ARI launchd agent that has a plist installed in ~/Library/LaunchAgents.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAUSED_FILE="$REPO_ROOT/state/PAUSED"

if [[ -f "$PAUSED_FILE" ]]; then
  rm "$PAUSED_FILE"
  echo "Removed $PAUSED_FILE"
else
  echo "Not paused (no PAUSED file found)."
fi

echo "Reloading ARI launchd agents..."
for plist in ~/Library/LaunchAgents/com.ari.*.plist; do
  [[ -e "$plist" ]] || continue
  label=$(basename "$plist" .plist)
  if launchctl list | grep -q "$label"; then
    echo "  $label already loaded"
  else
    launchctl load "$plist" && echo "  loaded $label"
  fi
done

echo ""
echo "ARI is resumed."
