"""Everyday requests ARI answers itself, without calling a model.

Most of what Alec texts ARI is a plain request with one meaning: "what's on my list",
"add milk to get done", "pause the music", "what's on my calendar tomorrow". ARI's own
code can do those exactly, instantly, and for free, so they never reach the API. Only
messages that need judgment or wording go to the model.

The patterns are deliberately strict. A message that doesn't clearly match one, or
whose target isn't real (an app that isn't installed, a shortcut that doesn't exist, a
to-do that matches more than one item), returns None and goes to the model as before.
Getting a request wrong is worse than paying a fraction of a cent for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from ari_core.apple import AppleDesk, AppleError
from ari_core.mac import MacDesk, MacError

APP_FOLDERS = (Path("/Applications"), Path("/System/Applications"), Path.home() / "Applications")
LIST_NAMES = r"(?:get done|my get done list|get done list|my list|the list|my to-?do list|my to-?dos?|to-?do list)"


@dataclass(frozen=True, slots=True)
class LocalAnswer:
    reply: str
    intent: str


def answer(
    text: str, *, apple: AppleDesk | None, mac: MacDesk | None, now: datetime, dry_run: bool = False
) -> LocalAnswer | None:
    """ARI's own answer to a plain request, or None when the model should handle it."""
    said = " ".join(text.strip().split()).rstrip(".!")
    command = said.lower().replace("’", "'")
    for handler in (_get_done, _calendar, _mac):
        try:
            result = handler(command, said, apple=apple, mac=mac, now=now, dry_run=dry_run)
        except (AppleError, MacError):
            return None  # the model can explain the failure in context
        if result is not None:
            return result
    return None


# --- GET DONE --------------------------------------------------------------------------


def _get_done(command: str, said: str, *, apple: AppleDesk | None, dry_run: bool, **_: Any) -> LocalAnswer | None:
    if apple is None:
        return None
    if re.fullmatch(rf"(?:what'?s on |show me |show |list |read me )?{LIST_NAMES}\??", command) or re.fullmatch(
        r"what do i (?:have to|need to) (?:do|get done)\??", command
    ):
        items = [item for item in apple.get_done() if not item.get("completed")]
        if not items:
            return LocalAnswer("GET DONE is clear.", "get_done_list")
        lines = "\n".join(f"- {item['title']}" for item in items[:15])
        more = f"\n…and {len(items) - 15} more." if len(items) > 15 else ""
        return LocalAnswer(f"GET DONE ({len(items)}):\n{lines}{more}", "get_done_list")

    added = re.fullmatch(rf"(?:add|put) (.+?) (?:to|on) {LIST_NAMES}", said, re.IGNORECASE)
    if added:
        if dry_run:
            return None
        title = added.group(1).strip().strip('"“”')
        apple.add_reminder(title[:1].upper() + title[1:])
        return LocalAnswer(f"Added to GET DONE: {title}.", "add_to_get_done")

    done = re.fullmatch(r"(?:check off|cross off|mark|complete|done with|finished) (.+?)(?: as)?(?: done| complete| off)?", command)
    if done:
        wanted = done.group(1).strip().strip('"“”')
        matches = [item for item in apple.get_done() if not item.get("completed") and wanted in item["title"].lower()]
        if len(matches) != 1 or dry_run:
            return None  # none or several: the model asks which one
        apple.complete_reminder(matches[0]["id"])
        return LocalAnswer(f"Checked off: {matches[0]['title']}.", "complete_get_done")
    return None


# --- Calendar -------------------------------------------------------------------------


def _calendar(command: str, said: str, *, apple: AppleDesk | None, now: datetime, **_: Any) -> LocalAnswer | None:
    if apple is None:
        return None
    asked = re.fullmatch(
        r"(?:what'?s on |what is on |show )?(?:my )?(?:calendar|schedule)(?: for)?(?: (today|tomorrow))?\??"
        r"|what do i have (today|tomorrow)\??|what'?s (?:my schedule|on) (today|tomorrow)\??",
        command,
    )
    if asked:
        which = next((group for group in asked.groups() if group), "today")
        local = now.astimezone()
        day = local.date() + timedelta(days=1 if which == "tomorrow" else 0)
        start = datetime.combine(day, time.min).astimezone()
        events = sorted(apple.events(start, start + timedelta(days=1)), key=lambda event: event.get("start", ""))
        if not events:
            return LocalAnswer(f"Nothing on your calendar {which}.", "get_calendar")
        lines = "\n".join(f"- {_clock(event)} {event['title']}" for event in events)
        return LocalAnswer(f"{which.capitalize()}:\n{lines}", "get_calendar")

    if re.fullmatch(r"what'?s next(?: on my calendar| today)?\??", command):
        local = now.astimezone()
        end = datetime.combine(local.date(), time.max).astimezone()
        upcoming = [
            event for event in apple.events(local, end)
            if not event.get("all_day") and _when(event.get("start")) and _when(event["start"]) >= local
        ]
        if not upcoming:
            return LocalAnswer("Nothing else on your calendar today.", "get_calendar")
        first = min(upcoming, key=lambda event: event["start"])
        return LocalAnswer(f"Next: {first['title']} at {_clock(first)}.", "get_calendar")
    return None


def _when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _clock(event: dict[str, Any]) -> str:
    if event.get("all_day"):
        return "All day:"
    moment = _when(event.get("start"))
    return moment.strftime("%-I:%M %p").replace(":00 ", " ") if moment else ""


# --- The Mac --------------------------------------------------------------------------


def _mac(command: str, said: str, *, mac: MacDesk | None, dry_run: bool, **_: Any) -> LocalAnswer | None:
    if mac is None:
        return None
    on_mac = r"(?: on (?:my|the) (?:mac|computer|laptop))?"

    if re.fullmatch(rf"what'?s (?:open|running){on_mac}\??", command):
        status = mac.status()
        apps = ", ".join(status["open_apps"])
        sound = "muted" if status["muted"] else f"volume {status['volume']}"
        return LocalAnswer(
            f"Open: {apps}. {status['front_app']} is in front. {sound.capitalize()}, battery "
            f"{status['battery_percent']}%{' and charging' if status['charging'] else ''}.",
            "mac_status",
        )
    if re.fullmatch(r"(?:what|which) shortcuts(?: can you run| do i have)?(?: on my mac)?\??|list (?:my )?shortcuts", command):
        return LocalAnswer("Your Shortcuts: " + ", ".join(mac.shortcuts()) + ".", "mac_shortcuts")
    if dry_run:
        return None  # everything below changes something on the Mac

    opened = re.fullmatch(rf"(?:open|launch) (.+?){on_mac}", command)
    link = re.search(r"https?://\S+", said)
    if opened and (_installed(opened.group(1)) or (link and opened.group(1).startswith("http"))):
        target = _installed(opened.group(1)) or link.group(0)
        mac.open(target)
        return LocalAnswer(f"Opened {target}.", "mac_open")
    quit_app = re.fullmatch(rf"(?:quit|close) (.+?){on_mac}", command)
    if quit_app and _installed(quit_app.group(1)):
        app = _installed(quit_app.group(1))
        mac.quit(app)
        return LocalAnswer(f"Quit {app}.", "mac_quit")

    volume = re.fullmatch(rf"(?:set )?(?:the |my )?(?:mac'?s? )?volume (?:to )?(\d{{1,3}})%?{on_mac}", command)
    if volume:
        level = max(0, min(int(volume.group(1)), 100))
        mac.volume(level)
        return LocalAnswer(f"Volume {level}.", "mac_volume")
    if re.fullmatch(rf"(mute|unmute)(?: my mac| the mac| it)?{on_mac}", command):
        muted = command.startswith("mute")
        mac.volume(None, muted=muted)
        return LocalAnswer("Muted." if muted else "Unmuted.", "mac_volume")

    if re.fullmatch(rf"(?:pause|play)(?: the)?(?: music| song| spotify)?{on_mac}", command):
        mac.media("play_pause")
        return LocalAnswer("Done.", "mac_media")
    if re.fullmatch(rf"(?:next|skip)(?: the)?(?: song| track)?{on_mac}", command):
        mac.media("next")
        return LocalAnswer("Skipped.", "mac_media")
    if re.fullmatch(rf"(?:previous|last|go back a)(?: song| track){on_mac}", command):
        mac.media("previous")
        return LocalAnswer("Back one.", "mac_media")

    if re.fullmatch(r"lock (?:my |the )?(?:mac|computer|laptop|screen)", command):
        mac.lock()
        return LocalAnswer("Locked.", "mac_lock")
    awake = re.fullmatch(r"keep (?:my |the )?(?:mac|computer|laptop) awake(?: for)? (\d+) (hours?|hrs?|minutes?|mins?)", command)
    if awake:
        minutes = int(awake.group(1)) * (60 if awake.group(2).startswith("h") else 1)
        result = mac.keep_awake(minutes)
        return LocalAnswer(f"Keeping your Mac awake for {result['awake_for_minutes']} minutes.", "mac_keep_awake")

    run = re.fullmatch(r"run (?:the |my )?(?:shortcut )?(.+?)(?: shortcut)?", command)
    if run:
        try:
            ran = mac.run_shortcut(run.group(1))
        except MacError:
            return None  # not one of his Shortcuts: maybe he meant something else
        return LocalAnswer(f"Ran {ran['ran']}.", "mac_shortcut")
    return None


def _installed(name: str) -> str | None:
    """The real name of an installed app, matched without case, or None."""
    wanted = name.strip().lower().removesuffix(".app")
    for folder in APP_FOLDERS:
        try:
            for app in folder.iterdir():
                if app.suffix == ".app" and app.stem.lower() == wanted:
                    return app.stem
        except OSError:
            continue
    return None
