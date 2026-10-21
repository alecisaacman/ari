#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ari_runtime.sh"
REPO_ROOT="$(ari_repo_root_from_path "${BASH_SOURCE[0]}")"
LABEL="com.alecisaacman.ari.telegram-gateway"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
START_SCRIPT="$REPO_ROOT/scripts/telegram_gateway/start.sh"
MODE="install"

case "${1:-}" in
  "") ;;
  --check) MODE="check" ;;
  --replace) MODE="replace" ;;
  *) echo "Usage: $0 [--check|--replace]" >&2; exit 2 ;;
esac

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a source-bearing Git checkout: $REPO_ROOT" >&2
  exit 1
fi
if [[ ! -x "$START_SCRIPT" ]]; then
  echo "LaunchAgent target is missing or not executable: $START_SCRIPT" >&2
  exit 1
fi
PYTHON="$(ari_resolve_python "$REPO_ROOT")"

echo "Repository: $REPO_ROOT"
echo "Python: $PYTHON"
echo "LaunchAgent target: $START_SCRIPT"
echo "Plist: $PLIST_PATH"

if [[ "$MODE" == "check" ]]; then
  echo "Preflight passed; no files were written."
  exit 0
fi

if [[ -e "$PLIST_PATH" && "$MODE" != "replace" ]]; then
  echo "Refusing to overwrite existing LaunchAgent: $PLIST_PATH" >&2
  echo "Inspect it first, then rerun with --replace if replacement is intentional." >&2
  exit 2
fi

mkdir -p "$HOME/Library/LaunchAgents"

"$PYTHON" - "$PLIST_PATH" "$START_SCRIPT" "$REPO_ROOT" "$LABEL" <<'PY'
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
