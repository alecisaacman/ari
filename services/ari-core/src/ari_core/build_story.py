"""ARI's content engine: each day of building ARI, told as a story.

The series counts building days: Day 1 is the first day ARI's repository has commits
(April 10, 2026), and each later day with commits is the next day in the series, so it
reads as one continuous "Day N of building ARI". At night, on a day with work (or when
Alec texts "ARI story"), ARI turns that day's commits into lessons about what was worth
building, the day as a short story, and short-form video outlines. `backfill` writes
every day so far.

The lessons come first: ARI's reviews read the latest ones, so the story feeds its
self-improvement before it feeds any post. ARI never posts anything. The facts come
from git, in the commits' own words; only the writing calls a model, and it may use
only those facts. Each day is kept in ARI's content library
(modules/self_documentation/library.py), as a draft until Alec checks it.

    python -m ari_core.build_story backfill --repo PATH [--from-day N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from ari_core.brain import DEEP_MODEL, make_client
from ari_core.brain_usage import ModelCall, month_spend, record_model_call
from ari_core.modules.notes.db import search_ari_notes
from ari_core.modules.self_documentation.library import latest_build_day, store_build_day

CHANNEL = "story"
TITLE_PREFIX = "Build story"
MAX_STORY_TOKENS = 8000
STORY_EFFORT = "low"
LESSONS_HEADING = "What ARI learned"
MAX_COMMITS = 40
BODY_CHARS = 400
# Separators git won't find in a commit message.
FIELD, RECORD = "\x1f", "\x1e"

STORY_PROMPT = """You are ARI, Alec's personal AI operating system. Alec is building you, \
with Claude and Codex, in the open, and posts short-form videos as "Day N of building ARI". \
Write Day {day} from the facts given: that day's commits, each with what changed and why, \
in their own words.

Use only those facts. Never invent a feature, a number, or a result; when the commits are \
thin, keep it short. Plain words, no hype, no emoji, no exclamation points. Write about ARI \
in the third person and Alec by name. A viewer knows nothing about the code: say what ARI \
can do now that it couldn't, or what went wrong, in everyday terms.

Give it with send_story:
- lessons: one to three short, specific lessons for ARI's own self-improvement: what was \
worth building, what broke and why, what to do differently.
- story: the day in 80 to 160 words. The problem that started it, what was built, what it \
changed.
- scripts: one or two short-form video outlines (30 to 60 seconds), each with a hook (one \
line that makes someone stop scrolling, true to the facts), three to five beats, and a \
caption that starts with "Day {day} of building ARI." """

SEND_STORY_TOOL: dict[str, Any] = {
    "name": "send_story",
    "description": "Keep this day's build story.",
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
        """The iMessage: the hook, then the story. Lessons and scripts are in the hub."""
        hook = self.scripts[0]["hook"] if self.scripts else ""
        lead = f"{self.title}\nHook: {hook}" if hook else self.title
        return f"{lead}\n\n{self.story}\n\nLessons and video outlines are in the hub, under Notes."


def story_repo() -> Path | None:
    """ARI's repository, where the days come from (ARI_SOURCE_REPO, set by ari-live)."""
    value = os.environ.get("ARI_SOURCE_REPO")
    return Path(value) if value and Path(value).is_dir() else None


def building_days(repo: Path) -> list[date]:
    """Every day ARI's repository has commits, oldest first: Day 1 is the first."""
    dates = _git(repo, "log", "--all", "--format=%ad", "--date=short").split()
    return sorted({date.fromisoformat(value) for value in dates})


def day_number(repo: Path, day: date) -> int | None:
    days = building_days(repo)
    return days.index(day) + 1 if day in days else None


def gather(repo: Path, day: date) -> dict[str, Any] | None:
    """That day's commits in their own words, or None if nothing was committed."""
    number = day_number(repo, day)
    if number is None:
        return None
    log = _git(repo, "log", "--all", "--reverse", "--date=short", f"--format=%ad{FIELD}%s{FIELD}%b{RECORD}")
    commits, seen = [], set()
    for record in log.split(RECORD):
        parts = record.strip("\n").split(FIELD)
        if len(parts) != 3 or parts[0] != day.isoformat():
            continue
        subject = parts[1].strip()
        if subject in seen:  # the same commit on several branches
            continue
        seen.add(subject)
        commits.append({"what": subject, "why": _without_trailers(parts[2])[:BODY_CHARS]})
    return {"day": number, "date": day.strftime("%A %B %-d, %Y"), "commits": commits[:MAX_COMMITS]}


def write_with_model(facts: dict[str, Any]) -> tuple[dict[str, Any], ModelCall | None]:
    response = make_client().messages.create(
        model=DEEP_MODEL,
        max_tokens=MAX_STORY_TOKENS,
        system=STORY_PROMPT.format(day=facts["day"]),
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
    repo: Path,
    day: date,
    now: datetime | None = None,
    write: Write = write_with_model,
    spine_db_path: Path | None = None,
) -> Story | None:
    """Gather, write, and keep one day's story. None with no commits that day, or no budget."""
    current = now or datetime.now(tz=UTC)
    facts = gather(repo, day)
    if facts is None or not facts["commits"] or month_spend(session, now=current).exhausted:
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
    story = Story(
        title=f"{TITLE_PREFIX}, Day {facts['day']} ({day.strftime('%b %-d')})",
        lessons=[str(lesson).strip() for lesson in written.get("lessons") or [] if str(lesson).strip()],
        story=story_text,
        scripts=[script for script in written.get("scripts") or [] if isinstance(script, dict)],
    )
    kwargs = {} if spine_db_path is None else {"db_path": spine_db_path}
    store_build_day(
        day_number=facts["day"],
        day_date=day.isoformat(),
        title=story.title,
        lessons=story.lessons,
        story=story.story,
        scripts=story.scripts,
        commit_count=len(facts["commits"]),
        **kwargs,
    )
    return story


def latest_lessons(spine_db_path: Path | None = None) -> list[str]:
    """The lessons from the most recent build day, for ARI's reviews to build on."""
    kwargs = {} if spine_db_path is None else {"db_path": spine_db_path}
    day = latest_build_day(**kwargs)
    return list(day.lessons) if day else []


def import_notes(spine_db_path: Path | None = None) -> int:
    """Move build days written as ARI notes (before the library existed) into the library."""
    kwargs = {} if spine_db_path is None else {"db_path": spine_db_path}
    moved = 0
    for row in search_ari_notes(f"{TITLE_PREFIX}, Day", limit=500, **kwargs):
        match = re.match(rf"{TITLE_PREFIX}, Day (\d+) \((.+)\)$", row["title"])
        if match is None:
            continue
        lessons_part, _, rest = row["body"].partition("\n\nThe story\n")
        story, *raw_scripts = re.split(r"\n\nShort-form \d+\n", rest)
        scripts = []
        for raw in raw_scripts:
            lines = raw.splitlines()
            scripts.append({
                "hook": next((line[6:] for line in lines if line.startswith("Hook: ")), ""),
                "beats": [re.sub(r"^\d+\.\s*", "", line) for line in lines if re.match(r"^\d+\.", line)],
                "caption": next((line[9:] for line in lines if line.startswith("Caption: ")), ""),
            })
        store_build_day(
            day_number=int(match.group(1)),
            day_date=_note_date(row["created_at"], match.group(2)),
            title=row["title"],
            lessons=[line[2:].strip() for line in lessons_part.splitlines() if line.startswith("- ")],
            story=story.strip(),
            scripts=scripts,
            commit_count=0,
            **kwargs,
        )
        moved += 1
    return moved


def _note_date(created_at: str, short: str) -> str:
    """The day's ISO date from its title's "Oct 28", in the year the note was written."""
    year = str(created_at)[:4]
    try:
        return datetime.strptime(f"{short} {year}", "%b %d %Y").date().isoformat()
    except ValueError:
        return short


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _without_trailers(body: str) -> str:
    lines = [line for line in body.strip().splitlines() if not line.startswith(("Co-Authored-By:", "Signed-off-by:"))]
    return "\n".join(lines).strip()


def main(argv: list[str] | None = None) -> int:
    from ari_memory import DatabaseSettings, create_engine, create_session_factory

    from ari_core.core.env import load_local_env

    parser = argparse.ArgumentParser(prog="ari_core.build_story")
    commands = parser.add_subparsers(dest="command", required=True)
    backfill = commands.add_parser("backfill", help="Write a story for every building day so far.")
    backfill.add_argument("--repo", type=Path, required=True)
    backfill.add_argument("--from-day", type=int, default=1)
    commands.add_parser("import-notes", help="Move build days kept as ARI notes into the library.")
    args = parser.parse_args(argv)
    load_local_env()
    if args.command == "import-notes":
        print(f"Moved {import_notes()} build day(s) into the content library.")
        return 0
    factory = create_session_factory(create_engine(DatabaseSettings().database_url))
    for number, day in enumerate(building_days(args.repo), start=1):
        if number < args.from_day:
            continue
        with factory() as session:
            story = run_story(session, repo=args.repo, day=day)
        hook = story.scripts[0]["hook"] if story and story.scripts else ""
        print(f"Day {number} ({day}): {story.title + ' | ' + hook if story else 'not written'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
