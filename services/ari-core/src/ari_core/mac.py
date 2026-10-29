"""Alec's Mac, controlled from his phone through ARI.

Alec texts ARI ("open Spotify", "run Put the fan on auto", "volume 30", "lock my Mac") and
ARI does it on the Mac it runs on. Each action is a fixed command with its arguments
passed as arguments, never a script built from his text, and none of them can delete,
send, or buy anything. ARI acts only when Alec asks for that action.

The connection is off unless ARI_MAC_CONTROL=1 (set in ~/ARI/ari.env by `ari-live
setup`), so tests and development checkouts never touch the real Mac.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

COMMAND_TIMEOUT_SECONDS = 20
# A shortcut can take a while (a HomeKit scene, a web request), so it gets longer.
SHORTCUT_TIMEOUT_SECONDS = 60
MAX_AWAKE_MINUTES = 8 * 60
MEDIA_APPS = ("Spotify", "Music")
MEDIA_COMMANDS = {"play_pause": "playpause", "next": "next track", "previous": "previous track"}


class MacError(RuntimeError):
    """The Mac refused, or the command couldn't run."""


class Runner(Protocol):
    def __call__(self, argv: Sequence[str], timeout: float) -> str: ...


def run_command(argv: Sequence[str], timeout: float) -> str:
    try:
        completed = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MacError(f"{argv[0]} didn't finish: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:300]
        raise MacError(detail or f"{argv[0]} failed.")
    return completed.stdout


def start_detached(argv: Sequence[str]) -> None:
    subprocess.Popen(list(argv), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


@dataclass(frozen=True, slots=True)
class MacDesk:
    run: Runner = run_command
    start: Any = start_detached

    @classmethod
    def connected(cls) -> MacDesk | None:
        return cls() if os.environ.get("ARI_MAC_CONTROL") == "1" else None

    def status(self) -> dict[str, Any]:
        """What's in front, what's open, the volume, and the battery."""
        front = self.run(["lsappinfo", "info", "-only", "name", self.run(["lsappinfo", "front"], 5).strip()], 5)
        apps = re.findall(r'"([^"]+)"', self.run(["lsappinfo", "visibleProcessList"], 5))
        battery = self.run(["pmset", "-g", "batt"], 5)
        percent = re.search(r"(\d+)%", battery)
        return {
            "front_app": _quoted_value(front),
            "open_apps": list(dict.fromkeys(app.replace("_", " ") for app in apps)),
            "volume": self._osascript("output volume of (get volume settings)").strip(),
            "muted": self._osascript("output muted of (get volume settings)").strip() == "true",
            "battery_percent": int(percent.group(1)) if percent else None,
            "charging": "AC Power" in battery,
        }

    def shortcuts(self) -> list[str]:
        return [line.strip() for line in self.run(["shortcuts", "list"], COMMAND_TIMEOUT_SECONDS).splitlines() if line.strip()]

    def run_shortcut(self, name: str) -> dict[str, Any]:
        names = self.shortcuts()
        match = _closest(name, names)
        if match is None:
            raise MacError(f"There's no shortcut called {name!r} on the Mac.")
        output = self.run(["shortcuts", "run", match], SHORTCUT_TIMEOUT_SECONDS)
        return {"ran": match, "output": output.strip()[:500]}

    def open(self, target: str) -> dict[str, Any]:
        """Open an app by name, or a web link."""
        target = target.strip()
        if re.match(r"^https?://", target, re.IGNORECASE):
            self.run(["open", target], COMMAND_TIMEOUT_SECONDS)
            return {"opened": target}
        if "/" in target or target.startswith("-"):
            raise MacError("Give an app name or a web link.")
        self.run(["open", "-a", target], COMMAND_TIMEOUT_SECONDS)
        return {"opened": target}

    def quit(self, app: str) -> dict[str, Any]:
        """Quit an app the normal way, so it can ask to save anything unsaved."""
        self._osascript("on run argv\ntell application (item 1 of argv) to quit\nend run", app.strip())
        return {"quit": app.strip()}

    def volume(self, level: int | None = None, *, muted: bool | None = None) -> dict[str, Any]:
        if level is not None:
            self._osascript(f"set volume output volume {max(0, min(int(level), 100))} without output muted")
        if muted is not None:
            self._osascript("set volume with output muted" if muted else "set volume without output muted")
        return {"volume": self._osascript("output volume of (get volume settings)").strip(), "muted": muted}

    def media(self, command: str) -> dict[str, Any]:
        """Play/pause, next, or previous, in Spotify if it's open, otherwise Music."""
        verb = MEDIA_COMMANDS.get(command)
        if verb is None:
            raise MacError(f"Media commands are {', '.join(MEDIA_COMMANDS)}.")
        open_apps = self.run(["lsappinfo", "visibleProcessList"], 5)
        app = next((name for name in MEDIA_APPS if f'"{name}"' in open_apps), MEDIA_APPS[-1])
        # Spotify and Music share these commands; Music's dictionary lets the script compile.
        self._osascript(
            f'on run argv\nusing terms from application "Music"\n'
            f"tell application (item 1 of argv) to {verb}\nend using terms from\nend run",
            app,
        )
        return {"media": command, "app": app}

    def lock(self) -> dict[str, Any]:
        """Turn the display off, which locks the Mac when it asks for a password on wake."""
        self.run(["pmset", "displaysleepnow"], COMMAND_TIMEOUT_SECONDS)
        return {"display": "off"}

    def keep_awake(self, minutes: int) -> dict[str, Any]:
        """Keep the Mac (and so ARI) awake for a while; it sleeps normally afterwards."""
        minutes = max(1, min(int(minutes), MAX_AWAKE_MINUTES))
        self.start(["caffeinate", "-i", "-t", str(minutes * 60)])
        return {"awake_for_minutes": minutes}

    def _osascript(self, script: str, *args: str) -> str:
        return self.run(["osascript", "-e", script, *args], COMMAND_TIMEOUT_SECONDS)


def _quoted_value(text: str) -> str:
    match = re.search(r'="([^"]*)"', text)
    return match.group(1) if match else text.strip()


def _closest(name: str, names: list[str]) -> str | None:
    """The shortcut Alec meant: an exact name, ignoring case and spacing, then a unique partial."""
    wanted = " ".join(name.lower().split())
    for candidate in names:
        if " ".join(candidate.lower().split()) == wanted:
            return candidate
    partial = [candidate for candidate in names if wanted in candidate.lower()]
    return partial[0] if len(partial) == 1 else None
