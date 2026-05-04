from __future__ import annotations

import json
from pathlib import Path

from ari_core.modules.execution import ModelPlanner, run_one_step_coding_loop
from ari_core.modules.execution.inspection import get_execution_run


def test_one_step_coding_loop_completes_safe_grounded_action(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_one_step_coding_loop(
        "write file proof.txt with ready\n",
        execution_root=root,
        db_path=db_path,
    )

    assert result.status == "success"
    assert result.execution_run_id is not None
    assert result.preview_id is not None
    assert (root / "proof.txt").read_text(encoding="utf-8") == "ready"


def test_one_step_coding_loop_rejects_unsafe_action_before_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("safe\n", encoding="utf-8")
    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.9,
                "reason": "Unsafe command should fail closed.",
                "actions": [{"type": "run_command", "command": ["rm", "-rf", "."]}],
            }
        )
    )

    result = run_one_step_coding_loop(
        "Clean the repo",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "unsafe"
    assert result.execution_run_id is None
    assert (root / "README.md").read_text(encoding="utf-8") == "safe\n"


def test_one_step_coding_loop_asks_user_when_no_safe_action_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_one_step_coding_loop(
        "Invent a broad product strategy",
        execution_root=root,
        db_path=db_path,
    )

    assert result.status == "ask_user"
    assert result.execution_run_id is None
    assert "No bounded execution action matched" in result.reason


def test_one_step_coding_loop_verification_failure_blocks_result(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "proof.txt").write_text("old\n", encoding="utf-8")
    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.9,
                "reason": "Write content that will fail explicit verification.",
                "actions": [
                    {
                        "type": "write_file",
                        "path": "proof.txt",
                        "content": "wrong\n",
                    }
                ],
                "verification": [
                    {
                        "type": "file_content",
                        "target": "proof.txt",
                        "expected": "right\n",
                    }
                ],
            }
        )
    )

    result = run_one_step_coding_loop(
        "Create a proof file",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "blocked"
    assert result.execution_run is not None
    assert result.execution_run["results"][0]["verified"] is False
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_one_step_coding_loop_lifecycle_is_inspectable(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_one_step_coding_loop(
        "write file proof.txt with lifecycle",
        execution_root=root,
        db_path=db_path,
    )

    assert result.status == "success"
    assert result.execution_run_id is not None
    stored = get_execution_run(result.execution_run_id, db_path=db_path)
    assert stored is not None
    assert stored["status"] == "completed"
    assert result.to_dict()["execution_run_id"] == result.execution_run_id


def test_one_step_coding_loop_adds_no_arbitrary_shell_access(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.9,
                "reason": "Try an arbitrary network command.",
                "actions": [{"type": "run_command", "command": ["curl", "https://example.com"]}],
            }
        )
    )

    result = run_one_step_coding_loop(
        "Fetch a URL",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "unsafe"
    assert result.execution_run_id is None


def test_one_step_coding_loop_does_not_run_multi_step_plans(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_one_step_coding_loop(
        "write files one.txt with one; two.txt with two",
        execution_root=root,
        db_path=db_path,
    )

    assert result.status == "blocked"
    assert result.execution_run_id is None
    assert "exactly one candidate action" in result.reason
    assert not (root / "one.txt").exists()
    assert not (root / "two.txt").exists()
