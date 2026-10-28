"""What ARI's desktop pet shows: a small status file the poller keeps current.

The pet (tools/ari-pet) lives on the desktop even when the hub is closed. It reads
this file every couple of seconds, so it never calls a model or the API. The iMessage
poller writes it on every poll, and while it is handling a message.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ari_memory.tables import AlertRow
from ari_state import AlertStatus
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ari_core.brain_usage import month_spend
from ari_core.core.env import ari_home
from ari_core.core.pause import get_pause_state
from ari_core.panel import recent_exchange


def status_path() -> Path:
    return ari_home() / "state" / "pet-status.json"


def _credits_marker() -> Path:
    return ari_home() / "state" / "out-of-credits"


def note_credits(*, out: bool) -> None:
    """Remember whether Anthropic last refused for lack of credits."""
    marker = _credits_marker()
    if out:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.now(tz=UTC).isoformat())
    else:
        marker.unlink(missing_ok=True)


def build_pet_status(
    session: Session,
    *,
    now: datetime,
    thinking: bool = False,
    waiting_for_approval: int = 0,
) -> dict[str, Any]:
    pause = get_pause_state()
    spend = month_spend(session, now=now)
    pending_alerts = session.scalar(
        select(func.count()).select_from(AlertRow).where(AlertRow.status == AlertStatus.PENDING.value)
    )
    latest = next(
        (line["text"] for line in reversed(recent_exchange(session, channel="imessage")) if line["role"] == "ari"),
        None,
    )
    return {
        "updatedAt": now.isoformat(),
        "paused": bool(pause["paused"]),
        "pausedReason": pause.get("reason"),
        "thinking": thinking,
        "outOfCredits": _credits_marker().exists(),
        "budgetUsedUp": spend.exhausted,
        "spend": f"${spend.spent_usd:.2f} of ${spend.budget_usd:.0f} this month",
        "needsYou": int(pending_alerts or 0) + waiting_for_approval,
        "latest": latest,
    }


def write_pet_status(status: dict[str, Any], path: Path | None = None) -> None:
    """Replace the file in one step, so the pet never reads half of it."""
    target = path or status_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".pet-status-")
    with os.fdopen(handle, "w") as file:
        json.dump(status, file)
    os.replace(temporary, target)
