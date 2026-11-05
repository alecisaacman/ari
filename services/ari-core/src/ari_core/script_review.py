"""ARI reviews a building day's script before it can be approved: pass, or notes to fix.

Alec writes or rewrites scripts himself; ARI checks them the way an editor would. Two
kinds of check, and a script passes only if both do:

- Rules, checked here without a model: a hook short enough to read at a glance, three to
  six beats, a spoken length of roughly 20 to 75 seconds, and a caption that opens
  "Day N of building ARI."
- An editor's read, by ARI's deeper model, against that day's commits: is every claim
  true to what was built (and not something Alec "did" that the commits only made
  possible), does the hook earn attention without overstating, does it flow from the
  problem to the build to what changed, and would someone who doesn't code follow it.

The review is kept on the item, tied to the exact scripts it read (library.record_review),
so editing a script again needs a new review before approval.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from ari_core.brain import DEEP_MODEL, make_client
from ari_core.brain_usage import ModelCall, month_spend, record_model_call
from ari_core.build_story import gather, story_repo
from ari_core.core.paths import DB_PATH
from ari_core.modules.self_documentation.library import ContentItem, get_content_item, record_review

CHANNEL = "script_review"
# Narration runs near 150 words a minute.
WORDS_PER_SECOND = 2.5
SECONDS = (20, 75)
BEATS = (3, 6)
HOOK_WORDS = 16
MAX_REVIEW_TOKENS = 6000

REVIEW_PROMPT = """You are ARI's editor, reviewing a script for "Day {day} of building ARI", a \
short-form video Alec posts about building his AI, ARI. You get that day's commits (what \
changed and why, in their own words) and the script: a hook, beats, and a caption.

Judge it honestly, like a good editor who wants it to do well:
- Truth: every claim must be supported by the commits. Commits say what ARI became able \
to do; flag any line that says Alec did something, or that something happened, that the \
commits only made possible. Flag invented numbers.
- Hook: would it stop someone scrolling, and is it true? A hook that overstates fails.
- Flow: hook, then the problem, then what was built, then what changed or what was learned, \
then a reason to come back. Point out a beat that's out of order or doesn't earn its place.
- Plain words: someone who doesn't code should follow it.

Pass it only if there are no truth problems and it would hold attention. Give at most \
five notes, each one specific and fixable, in plain words. Give it with send_review."""

SEND_REVIEW_TOOL: dict[str, Any] = {
    "name": "send_review",
    "description": "Send the review of the script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "truth_problems": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
            "hook_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "flow_score": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["passed", "truth_problems", "notes", "hook_score", "flow_score"],
    },
}

Write = Callable[[dict[str, Any]], tuple[dict[str, Any], ModelCall | None]]


def rule_checks(item: ContentItem) -> list[str]:
    """What the scripts break of the rules, in plain words; empty when they keep them all."""
    problems = []
    for number, script in enumerate(item.scripts, start=1):
        label = f"Script {number}" if len(item.scripts) > 1 else "The script"
        hook = str(script.get("hook") or "")
        beats = [str(beat) for beat in script.get("beats") or []]
        words = len(hook.split()) + sum(len(beat.split()) for beat in beats) + 9  # plus the sign-off
        seconds = words / WORDS_PER_SECOND
        if len(hook.split()) > HOOK_WORDS:
            problems.append(f"{label}: the hook is {len(hook.split())} words; keep it to {HOOK_WORDS} or fewer.")
        if not BEATS[0] <= len(beats) <= BEATS[1]:
            problems.append(f"{label}: it has {len(beats)} beats; use {BEATS[0]} to {BEATS[1]}.")
        if not SECONDS[0] <= seconds <= SECONDS[1]:
            problems.append(f"{label}: it runs about {seconds:.0f} seconds spoken; aim for {SECONDS[0]} to {SECONDS[1]}.")
        caption = str(script.get("caption") or "")
        if not re.match(rf"^Day {item.day_number} of building ARI\b", caption):
            problems.append(f'{label}: the caption should start "Day {item.day_number} of building ARI."')
    return problems


def write_with_model(facts: dict[str, Any]) -> tuple[dict[str, Any], ModelCall | None]:
    response = make_client().messages.create(
        model=DEEP_MODEL,
        max_tokens=MAX_REVIEW_TOKENS,
        system=REVIEW_PROMPT.format(day=facts["day"]),
        messages=[{"role": "user", "content": json.dumps(facts, default=str)}],
        tools=[SEND_REVIEW_TOOL],
        tool_choice={"type": "auto"},
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
    )
    for block in response.content:
        if getattr(block, "type", "") == "tool_use" and isinstance(getattr(block, "input", None), dict):
            return dict(block.input), ModelCall.from_response(response)
    return {}, ModelCall.from_response(response)


def review(
    session: Session,
    item_id: str,
    *,
    repo: Path | None = None,
    write: Write = write_with_model,
    db_path: Path = DB_PATH,
    now: datetime | None = None,
) -> ContentItem:
    """Review an item's scripts, keep the verdict on it, and return the item."""
    item = get_content_item(item_id, db_path=db_path)
    if item is None:
        raise ValueError("There's no such content item.")
    if not item.scripts:
        raise ValueError(f"{item.title} has no script to review.")
    rules = rule_checks(item)
    commits = _commits(item, repo or story_repo())
    if month_spend(session, now=now or datetime.now(tz=UTC)).exhausted:
        raise ValueError("This month's model budget is used up, so ARI can't review scripts right now.")
    try:
        written, call = write({"day": item.day_number, "commits": commits, "scripts": list(item.scripts)})
    except anthropic.APIError as error:
        raise ValueError(f"ARI's editor didn't answer ({type(error).__name__}). Try again in a moment.") from error
    if call is not None:
        record_model_call(session, call, channel=CHANNEL, escalated=True)
    if "passed" not in written:
        raise ValueError("ARI's editor didn't return a review. Try again.")
    truth = [str(problem) for problem in written.get("truth_problems") or []]
    verdict = {
        "passed": bool(written["passed"]) and not truth and not rules,
        "truth": truth,
        "rules": rules,
        "notes": [str(note) for note in written.get("notes") or []][:5],
        "hookScore": written.get("hook_score"),
        "flowScore": written.get("flow_score"),
    }
    stored = record_review(item_id, verdict, db_path=db_path)
    assert stored is not None
    return stored


def _commits(item: ContentItem, repo: Path | None) -> list[dict[str, str]]:
    if repo is None or not item.day_date:
        return []
    try:
        facts = gather(repo, date.fromisoformat(item.day_date))
    except ValueError:
        return []
    return facts["commits"] if facts else []
