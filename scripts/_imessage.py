"""Shared iMessage send helper for ARI scripts. Not a standalone entry point."""
from __future__ import annotations

import subprocess


def send_imessage(to: str, body: str) -> bool:
    script = f"""
tell application "Messages"
    set theService to 1st service whose service type = iMessage
    set theBuddy to buddy {_osa_str(to)} of theService
    send {_osa_str(body)} to theBuddy
end tell
"""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  osascript error: {result.stderr.strip()}")
        return False
    return True


def _osa_str(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
