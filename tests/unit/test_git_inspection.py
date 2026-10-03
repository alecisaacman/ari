from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from ari_core.core import git_inspection
from ari_core.core.git_inspection import git_inspection_environment, run_git_inspection
from ari_core.modules.execution.controller import build_repo_context
from ari_core.modules.self_documentation.content_seed import generate_content_seed_from_commits
from ari_core.runtime.repo_inspector import inspect_repo_state

SECRET = "sk-ari-ambient-secret-0123456789"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=30
    ).stdout


def _hostile_program(directory: Path, name: str, log: Path, body: str) -> str:
    """A program that records that it ran and whether it could see the secret."""
    program = directory / name
    program.write_text(
        f'#!/bin/sh\necho "{name} secret=${{ARI_TEST_SECRET:-absent}}" >> "{log}"\n{body}\n',
        encoding="utf-8",
    )
    program.chmod(0o755)
    return str(program)


@pytest.fixture
def hostile_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A repository whose own config tries to run programs during inspection."""
    repo = tmp_path / "repo"
    tools = tmp_path / "tools"
    hooks = tmp_path / "hooks"
    log = tmp_path / "hostile.log"
    for directory in (repo, tools, hooks):
        directory.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "ari@test.invalid")
    _git(repo, "config", "user.name", "ARI Test")
    (repo / ".gitattributes").write_text("tracked.txt filter=evil=drv diff=evil=drv\n")
    (repo / "tracked.txt").write_text("first\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "first commit")
    (repo / "tracked.txt").write_text("first\nsecond\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "second commit")
    (repo / ".git" / "info" / "attributes").write_text("tracked.txt filter=info diff=info\n")

    hostile_config = {
        "core.fsmonitor": _hostile_program(tools, "fsmonitor", log, "exit 0"),
        "core.hooksPath": str(hooks),
        "diff.external": _hostile_program(tools, "external-diff", log, "exit 0"),
        "filter.evil=drv.clean": _hostile_program(tools, "attr-clean", log, "cat"),
        "filter.info.clean": _hostile_program(tools, "info-clean", log, "cat"),
        "filter.info.process": _hostile_program(tools, "info-process", log, "exit 1"),
        "diff.info.textconv": _hostile_program(tools, "textconv", log, 'cat "$1"'),
        "diff.info.command": _hostile_program(tools, "driver-diff", log, "exit 0"),
        "log.showSignature": "true",
        "gpg.program": _hostile_program(tools, "gpg", log, "exit 1"),
    }
    for key, value in hostile_config.items():
        _git(repo, "config", key, value)
    for hook in ("post-index-change", "pre-commit", "reference-transaction"):
        _hostile_program(hooks, hook, log, "exit 0")

    # Dirty the worktree with a stale stat so status/diff would consult filters.
    (repo / "tracked.txt").write_text("first\nsecond\nthird\n", encoding="utf-8")
    os.utime(repo / "tracked.txt", (1, 1))
    monkeypatch.setenv("ARI_TEST_SECRET", SECRET)
    monkeypatch.setenv(
        "GIT_CONFIG_PARAMETERS", f"'core.fsmonitor'='{hostile_config['core.fsmonitor']}'"
    )
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-a-repo"))
    return repo, log


def _ran(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_plain_git_really_runs_the_hostile_config(hostile_repo: tuple[Path, Path]) -> None:
    """Control: proves the fixture is hostile, so the negative tests mean something."""
    repo, log = hostile_repo
    env = {k: v for k, v in os.environ.items() if k not in {"GIT_CONFIG_PARAMETERS", "GIT_DIR"}}
    subprocess.run(["git", "diff", "--shortstat"], cwd=repo, env=env, capture_output=True)

    assert any(f"secret={SECRET}" in line for line in _ran(log))


def test_controller_repo_context_runs_no_repository_program(
    hostile_repo: tuple[Path, Path], tmp_path: Path
) -> None:
    repo, log = hostile_repo

    context = build_repo_context(repo)

    assert _ran(log) == []
    assert context.git_available is True
    assert context.current_branch == "main"
    assert "tracked.txt" in context.changed_paths


def test_repo_inspector_status_and_diff_run_no_repository_program(
    hostile_repo: tuple[Path, Path],
) -> None:
    repo, log = hostile_repo

    result = inspect_repo_state(repo)

    assert _ran(log) == []
    assert result.git_available is True
    assert "tracked.txt" in result.changed_paths
    assert result.diff_summary == "1 file changed, 1 insertion(+)"


def test_content_seed_log_and_diff_run_no_repository_program(
    hostile_repo: tuple[Path, Path],
) -> None:
    repo, log = hostile_repo

    seed = generate_content_seed_from_commits(from_ref="HEAD~1", to_ref="HEAD", repo_root=repo)

    assert _ran(log) == []
    assert [commit.subject for commit in seed.source_commits] == ["second commit"]
    assert list(seed.source_files) == ["tracked.txt"]


@pytest.mark.parametrize(
    "args",
    [
        ["status", "--short"],
        ["branch", "--show-current"],
        ["diff", "--shortstat"],
        ["diff", "--name-only", "HEAD~1"],
        ["log", "-2", "--format=%s"],
    ],
)
def test_every_inspection_command_runs_no_repository_program(
    hostile_repo: tuple[Path, Path], args: list[str]
) -> None:
    repo, log = hostile_repo

    completed = run_git_inspection(args, repo)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip()
    assert _ran(log) == []


def test_inspection_environment_is_constructed_not_inherited(
    hostile_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _log = hostile_repo
    captured: list[dict[str, str]] = []
    real_run = subprocess.run

    def recording_run(*args, **kwargs):
        captured.append(dict(kwargs["env"]))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(git_inspection.subprocess, "run", recording_run)
    run_git_inspection(["status", "--short"], repo)

    assert captured
    for env in captured:
        assert SECRET not in "".join(env.values())
        assert "ARI_TEST_SECRET" not in env
        assert "GIT_CONFIG_PARAMETERS" not in env and "GIT_DIR" not in env
        assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == os.devnull
        assert env["GIT_OPTIONAL_LOCKS"] == "0"
        assert not {key for key in env if not key.startswith("GIT_")} - {
            "PATH", "HOME", "LANG", "LC_ALL", "PAGER"
        }
    overrides = {
        captured[-1][f"GIT_CONFIG_KEY_{i}"]: captured[-1][f"GIT_CONFIG_VALUE_{i}"]
        for i in range(int(captured[-1]["GIT_CONFIG_COUNT"]))
    }
    assert overrides["core.fsmonitor"] == "false"
    assert overrides["core.hooksPath"] == os.devnull
    assert overrides["diff.external"] == ""
    assert overrides["filter.evil=drv.clean"] == overrides["filter.info.process"] == ""
    assert overrides["diff.info.textconv"] == overrides["diff.info.command"] == ""


def test_static_environment_never_carries_ambient_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARI_TEST_SECRET", SECRET)
    monkeypatch.setenv("GIT_SSH_COMMAND", "evil")

    env = git_inspection_environment()

    assert SECRET not in env.values() and "GIT_SSH_COMMAND" not in env


def test_refs_cannot_become_git_options(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x")
    written = tmp_path / "written-by-git.txt"

    with pytest.raises(ValueError):
        generate_content_seed_from_commits(
            from_ref=f"--output={written}", to_ref="HEAD", repo_root=repo
        )

    assert not list(tmp_path.glob(f"{written.name}*"))  # git would write "<file>..HEAD"



def test_changed_file_listing_cannot_take_a_ref_as_an_option(tmp_path: Path) -> None:
    from ari_core.modules.self_documentation import content_seed

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x")
    written = tmp_path / "diff-output.txt"

    with pytest.raises(ValueError):
        content_seed._load_changed_files(f"--output={written}", repo, content_seed._run_git)

    assert not list(tmp_path.glob(f"{written.name}*"))

def test_only_inspection_subcommands_are_accepted(tmp_path: Path) -> None:
    for args in (["commit", "-m", "x"], ["config", "core.fsmonitor"], ["-c", "x=y", "status"], []):
        with pytest.raises(ValueError, match="Unsupported internal git inspection"):
            run_git_inspection(args, tmp_path)



# --- each layer holds on its own ---------------------------------------------------------


def test_attr_source_alone_keeps_worktree_attributes_from_selecting_a_driver(
    hostile_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, log = hostile_repo
    (repo / ".git" / "info" / "attributes").unlink()  # only worktree attributes remain
    monkeypatch.setattr(git_inspection, "_driver_overrides", lambda *_args: [])

    for args in (["status", "--short"], ["diff", "--shortstat"]):
        assert run_git_inspection(args, repo).returncode == 0

    assert _ran(log) == []


def test_driver_blanking_alone_neutralizes_drivers_selected_by_attributes(
    hostile_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, log = hostile_repo
    # Read attributes from HEAD, which contains the hostile .gitattributes.
    monkeypatch.setattr(git_inspection, "_empty_tree", lambda *_args: "HEAD")

    for args in (["status", "--short"], ["diff", "--shortstat"]):
        assert run_git_inspection(args, repo).returncode == 0

    assert _ran(log) == []


def test_no_ext_diff_alone_blocks_external_and_driver_diff_programs(
    hostile_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, log = hostile_repo
    monkeypatch.setattr(
        git_inspection,
        "NEUTRALIZED_CONFIG",
        tuple(item for item in git_inspection.NEUTRALIZED_CONFIG if item[0] != "diff.external"),
    )
    monkeypatch.setattr(
        git_inspection,
        "_driver_overrides",
        lambda *_args: [("filter.evil=drv.clean", ""), ("filter.info.clean", ""),
                        ("filter.info.process", "")],
    )

    completed = run_git_inspection(["diff", "HEAD~1"], repo)  # full patch output

    assert completed.returncode == 0 and "+second" in completed.stdout
    assert _ran(log) == []
