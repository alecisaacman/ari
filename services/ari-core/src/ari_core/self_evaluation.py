"""ARI evaluates itself each night, on Alec's Claude plan, and proposes the next build.

The nightly "ARI builds" session in the Claude app builds an approved build when there
is one. When there isn't, it evaluates ARI instead: `evidence` prints what ARI's records
show (tool use and errors, what Alec asked for, what shipped and whether it's used, what
the watchdog has open, what ARI spends), the session reads the code it needs to judge,
and `propose` puts the one build that would help Alec most on the build list. ARI texts
him the proposal in the morning; "yes" approves it and the next night builds it.

This replaces proposing from the morning and night reviews, which are short, about his
day, and written through the API: in practice they proposed nothing. Nothing here calls
a model; the thinking happens in the Claude session, on the plan, not on API credits.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ari_memory.tables import BrainUsageRow, BuildProposalRow, SkillInvocationRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_core.build_log import recent_builds, tool_use
from ari_core.build_story import latest_lessons
from ari_core.builds import PROPOSED, list_builds, propose_build
from ari_core.core.env import ari_home
from ari_core.modules.skills.catalog import list_skill_manifests
from ari_core.panel import recent_exchange

SOURCE = "ari.self-evaluation"
# How far back the evidence reaches: long enough to see whether a release got used.
LOOKBACK = timedelta(days=14)
MAX_ERRORS = 25
MAX_EXCHANGE = 40
# ARI's running account of itself, kept by the nightly session: what each part does, how
# well it works, what's been tried and learned. Local, not in the public repo.
SELF_KNOWLEDGE = "self-knowledge.md"


def evidence(session: Session, *, now: datetime, home: Path | None = None) -> dict[str, Any]:
    """What ARI's records show about how well ARI is working. Read only; no model."""
    root = home or ari_home()
    since = now - LOOKBACK
    errors = session.scalars(
        select(SkillInvocationRow)
        .where(SkillInvocationRow.occurred_at >= since, SkillInvocationRow.is_error.is_(True))
        .order_by(SkillInvocationRow.occurred_at)
    ).all()
    spend = evidence_spend(session, now=now)
    path = root / "imessage" / "watchdog.json"
    knowledge = root / "state" / SELF_KNOWLEDGE
    try:
        known = knowledge.read_text()
    except OSError:
        known = ""
    try:
        watchdog = json.loads(path.read_text()).get("open") or {}
    except (OSError, ValueError):
        watchdog = {}
    return {
        "now": now.astimezone().strftime("%A %B %-d, %-I:%M %p"),
        "health": audit(session, now=now, home=root),
        "what_ari_knows_about_itself": known or f"Nothing yet: write it to ~/ARI/state/{SELF_KNOWLEDGE}.",
        "build_list": [build.describe() for build in list_builds(session)],
        "shipped_last_two_weeks": recent_builds(session, since=since),
        "tool_use_last_week": tool_use(session, since=now - timedelta(days=7)),
        "tool_use_last_two_weeks": tool_use(session, since=since),
        "tool_errors": [f"{row.tool_name}: {row.summary[:200]}" for row in errors][-MAX_ERRORS:],
        "what_alec_said_recently": [
            line
            for channel in ("imessage", "hub")
            for line in recent_exchange(session, channel=channel, limit=MAX_EXCHANGE)
        ],
        "watchdog_open": {key: entry.get("text") for key, entry in watchdog.items()},
        "api_spend_this_month_usd": spend,
        "lessons_from_last_build_story": latest_lessons(),
        "skills_not_built": [
            {"skill_id": manifest.skill_id, "name": manifest.name, "purpose": manifest.purpose}
            for manifest in list_skill_manifests()
            if manifest.lifecycle_status == "candidate"
        ],
    }


def audit(session: Session, *, now: datetime, home: Path | None = None) -> list[dict[str, Any]]:
    """Is every part of ARI working? One line per part, from the markers each part leaves. No model.

    A part that has gone quiet is a problem even when nothing logged an error: that is how
    the reviews stopped for four days without anyone noticing.
    """
    root = home or ari_home()
    local = now.astimezone()
    today, yesterday = local.date().isoformat(), (local.date() - timedelta(days=1)).isoformat()

    def marker(path: str) -> str | None:
        try:
            return (root / path).read_text().strip() or None
        except OSError:
            return None

    checks: list[dict[str, Any]] = []

    def check(part: str, ok: bool, detail: str) -> None:
        checks.append({"part": part, "ok": ok, "detail": detail})

    last_run = marker("imessage/last-run")
    try:
        quiet_for = now - datetime.fromisoformat(last_run) if last_run else None
    except ValueError:
        quiet_for = None
    check("iMessage poller", quiet_for is not None and quiet_for < timedelta(minutes=10),
          f"last ran {last_run or 'never'}")
    for kind in ("morning", "night"):
        sent = marker(f"imessage/last-review-{kind}")
        check(f"{kind} review", sent in (today, yesterday), f"last went out {sent or 'never'}")
    credits = marker("imessage/last-credits-notice")
    check("API credits", credits not in (today, yesterday),
          "refused for lack of credits" + (f" on {credits}" if credits else "") if credits in (today, yesterday)
          else "no refusals in the last day")
    spend = evidence_spend(session, now=now)
    check("API spend", sum(spend.values()) < float(os.environ.get("ARI_BRAIN_MONTHLY_BUDGET_USD") or 10) * 0.8,
          f"this month ${sum(spend.values()):.2f}: " + ", ".join(f"{k} ${v:.2f}" for k, v in spend.items()))
    try:
        release = json.loads((root / "runtime" / "current" / "RELEASE.json").read_text())
        check("live release", release.get("tests") == "passed",
              f"{str(release.get('commit'))[:7]} “{release.get('subject')}”, tests {release.get('tests')}")
    except (OSError, ValueError):
        check("live release", False, "no RELEASE.json for the live release")
    approved = [build for build in list_builds(session) if build.status == "approved"]
    check("builder", not any(now - _utc(build.created_at) > timedelta(days=2) for build in approved),
          f"{len(approved)} approved and waiting")
    try:
        open_problems = json.loads((root / "imessage" / "watchdog.json").read_text()).get("open") or {}
    except (OSError, ValueError):
        open_problems = {}
    check("watchdog", not open_problems, f"{len(open_problems)} open problem(s)")
    return checks


def evidence_spend(session: Session, *, now: datetime) -> dict[str, float]:
    """API spend this month by channel, in dollars."""
    spend: dict[str, float] = {}
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for usage in session.scalars(select(BrainUsageRow).where(BrainUsageRow.occurred_at >= month_start)):
        spend[usage.channel] = round(spend.get(usage.channel, 0.0) + usage.cost_microusd / 1e6, 4)
    return spend


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def propose(session: Session, *, title: str, why: str, brief: str, now: datetime) -> str:
    """Put tonight's proposal on the build list, unless one is still waiting on Alec.

    One open proposal at a time: a list of unanswered proposals is noise, and the oldest
    one already says what ARI most wants.
    """
    waiting = list_builds(session, statuses=(PROPOSED,))
    if waiting:
        return f"not proposed: “{waiting[0].title}” is still waiting for Alec to answer"
    build, is_new = propose_build(session, title=title, why=why, brief=brief, now=now, source=SOURCE)
    if not is_new:
        return f"not proposed: “{build.title}” is already on the list ({build.status})"
    return f"proposed: {build.title}"


def unannounced(session: Session) -> list[BuildProposalRow]:
    """Proposals from a nightly evaluation that Alec hasn't been told about yet."""
    rows = session.scalars(
        select(BuildProposalRow).where(BuildProposalRow.status == PROPOSED, BuildProposalRow.source == SOURCE)
    ).all()
    return [row for row in rows if row.announced_status != PROPOSED]


def announcement(row: BuildProposalRow) -> str:
    return (f"Last night I reviewed how I'm working. The build I'd do next: “{row.title}”. {row.why} "
            "Say “yes” and I'll build it tonight, or “hold”.")


def main(argv: list[str] | None = None) -> int:
    from ari_core.builder import _session_factory
    from ari_core.core.env import load_local_env

    parser = argparse.ArgumentParser(prog="ari_core.self_evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("evidence", help="Print what ARI's records show, as JSON.")
    proposal = commands.add_parser("propose", help="Put one build on the list for Alec to answer.")
    proposal.add_argument("--title", required=True)
    proposal.add_argument("--why", required=True)
    proposal.add_argument("--brief", required=True)
    args = parser.parse_args(argv)
    load_local_env()
    now = datetime.now(tz=UTC)
    with _session_factory()() as session:
        if args.command == "evidence":
            print(json.dumps(evidence(session, now=now), indent=2, default=str))
        else:
            print(propose(session, title=args.title, why=args.why, brief=args.brief, now=now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
