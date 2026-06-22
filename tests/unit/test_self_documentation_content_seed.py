from __future__ import annotations

import json
from pathlib import Path

from ari_core.modules.self_documentation import (
    GitCommandResult,
    generate_content_seed_from_commits,
)


def test_content_seed_generated_from_mocked_commit_range(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(args, cwd):
        del cwd
        calls.append(tuple(args))
        if args[0] == "log":
            return GitCommandResult(
                stdout=(
                    "abc123456789\x1fDocument ARI self-documentation skill\n"
                    "def456789abc\x1fDocument self-documentation stage 1 readiness\n"
                )
            )
        if args[0] == "diff":
            return GitCommandResult(
                stdout=(
                    "docs/skills/self-documentation-skill.md\n"
                    "docs/skills/self-documentation-stage-1-readiness.md\n"
                )
            )
        raise AssertionError(f"unexpected git args: {args}")

    seed = generate_content_seed_from_commits(
        from_ref="abc1234",
        to_ref="def4567",
        repo_root=tmp_path,
        test_output=".venv312/bin/python -m pytest tests/unit -q\n177 passed",
        git_runner=fake_git,
    )

    assert seed.source_commit_range == "abc1234..def4567"
    assert [commit.hash for commit in seed.source_commits] == [
        "abc123456789",
        "def456789abc",
    ]
    assert [commit.subject for commit in seed.source_commits] == [
        "Document ARI self-documentation skill",
        "Document self-documentation stage 1 readiness",
    ]
    assert seed.source_files == (
        "docs/skills/self-documentation-skill.md",
        "docs/skills/self-documentation-stage-1-readiness.md",
    )
    assert any("Commit abc123456789" in point for point in seed.proof_points)
    assert any("Changed 2 file" in point for point in seed.proof_points)
    assert any("177 passed" in point for point in seed.proof_points)
    assert seed.hook_options
    assert "content seed" in seed.demo_idea.lower()
    assert seed.claims_to_avoid
    assert calls == [
        ("log", "--reverse", "--format=%H%x1f%s", "abc1234..def4567"),
        ("diff", "--name-only", "abc1234..def4567"),
    ]


def test_content_seed_flags_sensitive_looking_input(tmp_path: Path) -> None:
    def fake_git(args, cwd):
        del cwd
        if args[0] == "log":
            return GitCommandResult(
                stdout=(
                    "abc123\x1fAvoid leaking alec@example.com token in "
                    "/Users/alecisaacman/private\n"
                )
            )
        if args[0] == "diff":
            return GitCommandResult(stdout=".env\nservices/demo.py\n")
        raise AssertionError(f"unexpected git args: {args}")

    seed = generate_content_seed_from_commits(
        from_ref="a",
        to_ref="b",
        repo_root=tmp_path,
        test_output="OPENAI_API_KEY=sk-testsecret123456789",
        git_runner=fake_git,
    )

    risk_text = " ".join(seed.risk_notes)
    assert "API key-like" in risk_text
    assert "Secret-like" in risk_text
    assert ".env" in risk_text
    assert "Private absolute path" in risk_text
    assert "Email address" in risk_text
    assert "Review and redact" in " ".join(seed.redaction_notes)
    assert "Do not publish raw inputs" in " ".join(seed.claims_to_avoid)


def test_content_seed_is_json_serializable_and_non_persistent(tmp_path: Path) -> None:
    created_paths_before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    def fake_git(args, cwd):
        del cwd
        if args[0] == "log":
            return GitCommandResult(stdout="abc123\x1fDocument skill inventory\n")
        if args[0] == "diff":
            return GitCommandResult(stdout="docs/skills/skill-inventory.md\n")
        raise AssertionError(f"unexpected git args: {args}")

    seed = generate_content_seed_from_commits(
        from_ref="abc",
        to_ref="def",
        repo_root=tmp_path,
        user_framing="Explain this as ARI becoming a brain that can use skills.",
        git_runner=fake_git,
    )

    payload = seed.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    created_paths_after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert decoded["seed_id"].startswith("content-seed-")
    assert decoded["source_commits"][0]["subject"] == "Document skill inventory"
    assert "User-approved framing" in " ".join(decoded["proof_points"])
    assert created_paths_after == created_paths_before


def test_content_seed_does_not_call_external_services(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_git(args, cwd):
        del cwd
        commands.append(tuple(args))
        if args[0] == "log":
            return GitCommandResult(stdout="abc123\x1fDocument ACE dashboard contract\n")
        if args[0] == "diff":
            return GitCommandResult(stdout="docs/ace/read-only-dashboard-contract.md\n")
        raise AssertionError(f"unexpected git args: {args}")

    generate_content_seed_from_commits(
        from_ref="abc",
        to_ref="def",
        repo_root=tmp_path,
        git_runner=fake_git,
    )

    assert all(command[0] in {"log", "diff"} for command in commands)
    assert not any(command[0] in {"curl", "wget", "open", "ssh"} for command in commands)
