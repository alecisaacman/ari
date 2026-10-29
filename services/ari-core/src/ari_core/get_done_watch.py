"""Notice what Alec adds to GET DONE himself, so nothing he captures goes unseen.

GET DONE syncs through iCloud, so Alec can add to it with no connection, or while the
Mac (and ARI) is asleep. Each look compares the list with the last one ARI saw. Items
that are new, and that ARI didn't write itself, are his: ARI names them and asks whether
to act on them now. The first look only remembers the list, so ARI never announces
everything that was already there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ari_core.apple import AppleDesk

OWN_LOG_SIZE = 200


def record_own(path: Path, reminder_id: str) -> None:
    """Remember a GET DONE item ARI wrote, so it is never mistaken for one of Alec's."""
    own = _read_ids(path) or []
    if reminder_id in own:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([*own, reminder_id][-OWN_LOG_SIZE:]))


def new_from_alec(apple: AppleDesk, seen_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The open GET DONE items Alec added since ARI last looked, and every open item's id.

    Pass the ids to mark_seen once Alec has been asked, so a failed send asks again.
    On the first look nothing is new. Raises AppleError when Reminders can't be read.
    """
    current = [item for item in apple.get_done() if not item.get("completed")]
    ids = [item["id"] for item in current]
    seen = _read_ids(seen_path)
    if seen is None:
        return [], ids
    own = set(_read_ids(apple.own_log) or []) if apple.own_log is not None else set()
    known = set(seen) | own
    return [item for item in current if item["id"] not in known], ids


def mark_seen(seen_path: Path, ids: list[str]) -> None:
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(ids))


def describe(items: list[dict[str, Any]]) -> str:
    titles = [item["title"].strip() or "(untitled)" for item in items]
    if len(titles) == 1:
        return f"You added to GET DONE while I was away: “{titles[0]}”. Want me to act on it now?"
    listed = "\n".join(f"- {title}" for title in titles)
    return f"You added these to GET DONE:\n{listed}\nWant me to act on any of them now?"


def _read_ids(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return [str(item) for item in value] if isinstance(value, list) else None
