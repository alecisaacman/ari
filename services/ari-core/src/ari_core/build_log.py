"""ARI's self-documentation: a log of every release that went live.

`ari-live install` records each release here once it is live, with the commits it
shipped since the release before it, in their own words (what changed and why). Reviews
read the log next to how often ARI's tools were actually used, so ARI can judge what
was worth building and what to build next. The same entries are the raw material for
telling the story of building ARI.

    python -m ari_core.build_log record --release NAME --repo PATH --to SHA [--since SHA]
"""

from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ari_memory.tables import BuildLogRow, SkillInvocationRow
from sqlalchemy import select
from sqlalchemy.orm import Session

# Separators git won't find in a commit message.
FIELD, RECORD = "\x1f", "\x1e"
MAX_COMMITS = 50
MAX_FILES = 200


def commits_between(repo: Path, since: str | None, to: str) -> tuple[list[dict[str, str]], list[str]]:
    """The commits after `since` up to `to`, oldest first, and the files they touched.

    The first release logged has nothing before it, so it records only its own commit.
    """
    span = f"{since}..{to}" if since else f"{to}^!"
    log = _git(repo, "log", "--reverse", f"--format=%H{FIELD}%s{FIELD}%b{RECORD}", span)
    commits = []
    for record in log.split(RECORD):
        parts = record.strip("\n").split(FIELD)
        if len(parts) == 3:
            sha, subject, body = parts
            commits.append({"sha": sha[:7], "subject": subject.strip(), "body": _without_trailers(body)})
    changed = (
        _git(repo, "diff", "--name-only", f"{since}..{to}")
        if since
        else _git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", to)
    )
    files = [line for line in changed.splitlines() if line]
    return commits[-MAX_COMMITS:], files[:MAX_FILES]


def record_release(
    session: Session,
    *,
    release: str,
    commit: str,
    commits: list[dict[str, str]],
    files: list[str],
    shipped_at: datetime,
) -> BuildLogRow | None:
    """Log a release once; a reinstall of the same release name is ignored."""
    if session.scalar(select(BuildLogRow).where(BuildLogRow.release == release)) is not None:
        return None
    row = BuildLogRow(id=uuid4(), release=release, commit=commit, shipped_at=shipped_at, commits=commits, files=files)
    session.add(row)
    session.commit()
    return row


def recent_builds(session: Session, *, since: datetime) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(BuildLogRow).where(BuildLogRow.shipped_at >= since).order_by(BuildLogRow.shipped_at)
    ).all()
    return [describe(row) for row in rows]


def describe(row: BuildLogRow) -> dict[str, Any]:
    shipped = row.shipped_at if row.shipped_at.tzinfo else row.shipped_at.replace(tzinfo=UTC)
    return {
        "release": row.release,
        "shipped": shipped.astimezone().strftime("%a %b %-d, %-I:%M %p"),
        "changes": [
            {"what": commit["subject"], "why": commit["body"][:600]} for commit in row.commits
        ],
        "files_changed": len(row.files),
    }


def tool_use(session: Session, *, since: datetime) -> dict[str, int]:
    """How often each of ARI's tools was used, most used first: what's actually useful."""
    names = session.scalars(select(SkillInvocationRow.tool_name).where(SkillInvocationRow.occurred_at >= since)).all()
    return dict(Counter(names).most_common())


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _without_trailers(body: str) -> str:
    lines = [line for line in body.strip().splitlines() if not line.startswith(("Co-Authored-By:", "Signed-off-by:"))]
    return "\n".join(lines).strip()


def main(argv: list[str] | None = None) -> int:
    from ari_memory import DatabaseSettings, create_engine, create_session_factory

    from .core.env import load_local_env

    parser = argparse.ArgumentParser(prog="ari_core.build_log")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--release", required=True)
    record.add_argument("--repo", type=Path, required=True)
    record.add_argument("--to", required=True)
    record.add_argument("--since")
    args = parser.parse_args(argv)
    load_local_env()
    commits, files = commits_between(args.repo, args.since, args.to)
    factory = create_session_factory(create_engine(DatabaseSettings().database_url))
    with factory() as session:
        row = record_release(
            session, release=args.release, commit=args.to, commits=commits, files=files, shipped_at=datetime.now(tz=UTC)
        )
    print(f"Build log: {len(commits)} change(s) recorded." if row else "Build log: already recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

