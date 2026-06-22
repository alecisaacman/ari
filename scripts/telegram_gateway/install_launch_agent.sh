#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LABEL="com.alecisaacman.ari.telegram-gateway"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
START_SCRIPT="$REPO_ROOT/scripts/telegram_gateway/start.sh"

mkdir -p "$HOME/Library/LaunchAgents"

python3 - "$PLIST_PATH" "$START_SCRIPT" "$REPO_ROOT" "$LABEL" <<'PY'
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
start_script = sys.argv[2]
repo_root = sys.argv[3]
label = sys.argv[4]

payload = {
    "Label": label,
    "ProgramArguments": [start_script],
    "WorkingDirectory": repo_root,
    "RunAtLoad": True,
    "KeepAlive": False,
    "StandardOutPath": f"{repo_root}/data/telegram/logs/launch-agent.out.log",
    "StandardErrorPath": f"{repo_root}/data/telegram/logs/launch-agent.err.log",
}

with plist_path.open("wb") as file:
    plistlib.dump(payload, file)
PY

echo "Wrote LaunchAgent plist:"
echo "$PLIST_PATH"
echo
echo "It is not loaded automatically."
echo "To enable:"
echo "launchctl load \"$PLIST_PATH\""
echo
echo "To disable:"
echo "launchctl unload \"$PLIST_PATH\""
