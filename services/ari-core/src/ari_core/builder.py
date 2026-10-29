"""ARI builds what Alec approved, on its own schedule, and ships it when he says so.

A build Alec approves ("yes" to a review's proposal) waits on the build list. Once an
hour launchd runs `python -m ari_core.builder run`. When the last build finished long
enough ago (ARI_BUILD_EVERY_HOURS, 5 by default) it takes the oldest approved build:

1. A fresh git worktree on a new branch, from GitHub's main, under ~/ARI/builds.
2. Claude Code, unattended, with the build's brief. It may read and edit files in that
   worktree, run the tests, and commit there. It can't push or reach anything else.
3. ARI runs the tests itself. The build is `built` only if there are new commits and
   the tests pass; otherwise it is `stuck`, with the reason.

Out of Claude credits, the build goes back to `approved` and the next hourly run tries
again, so it starts once the credits refresh. The poller texts Alec each result once.

Nothing goes live until Alec says "ship it". Then `python -m ari_core.builder ship ID`
brings the branch up to date with main, tests it again, pushes it to main, and installs
it as the live release, so it lands in ARI's build log like any other release.

Off unless ARI_AUTOBUILD=1 (set by `ari-live connect-builds`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from ari_memory.tables import BuildProposalRow
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ari_core.builds import APPROVED, BUILDING, BUILT, DONE, SHIPPING, STUCK
from ari_core.core.env import ari_home

CLAUDE_TIMEOUT_SECONDS = 2 * 60 * 60
TEST_TIMEOUT_SECONDS = 20 * 60
DEFAULT_EVERY_HOURS = 5.0
RESULT_CHARS = 700
TEST_COMMAND = ("uv", "run", "--quiet", "--extra", "dev", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x")
# Claude may read and edit inside the worktree, run the tests, and commit. Nothing else:
# in print mode a tool that isn't listed is refused, not asked about.
ALLOWED_TOOLS = (
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(uv run:*)", "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(ls:*)",
)
OUT_OF_CREDITS = re.compile(r"usage limit|hit your limit|limit reached|rate.?limit|out of (extra )?usage|credit", re.I)

BRIEF = """You are building one improvement to ARI that Alec approved, unattended, in this git \
worktree on branch {branch}. Nobody will answer questions while you work.

Build: {title}
Why: {why}
Brief: {brief}

How to work:
- Read the README, the docs, and the code you'll touch first. Match the code around it: \
its naming, comment density, and how it handles errors.
- Add or update tests. Run `uv run --quiet --extra dev python -m pytest -q -p no:cacheprovider -x` \
until everything passes.
- Commit on this branch. The commit message's first line says what changed; its body \
says why, in plain words (it becomes ARI's build log). End it with the line \
"Co-Authored-By: Claude <noreply@anthropic.com>".
- Never push, and never touch anything outside this folder (not ~/ARI, not other repos).
- This repository is public: never add personal information (names, numbers, \
addresses, emails, photos).
- If the brief is unclear or too big for one session, build the smallest useful piece \
and say what's left.

Finish with two or three plain sentences for Alec: what you built, and anything left."""


class BuildError(RuntimeError):
    """A step of building or shipping failed; the message says which, plainly."""


Run = Callable[..., subprocess.CompletedProcess[str]]


def _run(argv: Sequence[str], *, cwd: Path | None = None, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


@dataclass(slots=True)
class Builder:
    """Everything the builder touches outside the database, so tests can replace it."""

    source: Path
    builds_dir: Path
    state_path: Path
    run: Run = _run
    claude: str = "claude"
    every: timedelta = timedelta(hours=DEFAULT_EVERY_HOURS)
    live_script: Path = Path("scripts/ari-live")

    @classmethod
    def connected(cls) -> Builder | None:
        if os.environ.get("ARI_AUTOBUILD") != "1":
            return None
        source = os.environ.get("ARI_SOURCE_REPO")
        if not source:
            return None
        hours = float(os.environ.get("ARI_BUILD_EVERY_HOURS") or DEFAULT_EVERY_HOURS)
        return cls(
            source=Path(source),
            builds_dir=ari_home() / "builds",
            state_path=ari_home() / "state" / "builder.json",
            claude=os.environ.get("ARI_CLAUDE") or str(Path.home() / ".local" / "bin" / "claude"),
            every=timedelta(hours=hours),
            live_script=ari_home() / "runtime" / "current" / "scripts" / "ari-live",
        )

    def run_once(self, session: Session, *, now: datetime) -> str:
        """Build the oldest approved build, if it's time. Returns what happened, for the log."""
        state = self._state()
        last = state.get("last_built_at")
        if last and now - datetime.fromisoformat(last) < self.every:
            return "waiting: built recently"
        row = session.scalars(
            select(BuildProposalRow).where(BuildProposalRow.status == APPROVED).order_by(BuildProposalRow.decided_at)
        ).first()
        if row is None:
            return "nothing approved"
        branch = f"ari/build-{str(row.id)[:8]}"
        row.status, row.branch, row.result = BUILDING, branch, None
        session.commit()
        try:
            worktree = self._worktree(branch)
            summary = self._claude(worktree, row, branch)
            if self._git(worktree, "rev-list", "--count", "origin/main..HEAD").strip() == "0":
                raise BuildError(f"Claude made no commits. It said: {summary}")
            self._tests(worktree)
        except OutOfCredits as error:
            row.status, row.result = APPROVED, f"Waiting for Claude credits: {error}"[:RESULT_CHARS]
            session.commit()
            return "waiting: out of credits"
        except (BuildError, subprocess.TimeoutExpired) as error:
            row.status, row.result, row.built_at = STUCK, str(error)[:RESULT_CHARS], now
            session.commit()
            self._save_state(last_built_at=now.isoformat())
            return f"stuck: {row.title}"
        row.status, row.result, row.built_at = BUILT, summary[:RESULT_CHARS], now
        session.commit()
        self._save_state(last_built_at=now.isoformat())
        return f"built: {row.title} on {branch}"

    def ship(self, session: Session, build_id: UUID, *, now: datetime) -> str:
        """Bring the branch up to date with main, test it, push it to main, and install it."""
        row = session.get(BuildProposalRow, build_id)
        if row is None or row.branch is None:
            return "no such build"
        worktree = self.builds_dir / row.branch.removeprefix("ari/")
        try:
            self._git(self.source, "fetch", "--quiet", "origin", "main")
            self._git(worktree, "rebase", "--quiet", "origin/main")
            self._tests(worktree)
            sha = self._git(worktree, "rev-parse", "HEAD").strip()
            self._git(worktree, "push", "--quiet", "origin", "HEAD:main")
            installed = self.run(
                [sys.executable, str(self.live_script), "install", "--repo", str(self.source), "--commit", sha],
                cwd=self.source, timeout=TEST_TIMEOUT_SECONDS * 2,
            )
            if installed.returncode != 0:
                raise BuildError(f"It's on GitHub, but the release didn't install: {_tail(installed)}")
        except (BuildError, subprocess.TimeoutExpired) as error:
            self.run(["git", "rebase", "--abort"], cwd=worktree)
            row.status, row.result = STUCK, f"Shipping failed: {error}"[:RESULT_CHARS]
            session.commit()
            return f"stuck: {row.title}"
        row.status, row.result = DONE, f"Shipped as {sha[:7]} and live."
        session.commit()
        self.run(["git", "-C", str(self.source), "worktree", "remove", "--force", str(worktree)])
        return f"shipped: {row.title}"

    def _worktree(self, branch: str) -> Path:
        path = self.builds_dir / branch.removeprefix("ari/")
        self._git(self.source, "fetch", "--quiet", "origin", "main")
        if path.exists():
            self.run(["git", "-C", str(self.source), "worktree", "remove", "--force", str(path)])
        self.run(["git", "-C", str(self.source), "branch", "-D", branch])
        self.builds_dir.mkdir(parents=True, exist_ok=True)
        self._git(self.source, "worktree", "add", "--quiet", "-b", branch, str(path), "origin/main")
        return path

    def _claude(self, worktree: Path, row: BuildProposalRow, branch: str) -> str:
        prompt = BRIEF.format(branch=branch, title=row.title, why=row.why or "-", brief=row.brief or row.title)
        completed = self.run(
            [self.claude, "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
             "--allowedTools", *ALLOWED_TOOLS],
            cwd=worktree, timeout=CLAUDE_TIMEOUT_SECONDS,
        )
        try:
            result: dict[str, Any] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result = {"is_error": True, "result": _tail(completed)}
        text = str(result.get("result") or "").strip()
        if completed.returncode != 0 or result.get("is_error"):
            if OUT_OF_CREDITS.search(text):
                raise OutOfCredits(text[:200])
            raise BuildError(f"Claude stopped: {text[:400] or 'no message'}")
        return text or "Built, with no summary."

    def _tests(self, worktree: Path) -> None:
        completed = self.run(list(TEST_COMMAND), cwd=worktree, timeout=TEST_TIMEOUT_SECONDS)
        if completed.returncode != 0:
            raise BuildError(f"The tests fail: {_tail(completed)}")

    def _git(self, repo: Path, *args: str) -> str:
        completed = self.run(["git", "-C", str(repo), *args])
        if completed.returncode != 0:
            raise BuildError(f"git {args[0]} failed: {_tail(completed)}")
        return completed.stdout

    def _state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save_state(self, **values: Any) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({**self._state(), **values}))


class OutOfCredits(BuildError):
    """Claude is out of credits for now; the build waits for them to refresh."""


def start_ship(session: Session, build_id: UUID, *, spawn: Callable[[list[str]], Any] | None = None) -> dict[str, Any]:
    """Mark a built build as shipping and start shipping it in the background."""
    row = session.get(BuildProposalRow, build_id)
    if row is None:
        return {"error": "There's no build with that id."}
    if row.status != BUILT:
        return {"error": f"That build is {row.status}, not built, so there's nothing to ship."}
    row.status = SHIPPING
    session.commit()
    command = [sys.executable, "-m", "ari_core.builder", "ship", str(build_id)]
    (spawn or _spawn_detached)(command)
    return {"shipping": {"id": str(build_id), "title": row.title, "branch": row.branch}}


def unannounced(session: Session) -> list[BuildProposalRow]:
    """Builder results Alec hasn't been told about yet."""
    rows = session.scalars(
        select(BuildProposalRow).where(BuildProposalRow.status.in_((BUILT, STUCK, DONE)))
    ).all()
    return [row for row in rows if row.announced_status != row.status and row.branch]


def announcement(row: BuildProposalRow) -> str:
    if row.status == BUILT:
        return (f"I built “{row.title}” on branch {row.branch}. {row.result} "
                "The tests pass. Say “ship it” to put it live, or “hold”.")
    if row.status == DONE:
        return f"“{row.title}” is live. {row.result}"
    return f"I couldn't finish “{row.title}”. {row.result}"


def _spawn_detached(command: list[str]) -> None:
    log = ari_home() / "runtime" / "logs" / "builder.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as out:
        subprocess.Popen(command, stdout=out, stderr=out, start_new_session=True)


def _tail(completed: subprocess.CompletedProcess[str]) -> str:
    return " ".join((completed.stderr or completed.stdout or "").strip().splitlines()[-3:])[:300]


def _session_factory() -> sessionmaker[Session]:
    from ari_memory import DatabaseSettings, create_engine, create_session_factory

    return create_session_factory(create_engine(DatabaseSettings().database_url))


def main(argv: list[str] | None = None) -> int:
    from ari_core.core.env import load_local_env

    parser = argparse.ArgumentParser(prog="ari_core.builder")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    ship = commands.add_parser("ship")
    ship.add_argument("build_id", type=UUID)
    args = parser.parse_args(argv)
    load_local_env()
    builder = Builder.connected()
    if builder is None:
        print("ARI's builder is off (ari-live connect-builds turns it on).")
        return 0
    now = datetime.now(tz=UTC)
    with _session_factory()() as session:
        outcome = builder.run_once(session, now=now) if args.command == "run" else builder.ship(session, args.build_id, now=now)
    print(f"{now.isoformat()} {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
