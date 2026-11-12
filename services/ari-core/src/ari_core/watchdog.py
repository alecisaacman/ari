"""ARI's watchdog: every failure reaches Alec by text, once, and never only a log.

Each part of ARI that can fail says so as a `Problem` with a stable key. A one-off
failure (a review that didn't get written) is texted once. A lasting one (GET DONE
can't be read, a message keeps failing, a build stuck shipping) is texted once it has
lasted long enough to matter, so a blip that clears itself stays quiet, and once more
when its source reports it working again.

Messages that can't go out yet (quiet hours, ARI paused, Messages failing) wait in the
watchdog's file and go out later. It never calls a model and costs nothing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ari_memory.tables import BrainUsageRow, BuildProposalRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_core.builds import APPROVED, SHIPPING

# A ship takes minutes: tests, push, install. Past this, the ship step died.
SHIPPING_STALLED_AFTER = timedelta(minutes=30)
# The builder runs nightly, so an approved build waits at most a day; past this it was missed.
APPROVED_WAITING_AFTER = timedelta(hours=30)
# Keys the database check owns: it runs every poll, so one missing now has cleared.
RECORDS = "records:"
# A normal day is a few cents; this many dollars in one day means something is calling the model too much.
DAILY_SPEND_ALERT_USD = 0.25
# Every part of ARI that may spend API credits. Spend from anything else is a leak.
KNOWN_SPEND_CHANNELS = frozenset({"imessage", "hub", "review", "story", "script_review", "company_research"})
# One-offs already told, remembered so a check that repeats every poll doesn't repeat the text.
TOLD_MEMORY = 200


@dataclass(frozen=True, slots=True)
class Problem:
    key: str
    text: str
    # What stopped working, for the message when it works again.
    label: str = ""
    # How long it must last before Alec hears of it.
    after: timedelta = timedelta(0)
    # A lasting problem is also told when it clears; a one-off is told once and forgotten.
    lasting: bool = True


@dataclass(frozen=True, slots=True)
class Notice:
    key: str
    body: str


class Watchdog:
    """Remembers what's wrong and what Alec has been told, in one small file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def observe(self, problems: list[Problem], *, cleared: set[str], now: datetime) -> list[Notice]:
        """Record this poll's problems and what reported working; return what Alec should hear now.

        `cleared` holds keys whose source ran and worked, or prefixes ending in ":" for a
        source that checks everything it owns each time (an open key it didn't report has cleared).
        """
        state = self._load()
        open_, pending = state["open"], state["pending"]
        seen = {problem.key for problem in problems}
        for problem in problems:
            if not problem.lasting:
                # A check that runs every poll reports a one-off again and again; it's told once.
                if problem.key not in state["told"]:
                    pending[problem.key] = problem.text
                continue
            entry = open_.setdefault(
                problem.key, {"since": now.isoformat(), "told": False, "after": problem.after.total_seconds()}
            )
            entry["text"], entry["label"] = problem.text, problem.label
        for key in list(open_):
            prefixes = (prefix for prefix in cleared if prefix.endswith(":"))
            if key in seen or not (key in cleared or any(key.startswith(prefix) for prefix in prefixes)):
                continue
            entry = open_.pop(key)
            if entry["told"]:
                pending[f"fixed:{key}"] = f"{entry.get('label') or 'That'} is working again."
        self._save(state)
        notices = [Notice(key, body) for key, body in pending.items()]
        for key, entry in open_.items():
            since = datetime.fromisoformat(entry["since"])
            if not entry["told"] and now - since >= timedelta(seconds=entry["after"]):
                notices.append(Notice(key, entry["text"]))
        return notices

    def told(self, notice: Notice) -> None:
        """Alec got this one; it isn't sent again."""
        state = self._load()
        if state["pending"].pop(notice.key, None) is not None:
            state["told"] = [*state["told"], notice.key][-TOLD_MEMORY:]
        elif notice.key in state["open"]:
            state["open"][notice.key]["told"] = True
        self._save(state)

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text())
        except (OSError, ValueError):
            state = {}
        return {
            "open": dict(state.get("open") or {}),
            "pending": dict(state.get("pending") or {}),
            "told": list(state.get("told") or []),
        }

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=1))
        os.replace(temporary, self.path)


def check_records(session: Session, *, now: datetime, builder_on: bool) -> list[Problem]:
    """What ARI's own records show is stuck: a ship that died, an approved build nobody picked up."""
    problems: list[Problem] = []
    for row in session.scalars(select(BuildProposalRow).where(BuildProposalRow.status == SHIPPING)):
        # The row doesn't record when shipping started, so the watchdog's own clock times it.
        problems.append(Problem(
            key=f"{RECORDS}shipping:{row.id}",
            text=(f"“{row.title}” has been shipping for over 30 minutes with no result, so the ship "
                  "step most likely stopped partway. Its log is runtime/logs/builder.log under ~/ARI; "
                  "it needs a look before it can ship again."),
            label=f"Shipping “{row.title}”",
            after=SHIPPING_STALLED_AFTER,
        ))
    waiting = session.scalars(
        select(BuildProposalRow).where(BuildProposalRow.status == APPROVED).order_by(BuildProposalRow.decided_at)
    ).first()
    if waiting is not None and waiting.decided_at is not None:
        hours = int((now - _utc(waiting.decided_at)).total_seconds() // 3600)
        if now - _utc(waiting.decided_at) >= APPROVED_WAITING_AFTER:
            why = ("The “ARI builds” task in the Claude app runs it at 10:45 PM, but only while the app is open."
                   if builder_on else "The builder is off; `ari-live connect-builds` turns it on.")
            problems.append(Problem(
                key=f"{RECORDS}approved-waiting",
                text=f"You approved “{waiting.title}” {hours} hours ago and nothing has built it yet. {why}",
                label="The nightly builder",
            ))
    return problems


def check_spend(session: Session, *, now: datetime, daily_alert_usd: float | None = None) -> list[Problem]:
    """API money spent where it shouldn't be: a day far above normal, or a source ARI doesn't know.

    ARI's normal day is a few cents (two reviews, a story, a few replies). Anything that
    spends without being one of ARI's known channels is a leak, however small.
    """
    limit = daily_alert_usd if daily_alert_usd is not None else float(
        os.environ.get("ARI_SPEND_DAILY_ALERT_USD") or DAILY_SPEND_ALERT_USD
    )
    local_midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    # SQLite keeps these timestamps as naive UTC.
    since = local_midnight.replace(tzinfo=None) if session.get_bind().dialect.name == "sqlite" else local_midnight
    today: dict[str, float] = {}
    for usage in session.scalars(select(BrainUsageRow).where(BrainUsageRow.occurred_at >= since)):
        today[usage.channel] = today.get(usage.channel, 0.0) + usage.cost_microusd / 1e6
    problems: list[Problem] = []
    day = now.astimezone().date().isoformat()
    total = sum(today.values())
    if total >= limit:
        parts = ", ".join(f"{channel} ${cost:.2f}" for channel, cost in sorted(today.items(), key=lambda kv: -kv[1]))
        problems.append(Problem(
            key=f"spend-day:{day}",
            text=(f"ARI has spent ${total:.2f} of API credits today, well above a normal day of a few cents "
                  f"({parts}). Something may be calling the model when it shouldn't."),
            lasting=False,
        ))
    unknown = sorted(channel for channel in today if channel not in KNOWN_SPEND_CHANNELS)
    if unknown:
        problems.append(Problem(
            key=f"spend-unknown:{day}:{','.join(unknown)}",
            text=(f"Something ARI doesn't recognize spent API credits today: {', '.join(unknown)}. "
                  "Every model call should come from a known part of ARI."),
            lasting=False,
        ))
    return problems


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; ARI stores UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)
