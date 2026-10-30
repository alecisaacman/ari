"""ARI's content engine: the week's builds, told as a story.

Once a week (Sunday evening, or "ARI story" any time) ARI turns its build log into a
short story of what was built and why, what it taught ARI about what's actually useful,
and outlines for short-form videos. The lessons come first: they are what ARI's reviews
read next, so the story feeds its self-improvement. The scripts are raw material for
Alec's own posts; ARI never posts anything.

The facts are gathered deterministically from ARI's records; only the writing calls a
model, and it may use only those facts. Each story is kept as an ARI note.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anthropic
from ari_memory.tables import BuildProposalRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_core.brain import DEEP_MODEL, make_client
from ari_core.brain_usage import ModelCall, month_spend, record_model_call
from ari_core.build_log import recent_builds, tool_use
from ari_core.modules.notes.db import save_ari_note, search_ari_notes

CHANNEL = "story"
TITLE_PREFIX = "Build story"
WEEK = timedelta(days=7)
MAX_STORY_TOKENS = 8000
STORY_EFFORT = "low"
LESSONS_HEADING = "What ARI learned"

STORY_PROMPT = """You are ARI, Alec's personal AI operating system. Alec is building you, \
with Claude, in the open. Write this week's build story from the facts given: ARI's build \
log (each release, with what changed and why, in the commits' own words), how often each \
of ARI's tools was actually used, and the builds that were proposed, approved, or shipped.

Use only those facts. Never invent a feature, a number, or a result. Plain words, no \
hype, no emoji, no exclamation points. Write about ARI in the third person and Alec by name.

Give it with send_story:
- lessons: two to four short, specific lessons for ARI's own self-improvement. What was \
worth building, what isn't being used yet, what broke and why. These matter most.
- story: the week as a story, 150 to 300 words. Start with the problem that started it, \
then what was built, then what changed for Alec.
- scripts: one or two short-form video outlines (30 to 60 seconds), each with a hook (one \
line that makes someone stop scrolling), three to five beats, and a caption."""

SEND_STORY_TOOL: dict[str, Any] = {
    "name": "send_story",
    "description": "Keep this week's build story.",
    "input_schema": {
        "type": "object",
        "properties": {
            "lessons": {"type": "array", "items": {"type": "string"}},
            "story": {"type": "string"},
            "scripts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "hook": {"type": "string"},
                        "beats": {"type": "array", "items": {"type": "string"}},
                        "caption": {"type": "string"},
                    },
                    "required": ["hook", "beats", "caption"],
                },
            },
        },
        "required": ["lessons", "story", "scripts"],
    },
}

Write = Callable[[dict[str, Any]], tuple[dict[str, Any], ModelCall | None]]


@dataclass(frozen=True, slots=True)
class Story:
    title: str
    lessons: list[str]
    story: str
    scripts: list[dict[str, Any]]

    def note(self) -> str:
        parts = [LESSONS_HEADING, *(f"- {lesson}" for lesson in self.lessons), "", "The story", self.story]
        for number, script in enumerate(self.scripts, start=1):
            parts += ["", f"Short-form {number}", f"Hook: {script.get('hook', '')}"]
            parts += [f"{index}. {beat}" for index, beat in enumerate(script.get("beats") or [], start=1)]
            parts.append(f"Caption: {script.get('caption', '')}")
        return "\n".join(parts)

    def message(self) -> str:
        """The iMessage: the story itself, then the first hook. The rest is in the hub."""
        hook = self.scripts[0]["hook"] if self.scripts else ""
        tail = f"\n\nVideo hook: {hook}" if hook else ""
        return f"This week's build story.\n\n{self.story}{tail}\n\nLessons and scripts are in the hub, under Notes."


def gather(session: Session, *, now: datetime) -> dict[str, Any]:
    since = now - WEEK
    decided = session.scalars(
        select(BuildProposalRow).where(BuildProposalRow.created_at >= since)
    ).all()
    return {
        "week_ending": now.astimezone().strftime("%A %B %-d"),
        "shipped": recent_builds(session, since=since),
        "tool_use": tool_use(session, since=since),
        "builds": [{"title": row.title, "why": row.why, "status": row.status} for row in decided],
    }


def write_with_model(facts: dict[str, Any]) -> tuple[dict[str, Any], ModelCall | None]:
    response = make_client().messages.create(
        model=DEEP_MODEL,
        max_tokens=MAX_STORY_TOKENS,
        system=STORY_PROMPT,
        messages=[{"role": "user", "content": json.dumps(facts, default=str)}],
        tools=[SEND_STORY_TOOL],
        tool_choice={"type": "auto"},
        thinking={"type": "adaptive"},
        output_config={"effort": STORY_EFFORT},
    )
    for block in response.content:
        if getattr(block, "type", "") == "tool_use" and isinstance(getattr(block, "input", None), dict):
            return dict(block.input), ModelCall.from_response(response)
    return {}, ModelCall.from_response(response)


def run_story(
    session: Session,
    *,
    now: datetime | None = None,
    write: Write = write_with_model,
    spine_db_path: Path | None = None,
) -> Story | None:
    """Gather, write, and keep the week's story. None when nothing shipped or there's no budget."""
    current = now or datetime.now(tz=UTC)
    facts = gather(session, now=current)
    if not facts["shipped"] or month_spend(session, now=current).exhausted:
        return None
    try:
        written, call = write(facts)
    except anthropic.APIError:
        return None
    if call is not None:
        record_model_call(session, call, channel=CHANNEL, escalated=True)
    story_text = str(written.get("story") or "").strip()
    if not story_text:
        return None
    start = (current - WEEK + timedelta(days=1)).astimezone()
    story = Story(
        title=f"{TITLE_PREFIX}, week of {start.strftime('%b %-d')}",
        lessons=[str(lesson).strip() for lesson in written.get("lessons") or [] if str(lesson).strip()],
        story=story_text,
        scripts=[script for script in written.get("scripts") or [] if isinstance(script, dict)],
    )
    kwargs = {} if spine_db_path is None else {"db_path": spine_db_path}
    save_ari_note(story.title, story.note(), **kwargs)
    return story


def latest_lessons(spine_db_path: Path | None = None) -> list[str]:
    """The lessons from the most recent build story, for ARI's reviews to build on."""
    kwargs = {} if spine_db_path is None else {"db_path": spine_db_path}
    for row in search_ari_notes(TITLE_PREFIX, limit=5, **kwargs):
        if not row["title"].startswith(TITLE_PREFIX):
            continue
        section = row["body"].split("\n\n", 1)[0]
        return [line[2:].strip() for line in section.splitlines() if line.startswith("- ")]
    return []

