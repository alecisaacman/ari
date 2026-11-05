"""ARI's content library: every piece of content in one place, with where it stands.

Each item goes through the content process in order:

    idea -> script -> production -> ready -> posted   (or skipped)

An idea is what ARI wrote, or Alec's own rewrite of it. Before an idea can become a
script, ARI reviews it (ari_core.script_review): true to that day's commits, a hook
that earns attention, a clear flow, the right length. Only a script whose current
version passed review can be approved; editing it again needs a new review. Production is
recording, voice, and editing. Ready means the finished piece (a short-form video, or
long-form) exists and can be posted, so nothing reaches ready without production, and
nothing is posted that wasn't ready. Items can step back one stage.

Build days ("Day N of building ARI", written by ari_core.build_story from that day's
commits) are the first kind: the lessons for ARI's reviews, the day as a story, and
short-form outlines. The idea bank, the hub, and ARI's tools all read from here, so
there is one source.

A day that is written again keeps its status: rewriting Day 12's script doesn't make a
posted day look unposted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ari_core.core.paths import DB_PATH
from ari_core.modules.coordination.db import (
    get_coordination_entity,
    list_coordination_entities,
    put_coordination_entity,
)

CONTENT_ITEM_ENTITY = "content_item"
BUILD_DAY = "build_day"
STATUSES = ("idea", "script", "production", "ready", "posted", "skipped")
# Where an item can go from each stage: forward one, back one, or set aside.
MOVES: dict[str, tuple[str, ...]] = {
    "idea": ("script", "skipped"),
    "script": ("production", "idea", "skipped"),
    "production": ("ready", "script"),
    "ready": ("posted", "production"),
    "posted": ("ready",),
    "skipped": ("idea",),
}
# Stages from before the content process had production in it.
LEGACY_STATUSES = {"draft": "idea"}
# A build day starts as an idea: ARI wrote it, Alec hasn't checked it.
NEW_BUILD_DAY_STATUS = "idea"
FORMATS = ("short-form", "long-form")
MAX_ITEMS = 500


@dataclass(frozen=True, slots=True)
class ContentItem:
    item_id: str
    kind: str
    title: str
    hook: str
    status: str
    day_number: int | None = None
    day_date: str | None = None
    lessons: tuple[str, ...] = ()
    story: str = ""
    scripts: tuple[dict[str, Any], ...] = ()
    commit_count: int = 0
    content_format: str = FORMATS[0]
    # The finished video, once ARI's studio has made it: {"path", "voice", "producedAt"}.
    video: dict[str, Any] | None = None
    # ARI's last review of the scripts: {"passed", "notes", "checks", "scriptHash", "reviewedAt"}.
    review: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: _now_iso())
    updated_at: str = field(default_factory=lambda: _now_iso())
    posted_at: str | None = None

    def describe(self) -> dict[str, Any]:
        """For ARI's tools: what it is, where it stands, and its hooks."""
        return {
            "id": self.item_id,
            "title": self.title,
            "status": self.status,
            "date": self.day_date,
            "hooks": [script.get("hook", "") for script in self.scripts],
            "posted_at": self.posted_at,
        }


    def to_dict(self) -> dict[str, Any]:
        """Everything about the item, for the hub's Content tab."""
        return {
            "id": self.item_id,
            "kind": self.kind,
            "title": self.title,
            "hook": self.hook,
            "status": self.status,
            "dayNumber": self.day_number,
            "date": self.day_date,
            "lessons": list(self.lessons),
            "story": self.story,
            "scripts": list(self.scripts),
            "format": self.content_format,
            "video": self.video,
            "review": self.review,
            "reviewCurrent": review_is_current(self),
            "updatedAt": self.updated_at,
            "postedAt": self.posted_at,
        }


def content_view(*, db_path: Path = DB_PATH) -> dict[str, Any]:
    """The whole library, newest first, with how many items are at each status."""
    items = list_content_items(db_path=db_path)
    counts = {status: sum(1 for item in items if item.status == status) for status in STATUSES}
    return {
        "items": [item.to_dict() for item in items],
        "counts": counts,
        "statuses": list(STATUSES),
        "moves": {status: list(targets) for status, targets in MOVES.items()},
    }


def build_day_id(day_number: int) -> str:
    return f"day-{day_number}"


def store_build_day(
    *,
    day_number: int,
    day_date: str,
    title: str,
    lessons: list[str],
    story: str,
    scripts: list[dict[str, Any]],
    commit_count: int,
    db_path: Path = DB_PATH,
) -> ContentItem:
    """Add or rewrite a build day. A rewrite keeps the day's status and when it was posted."""
    item_id = build_day_id(day_number)
    existing = get_content_item(item_id, db_path=db_path)
    item = ContentItem(
        item_id=item_id,
        kind=BUILD_DAY,
        title=title,
        hook=scripts[0].get("hook", "") if scripts else "",
        status=existing.status if existing else NEW_BUILD_DAY_STATUS,
        day_number=day_number,
        day_date=day_date,
        lessons=tuple(lessons),
        story=story,
        scripts=tuple(scripts),
        commit_count=commit_count,
        created_at=existing.created_at if existing else _now_iso(),
        posted_at=existing.posted_at if existing else None,
    )
    return _put(item, db_path=db_path)


def set_status(item_id: str, status: str, *, db_path: Path = DB_PATH) -> ContentItem | None:
    """Move an item one stage along the content process (or back one, or aside)."""
    if status not in STATUSES:
        raise ValueError(f"The stages are {', '.join(STATUSES)}.")
    item = get_content_item(item_id, db_path=db_path)
    if item is None:
        return None
    if status != item.status and status not in MOVES[item.status]:
        allowed = " or ".join(MOVES[item.status])
        raise ValueError(f"{item.title} is at {item.status}; from there it can go to {allowed}.")
    if item.status == "idea" and status == "script" and not _passed(item):
        raise ValueError(f"{item.title} needs ARI's review to pass its current script before it's approved.")
    if status == "ready" and not _video_exists(item):
        raise ValueError(f"{item.title} has no finished video yet, so it can't be ready to post.")
    posted_at = item.posted_at if status == "posted" and item.posted_at else (_now_iso() if status == "posted" else None)
    return _put(_replace(item, status=status, posted_at=posted_at), db_path=db_path)


EDITABLE = ("idea", "script")


def edit_script(
    item_id: str, index: int, *, hook: str, beats: list[str], caption: str, db_path: Path = DB_PATH
) -> ContentItem | None:
    """Replace one of an item's scripts with Alec's version. An approved script goes back
    to idea, because the version that was approved is gone; it needs a new review."""
    item = get_content_item(item_id, db_path=db_path)
    if item is None:
        return None
    if item.status not in EDITABLE:
        raise ValueError(f"{item.title} is in {item.status}; step it back to script to change the words.")
    scripts = list(item.scripts)
    if not 0 <= index < max(len(scripts), 1):
        raise ValueError(f"{item.title} has no script {index + 1}.")
    script = {
        "hook": hook.strip(),
        "beats": [beat.strip() for beat in beats if beat.strip()],
        "caption": caption.strip(),
        "by": "alec",
    }
    if not script["hook"] or not script["beats"]:
        raise ValueError("A script needs a hook and at least one beat.")
    if scripts:
        scripts[index] = script
    else:
        scripts = [script]
    return _put(
        _replace(item, scripts=tuple(scripts), hook=scripts[0]["hook"], status="idea"),
        db_path=db_path,
    )


def record_review(item_id: str, review: dict[str, Any], *, db_path: Path = DB_PATH) -> ContentItem | None:
    """Keep ARI's review, tied to the exact scripts it read."""
    item = get_content_item(item_id, db_path=db_path)
    if item is None:
        return None
    review = {**review, "scriptHash": script_hash(item), "reviewedAt": _now_iso()}
    return _put(_replace(item, review=review), db_path=db_path)


def script_hash(item: ContentItem) -> str:
    return hashlib.sha256(json.dumps(list(item.scripts), sort_keys=True).encode()).hexdigest()[:16]


def review_is_current(item: ContentItem) -> bool:
    return bool(item.review and item.review.get("scriptHash") == script_hash(item))


def _passed(item: ContentItem) -> bool:
    return review_is_current(item) and bool(item.review and item.review.get("passed"))


def attach_video(item_id: str, path: str, *, voice: str, db_path: Path = DB_PATH) -> ContentItem | None:
    """Record the finished video ARI's studio made for an item."""
    item = get_content_item(item_id, db_path=db_path)
    if item is None:
        return None
    video = {"path": path, "voice": voice, "producedAt": _now_iso()}
    return _put(_replace(item, video=video), db_path=db_path)


def _video_exists(item: ContentItem) -> bool:
    return bool(item.video and Path(str(item.video.get("path", ""))).is_file())


def get_content_item(item_id: str, *, db_path: Path = DB_PATH) -> ContentItem | None:
    row = get_coordination_entity(CONTENT_ITEM_ENTITY, item_id, db_path=db_path)
    return None if row is None else _from_row(row)


def list_content_items(
    *, status: str | None = None, kind: str | None = None, limit: int = MAX_ITEMS, db_path: Path = DB_PATH
) -> tuple[ContentItem, ...]:
    """Newest day first."""
    rows = list_coordination_entities(CONTENT_ITEM_ENTITY, limit=MAX_ITEMS, db_path=db_path)
    items = [_from_row(row) for row in rows]
    items = [item for item in items if (status is None or item.status == status) and (kind is None or item.kind == kind)]
    return tuple(items[:limit])


def latest_build_day(*, db_path: Path = DB_PATH) -> ContentItem | None:
    days = list_content_items(kind=BUILD_DAY, limit=1, db_path=db_path)
    return days[0] if days else None


def _put(item: ContentItem, *, db_path: Path) -> ContentItem:
    payload = {
        "lessons": list(item.lessons),
        "story": item.story,
        "scripts": list(item.scripts),
        "commit_count": item.commit_count,
        "format": item.content_format,
        "video": item.video,
        "review": item.review,
    }
    row = put_coordination_entity(
        CONTENT_ITEM_ENTITY,
        {
            "item_id": item.item_id,
            "kind": item.kind,
            "day_number": item.day_number,
            "day_date": item.day_date,
            "title": item.title,
            "hook": item.hook,
            "status": item.status,
            "payload_json": json.dumps(payload, sort_keys=True),
            "created_at": item.created_at,
            "updated_at": _now_iso(),
            "posted_at": item.posted_at,
        },
        db_path=db_path,
    )
    return _from_row(row)


def _from_row(row: Any) -> ContentItem:
    payload = json.loads(row["payload_json"])
    return ContentItem(
        item_id=row["item_id"],
        kind=row["kind"],
        title=row["title"],
        hook=row["hook"],
        status=LEGACY_STATUSES.get(row["status"], row["status"]),
        day_number=row["day_number"],
        day_date=row["day_date"],
        lessons=tuple(payload.get("lessons") or ()),
        story=payload.get("story") or "",
        scripts=tuple(payload.get("scripts") or ()),
        commit_count=int(payload.get("commit_count") or 0),
        content_format=payload.get("format") or FORMATS[0],
        video=payload.get("video"),
        review=payload.get("review"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        posted_at=row["posted_at"],
    )


def _replace(item: ContentItem, **changes: Any) -> ContentItem:
    values = {name: getattr(item, name) for name in item.__dataclass_fields__}
    return ContentItem(**{**values, **changes})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
