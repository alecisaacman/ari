from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ari_core.builder import Builder, announcement, start_ship, unannounced
from ari_core.builds import APPROVED, BUILT, DONE, STUCK, decide_build, list_builds, propose_build
from ari_memory import create_engine, create_session_factory
from ari_memory.tables import BuildProposalRow

NOW = datetime(2026, 10, 28, 21, 0, tzinfo=UTC)


class FakeShell:
    """git, claude, and the tests, answered without running anything."""

    def __init__(self, *, claude: dict | None = None, claude_code: int = 0, commits: str = "1", tests: int = 0):
        self.claude_result = claude or {"is_error": False, "result": "Added the thing, with tests."}
        self.claude_code, self.commits, self.tests = claude_code, commits, tests
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, cwd=None, timeout=600):
        argv = list(argv)
        self.calls.append(argv)
        if argv[0].endswith("claude"):
            return subprocess.CompletedProcess(argv, self.claude_code, json.dumps(self.claude_result), "")
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, self.tests, "", "1 failed" if self.tests else "")
        if "rev-list" in argv:
            return subprocess.CompletedProcess(argv, 0, self.commits + "\n", "")
        if "rev-parse" in argv:
            return subprocess.CompletedProcess(argv, 0, "abcdef1234\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")


def _setup(tmp_path: Path, shell: FakeShell):
    factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    builder = Builder(source=tmp_path / "repo", builds_dir=tmp_path / "builds", state_path=tmp_path / "builder.json",
                      run=shell, claude="claude", live_script=tmp_path / "ari-live")
    with factory() as session:
        build, _ = propose_build(session, title="Email digest", why="He asked.", brief="Summarize email.", now=NOW)
        decide_build(session, build.id, "approve", now=NOW)
    return factory, builder, build.id


def test_approved_build_is_built_on_its_own_branch_and_announced_once(tmp_path: Path) -> None:
    shell = FakeShell()
    factory, builder, build_id = _setup(tmp_path, shell)
    with factory() as session:
        assert builder.run_once(session, now=NOW).startswith("built")
        row = session.get(BuildProposalRow, build_id)
        assert row.status == BUILT and row.branch == f"ari/build-{str(build_id)[:8]}"
        claude = next(call for call in shell.calls if call[0] == "claude")
        assert "Summarize email." in claude[2] and "Never push" in claude[2]
        assert "Bash(git push:*)" not in claude and "Bash(uv run:*)" in claude
        assert any(call[:1] == ["uv"] for call in shell.calls)  # ARI checks the tests itself

        [pending] = unannounced(session)
        assert "ship it" in announcement(pending)
        pending.announced_status = pending.status
        session.commit()
        assert unannounced(session) == []

        # The next approved build waits until the pace allows another.
        later, _ = propose_build(session, title="Second", why="", brief="", now=NOW)
        decide_build(session, later.id, "approve", now=NOW)
        assert builder.run_once(session, now=NOW + timedelta(hours=1)) == "waiting: built recently"
        assert builder.run_once(session, now=NOW + timedelta(hours=6)).startswith("built")


def test_out_of_credits_puts_the_build_back_to_wait_for_them(tmp_path: Path) -> None:
    shell = FakeShell(claude={"is_error": True, "result": "Claude usage limit reached. Resets at 9pm."}, claude_code=1)
    factory, builder, build_id = _setup(tmp_path, shell)
    with factory() as session:
        assert builder.run_once(session, now=NOW) == "waiting: out of credits"
        row = session.get(BuildProposalRow, build_id)
        assert row.status == APPROVED and "credits" in row.result
        assert unannounced(session) == []
        shell.claude_code, shell.claude_result = 0, {"is_error": False, "result": "Done."}
        assert builder.run_once(session, now=NOW + timedelta(hours=1)).startswith("built")


def test_failing_tests_or_no_commits_leave_the_build_stuck_with_the_reason(tmp_path: Path) -> None:
    for shell, reason in ((FakeShell(tests=1), "tests fail"), (FakeShell(commits="0"), "no commits")):
        factory, builder, build_id = _setup(tmp_path / reason.replace(" ", "-"), shell)
        with factory() as session:
            assert builder.run_once(session, now=NOW).startswith("stuck")
            row = session.get(BuildProposalRow, build_id)
            assert row.status == STUCK and reason in row.result.lower()
            assert "couldn't finish" in announcement(row)


def test_ship_only_starts_for_a_built_build_then_pushes_and_installs(tmp_path: Path) -> None:
    shell = FakeShell()
    factory, builder, build_id = _setup(tmp_path, shell)
    spawned: list[list[str]] = []
    with factory() as session:
        assert "not built" in start_ship(session, build_id, spawn=spawned.append)["error"]
        builder.run_once(session, now=NOW)
        assert start_ship(session, build_id, spawn=spawned.append)["shipping"]["title"] == "Email digest"
        assert spawned[0][-2:] == ["ship", str(build_id)]

        assert builder.ship(session, build_id, now=NOW).startswith("shipped")
        assert ["git", "-C", str(tmp_path / "builds" / f"build-{str(build_id)[:8]}"), "push", "--quiet", "origin", "HEAD:main"] in shell.calls
        assert any("install" in call for call in shell.calls)
        assert session.get(BuildProposalRow, build_id).status == DONE
        assert list_builds(session) == []


def test_a_session_here_claims_builds_finishes_and_can_give_one_back(tmp_path: Path) -> None:
    from uuid import UUID

    shell = FakeShell()
    factory, builder, build_id = _setup(tmp_path, shell)
    with factory() as session:
        claimed = builder.claim(session, now=NOW)
        assert claimed["id"] == str(build_id) and "Summarize email." in claimed["instructions"]
        assert claimed["worktree"].endswith(f"build-{str(build_id)[:8]}")
        assert builder.claim(session, now=NOW) == "nothing approved"  # it's being built

        assert builder.give_back(session, build_id, reason="Out of credits") .startswith("back on the list")
        assert session.get(BuildProposalRow, build_id).status == APPROVED

        claimed = builder.claim(session, now=NOW)
        assert builder.finish(session, UUID(claimed["id"]), summary="Added the digest.", now=NOW).startswith("built")
        row = session.get(BuildProposalRow, build_id)
        assert row.status == BUILT and row.result == "Added the digest."


def test_a_build_left_building_by_a_session_that_died_is_tried_again(tmp_path: Path) -> None:
    factory, builder, build_id = _setup(tmp_path, FakeShell())
    with factory() as session:
        builder.claim(session, now=NOW)
        assert builder.claim(session, now=NOW + timedelta(hours=1)) == "nothing approved"
        assert builder.claim(session, now=NOW + timedelta(hours=4))["id"] == str(build_id)
