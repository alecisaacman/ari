"""Send replies into the self-thread through Messages.app.

The text and the handle are passed to AppleScript as arguments, never spliced
into the script, so a reply cannot change what the script does. Sending needs
the macOS Automation permission for whatever process runs the gateway.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

Runner = Callable[..., subprocess.CompletedProcess[str]]

SEND_SCRIPT = """
on run argv
    set theHandle to item 1 of argv
    set theBody to item 2 of argv
    tell application "Messages"
        set theService to 1st service whose service type = iMessage
        set theBuddy to buddy theHandle of theService
        send theBody to theBuddy
    end tell
end run
"""


class MessagesApp:
    def __init__(self, *, runner: Runner = subprocess.run) -> None:
        self.runner = runner
        self.last_error: str | None = None

    def send(self, handle: str, body: str) -> bool:
        completed = self.runner(
            ["/usr/bin/osascript", "-e", SEND_SCRIPT, handle, body],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.last_error = None if completed.returncode == 0 else completed.stderr.strip()
        return completed.returncode == 0
