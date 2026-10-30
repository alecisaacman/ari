"""ARI's morning and night reviews.

Twice a day ARI looks at where Alec is and where ARI itself falls short. The morning
review lays out the day; the night review says what got done and what's still open.
Each review may propose one thing for ARI to build next, which goes on the build list
for Alec to approve, hold, or decline. ARI never starts building on its own.

Gathering is deterministic and reads only ARI's records and Apple's. Only the writing
calls a model, so a review's facts are always real.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import anthropic
from ari_memory.tables import SkillInvocationRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_core.apple import AppleDesk, AppleError
from ari_core.brain import DEEP_MODEL, make_client
from ari_core.brain_usage import ModelCall, month_spend, record_model_call
from ari_core.build_log import recent_builds, tool_use
from ari_core.build_story import latest_lessons
from ari_core.builds import STILL_OPEN, propose_build
from ari_core.builds import list_builds as _list_builds
from ari_core.modules.notes.db import save_ari_note
from ari_core.modules.skills.catalog import list_skill_manifests
from ari_core.panel import recent_exchange
from ari_core.reminders import pending_reminders
from ari_core.state import get_daily_state, get_weekly_state, list_open_loops

Kind = Literal["morning", "night"]
CHANNEL = "review"
# Thinking counts against this. At 1200 the model spent it all thinking and wrote nothing.
MAX_REVIEW_TOKENS = 8000
REVIEW_EFFORT = "low"

REVIEW_PROMPT = """You are ARI, Alec's personal AI operating system, writing his {kind} \
review. It is sent as one iMessage: plain text, no markdown, no emoji, no exclamation \
points. Calm and direct.

{purpose}

Use only the facts given. Never invent a task, event, or result. Keep it under 120 \
words. Lead with what matters most.

Then look at ARI itself: what shipped recently (shipped_recently, from ARI's build log), \
the lessons from its last build story, \
and whether ARI's tools are actually being used (tool_use_last_week), the skills it \
doesn't have yet, tool errors, things Alec asked for that it couldn't do, and the builds \
already on its list. If one build would clearly \
help Alec most right now and isn't already on the list, propose it. Propose at most one, \
and none if nothing stands out. End the message with the proposal in one line, asking \
him to approve or hold it.

Give the review with send_review.
"""

SEND_REVIEW_TOOL: dict[str, Any] = {
    "name": "send_review",
    "description": "Send the review to Alec, with at most one proposed build.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "The iMessage text, under 120 words."},
            "build": {
                "type": ["object", "null"],
                "description": "The one build to propose, or null.",
                "properties": {
                    "title": {"type": "string", "description": "Short name."},
                    "why": {"type": "string", "description": "One sentence tied to the facts."},
                    "brief": {"type": "string", "description": "What to build and what done looks like, for a coding agent."},
                    "skill_id": {"type": ["string", "null"], "description": "Catalog skill id, if it is one."},
                },
                "required": ["title", "why", "brief"],
            },
        },
        "required": ["message"],
    },
}

PURPOSE = {
    "morning": "Lay out the day: the calendar, the few things on GET DONE and his open "
    "loops that matter today, and any reminders. Suggest what to start with.",
    "night": "Say where he got to today: what he checked off and what moved, then what is "
    "still open, and what tomorrow's calendar starts with.",
}


@dataclass(frozen=True, slots=True)
class Review:
    kind: Kind
    message: str
    build: dict[str, Any] | None
    facts: dict[str, Any]


Write = Callable[[str, dict[str, Any]], tuple[dict[str, Any], ModelCall | None]]


def gather(
    session: Session,
    *,
    kind: Kind,
    now: datetime,
    apple: AppleDesk | None,
) -> dict[str, Any]:
    """Everything a review is allowed to say, read from ARI's records and Apple's."""
    local = now.astimezone()
    today = local.date()
    midnight = datetime.combine(today, datetime.min.time()).astimezone()
    daily = get_daily_state(session, day=today)
    weekly = get_weekly_state(session, state_date=today)
    spend = month_spend(session, now=now)
    facts: dict[str, Any] = {
        "now": local.strftime("%A %B %-d, %-I:%M %p"),
        "today": None if daily is None else daily.model_dump(mode="json"),
        "week": None if weekly is None else weekly.model_dump(mode="json"),
        "open_loops": [
            {"title": loop.title, "priority": loop.priority, "notes": loop.notes[-300:]}
            for loop in list_open_loops(session)
        ],
        "timed_reminders": [reminder.describe() for reminder in pending_reminders(session)],
        "talked_about_today": [
            line
            for channel in ("imessage", "hub")
            for line in recent_exchange(session, channel=channel, limit=12)
        ],
        "tool_errors_last_day": _tool_errors(session, since=now - timedelta(days=1)),
        "build_list": [build.describe() for build in _list_builds(session, statuses=STILL_OPEN)],
        "shipped_recently": recent_builds(session, since=now - timedelta(days=1)),
        "tool_use_last_week": tool_use(session, since=now - timedelta(days=7)),
        "lessons_from_last_build_story": latest_lessons(),
        "skills_not_built": [
            {"skill_id": manifest.skill_id, "name": manifest.name, "purpose": manifest.purpose}
            for manifest in list_skill_manifests()
            if manifest.lifecycle_status == "candidate"
        ],
        "spend": {"spent_usd": round(spend.spent_usd, 2), "budget_usd": spend.budget_usd},
    }
    if apple is None:
        facts["apple"] = "Reminders and Calendar aren't connected."
        return facts
    reads: dict[str, Callable[[], Any]] = {
        "get_done": lambda: [{"title": item["title"], "due": item.get("due")} for item in apple.get_done()],
    }
    if kind == "morning":
        reads["calendar_today"] = lambda: _local_events(apple.events(midnight, midnight + timedelta(days=1)))
    else:
        reads["checked_off_today"] = lambda: [item["title"] for item in apple.completed(midnight, now)]
        reads["calendar_tomorrow"] = lambda: _local_events(
            apple.events(midnight + timedelta(days=1), midnight + timedelta(days=2))
        )
    # Each read stands alone, so one failure doesn't hide the rest.
    for key, read in reads.items():
        try:
            facts[key] = read()
        except AppleError as error:
            facts[key] = f"Couldn't read this from Apple: {error}"
    return facts


def _local_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calendar times as Alec reads them: local clock times, not UTC timestamps."""

    def clock(value: Any) -> Any:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%-I:%M %p")
        except ValueError:
            return value

    return [
        {**event, "start": clock(event.get("start")), "end": clock(event.get("end"))} if not event.get("all_day") else event
        for event in events
    ]


def write_with_model(kind: str, facts: dict[str, Any]) -> tuple[dict[str, Any], ModelCall | None]:
    client = make_client()
    response = client.messages.create(
        model=DEEP_MODEL,
        max_tokens=MAX_REVIEW_TOKENS,
        system=REVIEW_PROMPT.format(kind=kind, purpose=PURPOSE[kind]),
        messages=[{"role": "user", "content": json.dumps(facts, default=str)}],
        tools=[SEND_REVIEW_TOOL],
        tool_choice={"type": "auto"},
        thinking={"type": "adaptive"},
        output_config={"effort": REVIEW_EFFORT},
    )
    for block in response.content:
        if getattr(block, "type", "") == "tool_use" and isinstance(getattr(block, "input", None), dict):
            return dict(block.input), ModelCall.from_response(response)
    text = "".join(getattr(block, "text", "") for block in response.content)
    return _parse(text), ModelCall.from_response(response)


def run_review(
    session: Session,
    *,
    kind: Kind,
    now: datetime | None = None,
    apple: AppleDesk | None = None,
    write: Write = write_with_model,
    spine_db_path: Path | None = None,
) -> Review | None:
    """Gather, write, and keep a review. None when the budget has no room for it."""
    current = now or datetime.now(tz=UTC)
    if month_spend(session, now=current).exhausted:
        return None
    facts = gather(session, kind=kind, now=current, apple=apple)
    try:
        written, call = write(kind, facts)
    except anthropic.APIError:
        return None
    if call is not None:
        record_model_call(session, call, channel=CHANNEL, escalated=True)
    message = str(written.get("message") or "").strip()
    if not message:
        return None
    build = written.get("build") if isinstance(written.get("build"), dict) else None
    if build and build.get("title"):
        proposal, is_new = propose_build(
            session,
            title=str(build["title"]),
            why=str(build.get("why") or ""),
            brief=str(build.get("brief") or ""),
            skill_id=build.get("skill_id") or None,
            now=current,
        )
        build = {**proposal.describe(), "new": is_new}
    else:
        build = None
    title = f"{kind.capitalize()} review, {current.astimezone().strftime('%a %b %-d')}"
    kwargs = {} if spine_db_path is None else {"db_path": spine_db_path}
    save_ari_note(title, message, **kwargs)
    return Review(kind=kind, message=message, build=build, facts=facts)


def _tool_errors(session: Session, *, since: datetime) -> list[str]:
    rows = session.scalars(
        select(SkillInvocationRow)
        .where(SkillInvocationRow.occurred_at >= since, SkillInvocationRow.is_error.is_(True))
        .order_by(SkillInvocationRow.occurred_at)
    ).all()
    return [f"{row.tool_name}: {row.summary[:160]}" for row in rows][-10:]


def _parse(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return {"message": text.strip(), "build": None}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"message": text.strip(), "build": None}
    return parsed if isinstance(parsed, dict) else {"message": text.strip(), "build": None}
