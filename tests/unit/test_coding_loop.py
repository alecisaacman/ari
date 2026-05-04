from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ari_core.modules.execution import ModelPlanner, run_one_step_coding_loop
from ari_core.modules.execution.inspection import get_execution_run, inspect_coding_loop_result
from ari_core.modules.execution.models import (
    ExecutionGoal,
    PlannerResult,
    RepoContext,
    WorkerAction,
    WorkerPlan,
)


class _ApprovalPlanner:
    planner_name = "approval_test"

    def plan(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: object | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        del goal, repo_context, failure_context, memory_context
        return PlannerResult(
            status="act",
            reason="Propose an action that requires explicit authority.",
            confidence=0.9,
            planner_name=self.planner_name,
            plan=WorkerPlan(
                actions=(
                    WorkerAction(
                        action_type="write_file",
                        payload={"path": "approval.txt", "content": "pending"},
                        reason="Authority-gated write for approval test.",
                        requires_approval=True,
                    ),
                ),
                verification=(),
                reason="Approval-gated one-step plan.",
            ),
        )


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
    assert result.retry_proposal is None
    assert result.approval_required_reason is None
    assert (root / "proof.txt").read_text(encoding="utf-8") == "ready"


def test_one_step_coding_loop_returns_requires_approval_without_execution(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_one_step_coding_loop(
        "Write an authority-gated file",
        execution_root=root,
        db_path=db_path,
        planner=_ApprovalPlanner(),
    )

    assert result.status == "requires_approval"
    assert result.execution_run_id is None
    assert result.preview_id is not None
    assert result.preview is not None
    assert result.approval_required_reason is not None
    assert "Approval required" in result.approval_required_reason
    assert result.to_dict()["approval_required_reason"] == result.approval_required_reason
    assert not (root / "approval.txt").exists()

    inspected = inspect_coding_loop_result(result)
    assert inspected["status"] == "requires_approval"
    assert inspected["execution_occurred"] is False
    assert inspected["execution_run_id"] is None
    assert inspected["approval_required_reason"] == result.approval_required_reason


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


def test_one_step_coding_loop_verification_failure_proposes_retry(tmp_path: Path) -> None:
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

    assert result.status == "retryable_failure"
    assert result.execution_run is not None
    assert result.execution_run_id is not None
    assert result.execution_run["results"][0]["verified"] is False
    assert result.retry_proposal is not None
    assert result.retry_proposal["approval_required"] is False
    assert "proof.txt" in str(result.retry_proposal["failed_verification_summary"])
    assert result.retry_proposal["suggested_next_action"] == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert result.retry_proposal["suggested_next_goal"] == "write file proof.txt with right\n"
    assert result.to_dict()["retry_proposal"] == result.retry_proposal
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    inspected = inspect_coding_loop_result(result)
    assert inspected["status"] == "retryable_failure"
    assert inspected["execution_occurred"] is True
    assert inspected["execution_run_id"] == result.execution_run_id
    assert inspected["retry_proposal"] == result.retry_proposal
    assert inspected["suggested_next_goal"] == "write file proof.txt with right\n"
    assert inspected["retry_requires_approval"] is False


def test_one_step_coding_loop_retry_proposal_does_not_execute(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "proof.txt").write_text("old\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def completion(payload: dict[str, object]) -> str:
        calls.append(dict(payload))
        return json.dumps(
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

    result = run_one_step_coding_loop(
        "Create a proof file",
        execution_root=root,
        db_path=db_path,
        planner=ModelPlanner(completion),
    )

    assert result.status == "retryable_failure"
    assert result.retry_proposal is not None
    assert len(calls) == 1
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
