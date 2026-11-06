"""ARI's control panel: one read-only snapshot of what is inside ARI right now.

Surfaces display this; they never compute their own version of it. Everything
here comes from ARI's records: the same open loops, state, alerts, reminders,
memory, and conversations the brain reads and writes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ari_memory.tables import AlertRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_core.action_desk import ActionDesk
from ari_core.apple import AppleDesk, AppleError
from ari_core.brain_usage import month_spend
from ari_core.builds import list_builds
from ari_core.core.pause import get_pause_state
from ari_core.memory import get_conversation_state
from ari_core.modules.memory.db import list_ari_memories
from ari_core.modules.notes.db import search_ari_notes
from ari_core.modules.tasks.db import list_ari_tasks
from ari_core.reminders import pending_reminders
from ari_core.state import get_daily_state, get_weekly_state, list_open_loops

HUB_CHANNEL = "hub"
CHANNELS = ("imessage", HUB_CHANNEL)
RECENT_MESSAGES = 12
RECENT_ALERTS = timedelta(days=2)


def _apple_view(apple: AppleDesk | None, current: datetime) -> dict[str, Any]:
    """GET DONE and today's calendar, as Apple has them. The panel still loads if Apple can't answer."""
    if apple is None:
        return {"apple": {"connected": False, "error": None}, "getDone": [], "calendarToday": []}
    start = datetime.combine(current.astimezone().date(), datetime.min.time()).astimezone()
    try:
        get_done = apple.get_done()
        events = apple.events(start, start + timedelta(days=1))
    except AppleError as error:
        return {"apple": {"connected": True, "error": str(error)}, "getDone": [], "calendarToday": []}
    return {"apple": {"connected": True, "error": None}, "getDone": get_done, "calendarToday": events}


def build_panel(
    session: Session,
    *,
    spine_db_path: Path,
    action_desk: ActionDesk | None,
    now: datetime | None = None,
    apple: AppleDesk | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(tz=UTC)
    today = current.astimezone().date()
    apple_view = _apple_view(apple, current)
    daily = get_daily_state(session, day=today)
    weekly = get_weekly_state(session, state_date=today)
    return {
        "generatedAt": current.isoformat(),
        "paused": get_pause_state(),
        "today": None if daily is None else daily.model_dump(mode="json"),
        "week": None if weekly is None else weekly.model_dump(mode="json"),
        "openLoops": [
            {
                "id": str(loop.id),
                "title": loop.title,
                "kind": loop.kind,
                "priority": loop.priority,
                "notes": loop.notes,
                "openedAt": loop.opened_at.isoformat(),
                "lastTouchedAt": None if loop.last_touched_at is None else loop.last_touched_at.isoformat(),
            }
            for loop in list_open_loops(session)
        ],
        "hubTasks": [
            {"id": row["id"], "title": row["title"], "notes": row["notes"]}
            for row in list_ari_tasks(limit=50, db_path=spine_db_path)
            if row["status"] == "open"
        ],
        "reminders": [reminder.describe() for reminder in pending_reminders(session)],
        **apple_view,
        "builds": [build.describe() for build in list_builds(session)],
        "alerts": _recent_alerts(session, since=current - RECENT_ALERTS),
        "memories": [
            {"id": row["id"], "kind": row["type"], "title": row["title"], "content": row["content"]}
            for row in list_ari_memories(limit=20, db_path=spine_db_path)
        ],
        "notes": [
            {"id": row["id"], "title": row["title"], "body": row["body"]}
            for row in search_ari_notes("", limit=10, db_path=spine_db_path)
        ],
        "conversations": {channel: recent_exchange(session, channel=channel) for channel in CHANNELS},
        "spend": _spend(session),
        "waitingForApproval": [
            {"taskId": item.task_id, "summary": item.summary, "createdAt": item.created_at}
            for item in (action_desk.pending() if action_desk else [])
        ],
    }


def recent_exchange(session: Session, *, channel: str, limit: int = RECENT_MESSAGES) -> list[dict[str, str]]:
    """The visible text of a channel's recent conversation: what Alec said and what ARI said."""
    state = get_conversation_state(session, channel=channel)
    lines: list[dict[str, str]] = []
    for message in [] if state is None else state.messages:
        text = _visible_text(message.get("content"))
        if text:
            lines.append({"role": "alec" if message.get("role") == "user" else "ari", "text": text})
    return lines[-limit:]


def _visible_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    # The brain adds a "(Sent ...)" block to each user turn; it isn't something Alec said.
    parts = [
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and not str(block.get("text", "")).startswith("(Sent ")
    ]
    return "\n".join(part for part in parts if part).strip()


def _recent_alerts(session: Session, *, since: datetime) -> list[dict[str, Any]]:
    bound = since.astimezone(UTC)
    if session.get_bind().dialect.name == "sqlite":
        bound = bound.replace(tzinfo=None)
    rows = session.scalars(
        select(AlertRow).where(AlertRow.created_at >= bound).order_by(AlertRow.created_at.desc())
    ).all()
    return [
        {
            "id": str(row.id),
            "day": row.state_date.isoformat(),
            "status": row.status,
            "level": row.escalation_level,
            "title": row.title,
            "message": row.message,
            "reason": row.reason,
            "sentAt": None if row.sent_at is None else row.sent_at.isoformat(),
        }
        for row in rows
    ]


def _spend(session: Session) -> dict[str, Any]:
    spend = month_spend(session)
    return {
        "spentUsd": round(spend.spent_usd, 4),
        "budgetUsd": spend.budget_usd,
        "requests": spend.requests,
        "deeperModelRequests": spend.escalated_requests,
        "summary": spend.describe(),
    }


_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
AMBIENT_ACTIVITY_MAX = 80


def ambient_status(
    session: Session,
    *,
    spine_db_path: Path,
    action_desk: ActionDesk | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """ARI in one glance, for ambient surfaces (the screensaver, a phone widget).

    Deliberately tiny: a state word, one line of what ARI is on, and how much is waiting.
    It names one thing at most, never notes, messages, memory, or spend; those stay in
    the panel. The state is the first of these that is true:

    - paused: Alec said stop. Activity is the reason he gave.
    - building / shipping: ARI's builder is working on an approved build. Activity is its title.
    - awaiting approval: an action or a finished build is waiting on Alec's yes.
    - stuck: a build failed and needs a look.
    - idle: nothing in motion. Activity is the most important open loop.

    Queue counts what is waiting on someone: open loops, open hub tasks, and approvals.
    """
    current = now or datetime.now(tz=UTC)
    paused = get_pause_state()
    builds = list_builds(session)
    pending = action_desk.pending() if action_desk else []
    loops = sorted(
        list_open_loops(session),
        key=lambda loop: (_PRIORITY_RANK.get(str(getattr(loop.priority, "value", loop.priority)), 9), loop.opened_at),
    )
    hub_tasks = [row for row in list_ari_tasks(limit=50, db_path=spine_db_path) if row["status"] == "open"]

    def first(status: str) -> str | None:
        return next((build.title for build in builds if build.status == status), None)

    state, activity = "idle", loops[0].title if loops else ""
    if paused.get("paused"):
        state, activity = "paused", paused.get("reason") or ""
    elif first("building") is not None:
        state, activity = "building", f"Building: {first('building')}"
    elif first("shipping") is not None:
        state, activity = "shipping", f"Shipping: {first('shipping')}"
    elif pending:
        state, activity = "awaiting approval", pending[0].summary
    elif first("built") is not None:
        state, activity = "awaiting approval", f"Ready to ship: {first('built')}"
    elif first("stuck") is not None:
        state, activity = "stuck", f"Stuck: {first('stuck')}"

    activity = " ".join(str(activity).split())
    if len(activity) > AMBIENT_ACTIVITY_MAX:
        activity = activity[: AMBIENT_ACTIVITY_MAX - 1].rstrip() + "…"
    return {
        "state": state,
        "activity": activity,
        "queue": len(loops) + len(hub_tasks) + len(pending),
        "updatedAt": current.isoformat(),
    }
