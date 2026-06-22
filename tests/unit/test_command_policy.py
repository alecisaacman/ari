from __future__ import annotations

from pathlib import Path

import pytest
from ari_core.modules.execution.command_policy import validate_command


@pytest.mark.parametrize(
    ("command", "category"),
    [
        (".venv312/bin/python -m pytest tests/unit -q", "unit_tests"),
        (
            ".venv312/bin/python -m pytest tests/unit/test_execution_controller.py -q",
            "focused_unit_tests",
        ),
        (
            ".venv312/bin/python -m ruff check "
            "services/ari-core/src/ari_core/modules/execution/openai_responses.py",
            "lint",
        ),
        ("git status --short", "git_inspection"),
        ("git diff --stat", "git_inspection"),
        (
            "git diff -- services/ari-core/src/ari_core/modules/execution/openai_responses.py",
            "git_inspection",
        ),
        ("ls services/ari-core/src/ari_core/modules/execution", "list"),
    ],
)
def test_command_policy_allows_safe_verification_commands(
    tmp_path: Path,
    command: str,
    category: str,
) -> None:
    result = validate_command(command, repo_root=tmp_path)

    assert result.allowed is True
    assert result.category == category
    assert result.normalized_command is not None
    assert result.rejection_code is None


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .",
        "sudo rm -rf /",
        "curl https://example.com",
        "wget https://example.com/file",
        "pip install something",
        ".venv312/bin/python -m pip install something",
        "npm install",
        "git push",
        "git reset --hard",
        "git checkout main",
        "git clean -fd",
        "open .",
        "chmod +x file",
        "git status --short; rm -rf .",
        "git status --short && git diff --stat",
        "git status --short || git diff --stat",
        "git status --short | cat",
        "git diff --stat > out.txt",
        "git diff --stat >> out.txt",
        "cat < README.md",
        "echo `whoami`",
        "echo $(whoami)",
        "ls ../outside",
        "ls /tmp/outside",
        ".venv312/bin/python scripts/dev/smoke_openai_planner.py",
        "bash scripts/dev/check.sh",
    ],
)
def test_command_policy_rejects_unsafe_commands(tmp_path: Path, command: str) -> None:
    result = validate_command(command, repo_root=tmp_path)

    assert result.allowed is False
    assert result.rejection_code is not None
    assert result.normalized_command is None


def test_command_policy_allows_absolute_path_inside_repo(tmp_path: Path) -> None:
    safe_dir = tmp_path / "services" / "ari-core"
    safe_dir.mkdir(parents=True)

    result = validate_command(f"ls {safe_dir}", repo_root=tmp_path)

    assert result.allowed is True
    assert result.category == "list"


def test_command_policy_rejects_wildcards(tmp_path: Path) -> None:
    result = validate_command(
        ".venv312/bin/python -m ruff check services/**/*.py",
        repo_root=tmp_path,
    )

    assert result.allowed is False
    assert result.rejection_code == "unsafe_path"
