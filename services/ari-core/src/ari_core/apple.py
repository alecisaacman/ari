"""Apple Reminders and Calendar, through ARI's EventKit helper (tools/ari-eventkit).

Both sync through iCloud, so what ARI writes here reaches Alec's iPhone, and a reminder
with a time goes off there even while the Mac is asleep. ARI writes reminders to one
list, GET DONE.

The connection is off unless ARI_APPLE_CONNECTED=1 (set in ~/ARI/ari.env by
`ari-live setup`), so tests and development checkouts never touch Alec's real lists.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from ari_core.core.env import ari_home

GET_DONE = "GET DONE"
DEFAULT_CALENDAR = "ARI"
HELPER_TIMEOUT_SECONDS = 30


class AppleError(RuntimeError):
    """Reminders or Calendar refused, or the helper couldn't run."""


class Runner(Protocol):
    def __call__(self, command: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def helper_path() -> Path:
    return Path(os.environ.get("ARI_EVENTKIT") or ari_home() / "bin" / "ari-eventkit")


def run_helper(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(helper_path()), command],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=HELPER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppleError(f"ARI's Reminders and Calendar helper didn't run: {error}") from error
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AppleError(
            f"ARI's Reminders and Calendar helper failed: {completed.stderr.strip()[:200]}"
        ) from error
    if completed.returncode != 0 or "error" in result:
        raise AppleError(str(result.get("error") or "Reminders or Calendar refused it."))
    return result


@dataclass(frozen=True, slots=True)
class AppleDesk:
    run: Runner = run_helper
    reminders_list: str = GET_DONE
    default_calendar: str = DEFAULT_CALENDAR

    @classmethod
    def connected(cls) -> AppleDesk | None:
        if os.environ.get("ARI_APPLE_CONNECTED") != "1" or not helper_path().exists():
            return None
        return cls(
            reminders_list=os.environ.get("ARI_REMINDERS_LIST") or GET_DONE,
            default_calendar=os.environ.get("ARI_CALENDAR") or DEFAULT_CALENDAR,
        )

    def get_done(self) -> list[dict[str, Any]]:
        return self.run("reminders", {"list": self.reminders_list})["reminders"]

    def completed(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """GET DONE items checked off between start and end."""
        return self.run("completed", {"list": self.reminders_list, "start": _iso(start), "end": _iso(end)})["reminders"]

    def add_reminder(
        self, title: str, *, due: datetime | None = None, notes: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"list": self.reminders_list, "title": title.strip()}
        if due is not None:
            payload["due"] = _iso(due)
        if notes:
            payload["notes"] = notes
        return self.run("add-reminder", payload)["reminder"]

    def complete_reminder(self, reminder_id: str) -> dict[str, Any]:
        return self.run("complete-reminder", {"id": reminder_id})["reminder"]

    def remove_reminder(self, reminder_id: str) -> dict[str, Any]:
        return self.run("remove-reminder", {"id": reminder_id})["reminder"]

    def events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return self.run("events", {"start": _iso(start), "end": _iso(end)})["events"]

    def add_event(
        self,
        title: str,
        *,
        start: datetime,
        end: datetime | None = None,
        calendar: str | None = None,
        notes: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "calendar": calendar or self.default_calendar,
            "title": title.strip(),
            "start": _iso(start),
            "end": _iso(end or start + timedelta(hours=1)),
        }
        if notes:
            payload["notes"] = notes
        if location:
            payload["location"] = location
        return self.run("add-event", payload)["event"]


def _iso(when: datetime) -> str:
    if when.tzinfo is None:
        when = when.astimezone()
    return when.isoformat(timespec="seconds")
