from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from ari_core.modules.execution import (
    ModelPlanner,
    approve_coding_loop_retry_approval,
    approve_stored_coding_loop_retry_approval,
    execute_approved_coding_loop_retry_approval,
    get_coding_loop_retry_approval,
    list_coding_loop_retry_approvals,
    reject_coding_loop_retry_approval,
    reject_stored_coding_loop_retry_approval,
    run_one_step_coding_loop,
    store_coding_loop_retry_approval,
)
from ari_core.modules.execution.inspection import (
    get_execution_run,
    inspect_coding_loop_result,
    inspect_coding_loop_retry_approval,
)
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


def _retry_failure_result(tmp_path: Path):
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
    assert result.retry_approval is not None
    return result, root, db_path


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
    assert result.retry_approval is None
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
    assert result.retry_proposal is None
    assert result.retry_approval is None
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
    assert result.retry_approval is not None
    assert result.retry_proposal["approval_required"] is False
    assert "proof.txt" in str(result.retry_proposal["failed_verification_summary"])
    assert result.retry_proposal["suggested_next_action"] == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert result.retry_proposal["suggested_next_goal"] == "write file proof.txt with right\n"
    assert result.to_dict()["retry_proposal"] == result.retry_proposal
    retry_approval = result.retry_approval.to_dict()
    assert retry_approval["approval_id"].startswith("coding-loop-retry-approval-")
    assert retry_approval["source_coding_loop_result_id"] == result.id
    assert retry_approval["source_preview_id"] == result.preview_id
    assert retry_approval["source_execution_run_id"] == result.execution_run_id
    assert retry_approval["original_goal"] == "Create a proof file"
    assert retry_approval["proposed_retry_goal"] == "write file proof.txt with right\n"
    assert retry_approval["proposed_retry_action"] == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert retry_approval["proposed_retry_action_description"] == "write_file proof.txt"
    assert "proof.txt" in str(retry_approval["failed_verification_summary"])
    assert retry_approval["approval_status"] == "pending"
    assert retry_approval["approval"]["status"] == "pending"
    assert retry_approval["approval"]["approved_by"] is None
    assert retry_approval["approval"]["approved_at"] is None
    assert retry_approval["approval"]["rejected_reason"] is None
    assert retry_approval["retry_execution_requires_approval"] is True
    assert retry_approval["proposed_action_requires_approval"] is False
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    inspected = inspect_coding_loop_result(result)
    assert inspected["status"] == "retryable_failure"
    assert inspected["execution_occurred"] is True
    assert inspected["execution_run_id"] == result.execution_run_id
    assert inspected["retry_proposal"] == result.retry_proposal
    assert inspected["retry_approval"] == retry_approval
    assert inspected["retry_approval_id"] == retry_approval["approval_id"]
    assert inspected["retry_approval_status"] == "pending"
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
    assert result.retry_approval is not None
    assert result.retry_approval.approval.status == "pending"
    assert len(calls) == 1
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_coding_loop_retry_approval_can_be_approved_without_execution(
    tmp_path: Path,
) -> None:
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

    assert result.retry_approval is not None
    approved = approve_coding_loop_retry_approval(
        result.retry_approval,
        approval_id=result.retry_approval.approval_id,
        approved_by="alec",
        approved_at="2026-05-04T12:00:00Z",
    )

    assert approved.approval_status == "approved"
    assert approved.approval.status == "approved"
    assert approved.approval.approved_by == "alec"
    assert approved.approval.approved_at == "2026-05-04T12:00:00Z"
    assert approved.updated_at == "2026-05-04T12:00:00Z"
    assert approved.source_execution_run_id == result.execution_run_id
    assert approved.proposed_retry_goal == "write file proof.txt with right\n"
    assert approved.proposed_retry_action == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert approved.failed_verification_summary == result.retry_approval.failed_verification_summary
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    inspected = inspect_coding_loop_result({"retry_approval": approved.to_dict()})
    assert inspected["retry_approval_status"] == "approved"
    assert inspected["retry_approval_id"] == approved.approval_id


def test_coding_loop_retry_approval_can_be_rejected_without_execution(
    tmp_path: Path,
) -> None:
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

    assert result.retry_approval is not None
    rejected = reject_coding_loop_retry_approval(
        result.retry_approval,
        approval_id=result.retry_approval.approval_id,
        rejected_reason="Prefer a different fix.",
        rejected_by="alec",
        rejected_at="2026-05-04T12:05:00Z",
    )

    assert rejected.approval_status == "rejected"
    assert rejected.approval.status == "rejected"
    assert rejected.approval.rejected_reason == "Prefer a different fix."
    assert rejected.rejected_by == "alec"
    assert rejected.rejected_at == "2026-05-04T12:05:00Z"
    assert rejected.updated_at == "2026-05-04T12:05:00Z"
    assert rejected.source_execution_run_id == result.execution_run_id
    assert rejected.proposed_retry_goal == "write file proof.txt with right\n"
    assert rejected.proposed_retry_action == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert rejected.failed_verification_summary == result.retry_approval.failed_verification_summary
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    inspected = inspect_coding_loop_result({"retry_approval": rejected.to_dict()})
    assert inspected["retry_approval_status"] == "rejected"
    assert inspected["retry_approval_id"] == rejected.approval_id


def test_coding_loop_retry_approval_fails_safely_for_unknown_or_terminal_id(
    tmp_path: Path,
) -> None:
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

    assert result.retry_approval is not None
    with pytest.raises(ValueError, match="not found"):
        approve_coding_loop_retry_approval(
            result.retry_approval,
            approval_id="coding-loop-retry-approval-missing",
            approved_by="alec",
        )

    approved = approve_coding_loop_retry_approval(
        result.retry_approval,
        approval_id=result.retry_approval.approval_id,
        approved_by="alec",
    )
    with pytest.raises(ValueError, match="already terminal"):
        reject_coding_loop_retry_approval(
            approved,
            approval_id=approved.approval_id,
            rejected_reason="Too late.",
        )
    with pytest.raises(ValueError, match="already terminal"):
        approve_coding_loop_retry_approval(
            approved,
            approval_id=approved.approval_id,
            approved_by="alec",
        )

    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_coding_loop_retry_approval_is_stored_and_retrievable(tmp_path: Path) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    stored = get_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        db_path=db_path,
    )

    assert stored is not None
    assert stored.approval_id == result.retry_approval.approval_id
    assert stored.approval_status == "pending"
    assert stored.source_coding_loop_result_id == result.id
    assert stored.source_preview_id == result.preview_id
    assert stored.source_execution_run_id == result.execution_run_id
    assert stored.original_goal == "Create a proof file"
    assert stored.proposed_retry_goal == "write file proof.txt with right\n"
    assert stored.proposed_retry_action == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert stored.failed_verification_summary == result.retry_approval.failed_verification_summary
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    listed = list_coding_loop_retry_approvals(db_path=db_path)
    assert [approval.approval_id for approval in listed] == [stored.approval_id]
    inspected = inspect_coding_loop_retry_approval(stored)
    assert inspected["approval_id"] == stored.approval_id
    assert inspected["approval_status"] == "pending"


def test_stored_coding_loop_retry_approval_can_be_approved_durably(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        approved_at="2026-05-04T13:00:00Z",
        db_path=db_path,
    )
    fetched = get_coding_loop_retry_approval(approved.approval_id, db_path=db_path)

    assert fetched is not None
    assert fetched.approval_status == "approved"
    assert fetched.approval.status == "approved"
    assert fetched.approval.approved_by == "alec"
    assert fetched.approval.approved_at == "2026-05-04T13:00:00Z"
    assert fetched.source_execution_run_id == result.execution_run_id
    assert fetched.proposed_retry_goal == "write file proof.txt with right\n"
    assert fetched.proposed_retry_action == result.retry_approval.proposed_retry_action
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_stored_coding_loop_retry_approval_can_be_rejected_durably(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    rejected = reject_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        rejected_reason="Do not retry this edit.",
        rejected_by="alec",
        rejected_at="2026-05-04T13:05:00Z",
        db_path=db_path,
    )
    fetched = get_coding_loop_retry_approval(rejected.approval_id, db_path=db_path)

    assert fetched is not None
    assert fetched.approval_status == "rejected"
    assert fetched.approval.status == "rejected"
    assert fetched.approval.rejected_reason == "Do not retry this edit."
    assert fetched.rejected_by == "alec"
    assert fetched.rejected_at == "2026-05-04T13:05:00Z"
    assert fetched.source_execution_run_id == result.execution_run_id
    assert fetched.proposed_retry_goal == "write file proof.txt with right\n"
    assert fetched.proposed_retry_action == result.retry_approval.proposed_retry_action
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_stored_coding_loop_retry_approval_fails_safely(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    with pytest.raises(ValueError, match="not found"):
        approve_stored_coding_loop_retry_approval(
            "coding-loop-retry-approval-missing",
            approved_by="alec",
            db_path=db_path,
        )

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    with pytest.raises(ValueError, match="already terminal"):
        reject_stored_coding_loop_retry_approval(
            approved.approval_id,
            rejected_reason="Too late.",
            db_path=db_path,
        )
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_approved_coding_loop_retry_approval_executes_one_retry(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    executed, execution_run = execute_approved_coding_loop_retry_approval(
        approved.approval_id,
        db_path=db_path,
    )

    assert executed.retry_execution_run_id == execution_run["id"]
    assert executed.retry_execution_status == "completed"
    assert executed.retry_execution_reason == "Action executed and verification passed."
    assert executed.executed_at is not None
    assert execution_run["status"] == "completed"
    assert execution_run["cycles_run"] == 1
    assert execution_run["decisions"][0]["planner_name"] == "rule_based"
    assert (root / "proof.txt").read_text(encoding="utf-8") == "right"

    stored = get_coding_loop_retry_approval(approved.approval_id, db_path=db_path)
    assert stored is not None
    assert stored.retry_execution_run_id == execution_run["id"]
    assert stored.retry_execution_status == "completed"
    assert stored.executed_at == executed.executed_at
    inspected = inspect_coding_loop_retry_approval(stored)
    assert inspected["retry_execution_run_id"] == execution_run["id"]
    assert inspected["retry_execution_status"] == "completed"
    assert inspected["executed_at"] == executed.executed_at


def test_coding_loop_retry_execution_requires_approved_status(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    with pytest.raises(ValueError, match="must be approved"):
        execute_approved_coding_loop_retry_approval(
            result.retry_approval.approval_id,
            db_path=db_path,
        )

    rejected = reject_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        rejected_reason="Do not retry.",
        db_path=db_path,
    )
    with pytest.raises(ValueError, match="must be approved"):
        execute_approved_coding_loop_retry_approval(
            rejected.approval_id,
            db_path=db_path,
        )

    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_coding_loop_retry_execution_fails_safely_for_unknown_or_repeated_id(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    with pytest.raises(ValueError, match="not found"):
        execute_approved_coding_loop_retry_approval(
            "coding-loop-retry-approval-missing",
            db_path=db_path,
        )

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    execute_approved_coding_loop_retry_approval(approved.approval_id, db_path=db_path)
    with pytest.raises(ValueError, match="already been executed"):
        execute_approved_coding_loop_retry_approval(approved.approval_id, db_path=db_path)

    assert (root / "proof.txt").read_text(encoding="utf-8") == "right"


def test_approved_coding_loop_retry_execution_keeps_unsafe_retry_closed(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    unsafe = replace(
        approved,
        proposed_retry_goal="run rm -rf .",
        proposed_retry_action={"type": "run_command", "command": ["rm", "-rf", "."]},
        proposed_retry_action_description="run_command ['rm', '-rf', '.']",
    )
    store_coding_loop_retry_approval(unsafe, db_path=db_path)

    executed, execution_run = execute_approved_coding_loop_retry_approval(
        unsafe.approval_id,
        db_path=db_path,
    )

    assert execution_run["status"] == "rejected"
    assert executed.retry_execution_status == "rejected"
    assert "command is not allowlisted" in executed.retry_execution_reason
    assert execution_run["cycles_run"] == 1
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
