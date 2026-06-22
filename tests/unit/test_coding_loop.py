from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from ari_core.modules.execution import (
    ModelPlanner,
    advance_coding_loop_retry_chain,
    approve_coding_loop_retry_approval,
    approve_latest_pending_coding_loop_retry_approval,
    approve_stored_coding_loop_retry_approval,
    create_coding_loop_retry_approval_from_review,
    decide_coding_loop_retry_continuation,
    execute_approved_coding_loop_retry_approval,
    get_coding_loop_retry_approval,
    list_coding_loop_retry_approvals,
    propose_next_coding_loop_retry_approval_from_chain,
    reject_coding_loop_retry_approval,
    reject_latest_pending_coding_loop_retry_approval,
    reject_stored_coding_loop_retry_approval,
    review_coding_loop_retry_execution,
    run_one_step_coding_loop,
    store_coding_loop_retry_approval,
)
from ari_core.modules.execution.inspection import (
    get_coding_loop_result,
    get_execution_run,
    inspect_coding_loop_chain,
    inspect_coding_loop_continuation_decision,
    inspect_coding_loop_result,
    inspect_coding_loop_retry_approval,
    inspect_coding_loop_retry_execution_review,
    list_coding_loop_results,
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

    review = review_coding_loop_retry_execution(approved.approval_id, db_path=db_path)
    inspected_review = inspect_coding_loop_retry_execution_review(review)
    assert inspected_review["status"] == "stop"
    assert inspected_review["retry_execution_run_id"] == execution_run["id"]
    assert inspected_review["retry_execution_status"] == "completed"
    assert inspected_review["approval_required"] is False
    assert inspected_review["suggested_next_goal"] is None


def test_coding_loop_retry_execution_requires_approved_status(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    pending_review = review_coding_loop_retry_execution(
        result.retry_approval.approval_id,
        db_path=db_path,
    )
    assert pending_review.status == "not_executed"
    assert pending_review.retry_execution_run_id is None

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

    review = review_coding_loop_retry_execution(unsafe.approval_id, db_path=db_path)
    assert review.status == "unsafe"
    assert review.retry_execution_run_id == execution_run["id"]
    assert review.suggested_next_goal is None


def test_coding_loop_retry_execution_review_can_propose_next_approval_item(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None
    assert result.execution_run_id is not None

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)

    review = review_coding_loop_retry_execution(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )

    assert review.status == "propose_retry"
    assert review.retry_execution_run_id == result.execution_run_id
    assert review.retry_execution_status == "exhausted"
    assert review.suggested_next_goal == "write file proof.txt with right\n"
    assert review.suggested_next_action == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert review.approval_required is True
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_coding_loop_continuation_policy_is_inspectable_and_bounded(
    tmp_path: Path,
) -> None:
    result, _root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    pending = decide_coding_loop_retry_continuation(
        result.retry_approval.approval_id,
        db_path=db_path,
    )
    assert pending.eligible is False
    assert pending.status == "not_executed"
    assert pending.review_status == "not_executed"
    assert pending.next_retry_approval_id is None

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)

    continuation = decide_coding_loop_retry_continuation(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    inspected = inspect_coding_loop_continuation_decision(continuation)
    assert inspected["eligible"] is True
    assert inspected["status"] == "create_pending_approval"
    assert inspected["review_status"] == "propose_retry"
    assert inspected["suggested_next_goal"] == "write file proof.txt with right\n"
    assert inspected["suggested_next_action"] == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert inspected["approval_required"] is True

    next_approval = create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    duplicate = decide_coding_loop_retry_continuation(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    assert duplicate.eligible is False
    assert duplicate.status == "duplicate_exists"
    assert duplicate.next_retry_approval_id == next_approval.approval_id


def test_propose_retry_review_creates_pending_follow_up_approval(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None
    assert result.execution_run_id is not None

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)

    next_approval = create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )

    assert next_approval.approval_status == "pending"
    assert next_approval.approval.status == "pending"
    assert next_approval.prior_retry_approval_id == reviewed_failed_retry.approval_id
    assert next_approval.prior_retry_execution_run_id == result.execution_run_id
    assert next_approval.source_execution_run_id == result.execution_run_id
    assert next_approval.original_goal == "Create a proof file"
    assert next_approval.proposed_retry_goal == "write file proof.txt with right\n"
    assert next_approval.proposed_retry_action == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert next_approval.proposed_retry_action_description == "write_file proof.txt"
    assert "Retry execution failed verification" in next_approval.reason
    assert "Prior retry execution status: exhausted." in (
        next_approval.failed_verification_summary
    )
    assert next_approval.retry_execution_run_id is None
    assert next_approval.executed_at is None
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    fetched_next = get_coding_loop_retry_approval(
        next_approval.approval_id,
        db_path=db_path,
    )
    assert fetched_next is not None
    assert fetched_next.prior_retry_approval_id == reviewed_failed_retry.approval_id
    fetched_prior = get_coding_loop_retry_approval(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    assert fetched_prior is not None
    assert fetched_prior.next_retry_approval_id == next_approval.approval_id

    inspected = inspect_coding_loop_retry_approval(fetched_next)
    assert inspected["approval_status"] == "pending"
    assert inspected["prior_retry_approval_id"] == reviewed_failed_retry.approval_id
    assert inspected["prior_retry_execution_run_id"] == result.execution_run_id

    listed_ids = [
        approval.approval_id
        for approval in list_coding_loop_retry_approvals(limit=5, db_path=db_path)
    ]
    assert next_approval.approval_id in listed_ids

    with pytest.raises(ValueError, match="already produced"):
        create_coding_loop_retry_approval_from_review(
            reviewed_failed_retry.approval_id,
            db_path=db_path,
        )


def test_non_propose_retry_review_does_not_create_follow_up_approval(
    tmp_path: Path,
) -> None:
    result, _root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    with pytest.raises(ValueError, match="has not executed"):
        create_coding_loop_retry_approval_from_review(
            result.retry_approval.approval_id,
            db_path=db_path,
        )

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    execute_approved_coding_loop_retry_approval(approved.approval_id, db_path=db_path)

    with pytest.raises(ValueError, match="not propose_retry"):
        create_coding_loop_retry_approval_from_review(
            approved.approval_id,
            db_path=db_path,
        )

    with pytest.raises(ValueError, match="not found"):
        create_coding_loop_retry_approval_from_review(
            "coding-loop-retry-approval-missing",
            db_path=db_path,
        )


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

    persisted = get_coding_loop_result(result.id, db_path=db_path)
    assert persisted is not None
    assert persisted["id"] == result.id
    assert persisted["status"] == "success"
    assert persisted["original_goal"] == "write file proof.txt with lifecycle"
    assert persisted["execution_run_id"] == result.execution_run_id
    assert persisted["execution_occurred"] is True
    assert persisted["retry_proposal"] is None
    assert persisted["retry_approval_id"] is None
    assert persisted["post_run_review"] is None
    assert "execution_run" not in persisted


def test_coding_loop_result_persists_non_executing_outcomes(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("safe\n", encoding="utf-8")

    ask_user = run_one_step_coding_loop(
        "Invent a broad product strategy",
        execution_root=root,
        db_path=db_path,
    )
    blocked = run_one_step_coding_loop(
        "write files one.txt with one; two.txt with two",
        execution_root=root,
        db_path=db_path,
    )
    unsafe = run_one_step_coding_loop(
        "run rm -rf .",
        execution_root=root,
        db_path=db_path,
    )
    requires_approval = run_one_step_coding_loop(
        "Write an authority-gated file",
        execution_root=root,
        db_path=db_path,
        planner=_ApprovalPlanner(),
    )

    persisted = {
        result.id: get_coding_loop_result(result.id, db_path=db_path)
        for result in (ask_user, blocked, unsafe, requires_approval)
    }

    assert persisted[ask_user.id] is not None
    assert persisted[ask_user.id]["status"] == "ask_user"
    assert persisted[ask_user.id]["execution_occurred"] is False
    assert persisted[blocked.id]["status"] == "blocked"
    assert persisted[blocked.id]["execution_run_id"] is None
    assert persisted[unsafe.id]["status"] == "unsafe"
    assert persisted[unsafe.id]["execution_occurred"] is False
    assert persisted[requires_approval.id]["status"] == "requires_approval"
    assert persisted[requires_approval.id]["approval_required_reason"] is not None
    assert not (root / "approval.txt").exists()

    listed = list_coding_loop_results(limit=10, db_path=db_path)
    listed_ids = {result["id"] for result in listed}
    assert {ask_user.id, blocked.id, unsafe.id, requires_approval.id}.issubset(
        listed_ids
    )


def test_coding_loop_result_tracks_retry_approval_review_and_lineage(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    persisted = get_coding_loop_result(result.id, db_path=db_path)
    assert persisted is not None
    assert persisted["status"] == "retryable_failure"
    assert persisted["retry_proposal"] == result.retry_proposal
    assert persisted["retry_approval_id"] == result.retry_approval.approval_id
    assert persisted["retry_approval_status"] == "pending"
    assert persisted["suggested_next_goal"] == "write file proof.txt with right\n"
    assert persisted["suggested_next_action"] == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    executed, execution_run = execute_approved_coding_loop_retry_approval(
        approved.approval_id,
        db_path=db_path,
    )
    persisted_after_execution = get_coding_loop_result(result.id, db_path=db_path)
    assert persisted_after_execution is not None
    assert persisted_after_execution["retry_approval_status"] == "approved"
    assert persisted_after_execution["retry_execution_run_id"] == execution_run["id"]
    assert persisted_after_execution["retry_execution_status"] == "completed"
    assert persisted_after_execution["post_run_review"]["status"] == "stop"
    assert persisted_after_execution["post_run_review"]["retry_execution_run_id"] == (
        execution_run["id"]
    )
    assert persisted_after_execution["next_retry_approval_id"] is None
    assert (root / "proof.txt").read_text(encoding="utf-8") == "right"

    reviewed_failed_retry = replace(
        executed,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
        next_retry_approval_id=None,
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)
    next_approval = create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    persisted_after_next = get_coding_loop_result(result.id, db_path=db_path)
    assert persisted_after_next is not None
    assert persisted_after_next["post_run_review"]["status"] == "propose_retry"
    assert persisted_after_next["next_retry_approval_id"] == next_approval.approval_id
    assert persisted_after_next["suggested_next_goal"] == "write file proof.txt with right\n"
    assert persisted_after_next["retry_execution_status"] == "exhausted"


def test_coding_loop_retry_chain_inspection_reconstructs_lineage(
    tmp_path: Path,
) -> None:
    result, _root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    pending_chain = inspect_coding_loop_chain(result.id, db_path=db_path)
    assert pending_chain is not None
    assert pending_chain["root_coding_loop_result_id"] == result.id
    assert pending_chain["original_goal"] == "Create a proof file"
    assert pending_chain["initial_status"] == "retryable_failure"
    assert pending_chain["initial_execution_run_id"] == result.execution_run_id
    assert pending_chain["terminal_status"] == "pending_approval"
    assert pending_chain["chain_depth"] == 1
    assert pending_chain["retry_approvals"][0]["approval_status"] == "pending"
    assert pending_chain["retry_approvals"][0]["post_run_review"]["status"] == (
        "not_executed"
    )
    assert pending_chain["retry_approvals"][0]["continuation"]["status"] == (
        "not_executed"
    )

    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    approved_chain = inspect_coding_loop_chain(result.id, db_path=db_path)
    assert approved_chain is not None
    assert approved_chain["terminal_status"] == "executable_approved_retry_available"
    assert approved_chain["retry_approvals"][0]["approval_status"] == "approved"

    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)
    next_approval = create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )

    chain = inspect_coding_loop_chain(result.id, db_path=db_path)
    assert chain is not None
    assert chain["terminal_status"] == "pending_approval"
    assert chain["chain_depth"] == 2
    assert chain["truncated"] is False
    assert chain["cycle_detected"] is False
    assert [item["approval_id"] for item in chain["retry_approvals"]] == [
        reviewed_failed_retry.approval_id,
        next_approval.approval_id,
    ]
    first = chain["retry_approvals"][0]
    second = chain["retry_approvals"][1]
    assert first["retry_execution_run_id"] == result.execution_run_id
    assert first["retry_execution_status"] == "exhausted"
    assert first["retry_execution_reason"] == (
        "Retryable execution failed until max_cycles was exhausted."
    )
    assert first["post_run_review"]["status"] == "propose_retry"
    assert first["continuation"]["status"] == "duplicate_exists"
    assert first["next_retry_approval_id"] == next_approval.approval_id
    assert second["approval_status"] == "pending"
    assert second["post_run_review"]["status"] == "not_executed"
    assert chain["next_retry_approval_id"] is None

    shallow = inspect_coding_loop_chain(result.id, max_depth=1, db_path=db_path)
    assert shallow is not None
    assert shallow["chain_depth"] == 1
    assert shallow["truncated"] is True
    assert shallow["terminal_status"] == "unknown/incomplete"


def test_coding_loop_retry_chain_terminal_statuses(
    tmp_path: Path,
) -> None:
    stopped_parent = tmp_path / "stopped"
    stopped_parent.mkdir()
    stopped_result, _root, db_path = _retry_failure_result(stopped_parent)
    assert stopped_result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        stopped_result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    execute_approved_coding_loop_retry_approval(approved.approval_id, db_path=db_path)
    stopped_chain = inspect_coding_loop_chain(stopped_result.id, db_path=db_path)
    assert stopped_chain is not None
    assert stopped_chain["terminal_status"] == "stopped"
    assert stopped_chain["retry_approvals"][0]["post_run_review"]["status"] == "stop"

    rejected_parent = tmp_path / "rejected"
    rejected_parent.mkdir()
    rejected_result, _root, db_path = _retry_failure_result(rejected_parent)
    assert rejected_result.retry_approval is not None
    reject_stored_coding_loop_retry_approval(
        rejected_result.retry_approval.approval_id,
        rejected_reason="No retry.",
        db_path=db_path,
    )
    rejected_chain = inspect_coding_loop_chain(rejected_result.id, db_path=db_path)
    assert rejected_chain is not None
    assert rejected_chain["terminal_status"] == "rejected"


def test_coding_loop_chain_advancement_executes_one_approved_retry(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None
    approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )

    advancement = advance_coding_loop_retry_chain(result.id, db_path=db_path)

    assert advancement.root_coding_loop_result_id == result.id
    assert advancement.prior_terminal_status == "executable_approved_retry_available"
    assert advancement.action_taken == "executed_approved_retry"
    assert advancement.executed_retry_approval_id == result.retry_approval.approval_id
    assert advancement.retry_execution_run_id is not None
    assert advancement.refreshed_terminal_status == "stopped"
    assert advancement.refreshed_chain is not None
    assert advancement.refreshed_chain["terminal_status"] == "stopped"
    assert advancement.refreshed_chain["chain_depth"] == 1
    assert "One approved retry" in str(advancement.stop_reason)
    assert (root / "proof.txt").read_text(encoding="utf-8") == "right"

    stored = get_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        db_path=db_path,
    )
    assert stored is not None
    assert stored.retry_execution_run_id == advancement.retry_execution_run_id

    repeated = advance_coding_loop_retry_chain(result.id, db_path=db_path)
    assert repeated.action_taken == "no_action"
    assert repeated.prior_terminal_status == "stopped"
    assert repeated.retry_execution_run_id is None


def test_coding_loop_chain_advancement_refuses_non_executable_chains(
    tmp_path: Path,
) -> None:
    pending_parent = tmp_path / "pending"
    pending_parent.mkdir()
    pending_result, pending_root, db_path = _retry_failure_result(pending_parent)
    assert pending_result.retry_approval is not None
    pending = advance_coding_loop_retry_chain(pending_result.id, db_path=db_path)
    assert pending.action_taken == "no_action"
    assert pending.prior_terminal_status == "pending_approval"
    assert pending.retry_execution_run_id is None
    assert pending_root.joinpath("proof.txt").read_text(encoding="utf-8") == "wrong\n"

    rejected_parent = tmp_path / "rejected-advance"
    rejected_parent.mkdir()
    rejected_result, rejected_root, db_path = _retry_failure_result(rejected_parent)
    assert rejected_result.retry_approval is not None
    reject_stored_coding_loop_retry_approval(
        rejected_result.retry_approval.approval_id,
        rejected_reason="No retry.",
        db_path=db_path,
    )
    rejected = advance_coding_loop_retry_chain(rejected_result.id, db_path=db_path)
    assert rejected.action_taken == "no_action"
    assert rejected.prior_terminal_status == "rejected"
    assert rejected.retry_execution_run_id is None
    assert rejected_root.joinpath("proof.txt").read_text(encoding="utf-8") == "wrong\n"

    stopped_parent = tmp_path / "stopped-advance"
    stopped_parent.mkdir()
    stopped_result, stopped_root, db_path = _retry_failure_result(stopped_parent)
    assert stopped_result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        stopped_result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    execute_approved_coding_loop_retry_approval(approved.approval_id, db_path=db_path)
    stopped = advance_coding_loop_retry_chain(stopped_result.id, db_path=db_path)
    assert stopped.action_taken == "no_action"
    assert stopped.prior_terminal_status == "stopped"
    assert stopped.retry_execution_run_id is None
    assert stopped_root.joinpath("proof.txt").read_text(encoding="utf-8") == "right"

    unsafe_parent = tmp_path / "unsafe-advance"
    unsafe_parent.mkdir()
    unsafe_root = unsafe_parent / "repo"
    unsafe_root.mkdir()
    unsafe_result = run_one_step_coding_loop(
        "run rm -rf .",
        execution_root=unsafe_root,
        db_path=unsafe_parent / "state" / "networking.db",
    )
    unsafe = advance_coding_loop_retry_chain(
        unsafe_result.id,
        db_path=unsafe_parent / "state" / "networking.db",
    )
    assert unsafe.action_taken == "no_action"
    assert unsafe.prior_terminal_status == "unsafe"

    with pytest.raises(ValueError, match="not found"):
        advance_coding_loop_retry_chain(
            "coding-loop-result-missing",
            db_path=db_path,
        )


def test_coding_loop_chain_advancement_refuses_incomplete_traversal(
    tmp_path: Path,
) -> None:
    result, _root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)
    next_approval = create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    approve_stored_coding_loop_retry_approval(
        next_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )

    advancement = advance_coding_loop_retry_chain(
        result.id,
        max_depth=1,
        db_path=db_path,
    )

    assert advancement.action_taken == "rejected"
    assert advancement.prior_terminal_status == "unknown/incomplete"
    assert advancement.retry_execution_run_id is None
    refreshed = advancement.refreshed_chain
    assert refreshed is not None
    assert refreshed["truncated"] is True
    latest = get_coding_loop_retry_approval(next_approval.approval_id, db_path=db_path)
    assert latest is not None
    assert latest.retry_execution_run_id is None


def test_coding_loop_chain_approve_latest_uses_existing_pending_approval(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    mutation = approve_latest_pending_coding_loop_retry_approval(
        result.id,
        approved_by="alec",
        db_path=db_path,
    )

    assert mutation.root_coding_loop_result_id == result.id
    assert mutation.action_taken == "approved_latest"
    assert mutation.updated_retry_approval.approval_id == result.retry_approval.approval_id
    assert mutation.updated_retry_approval.approval_status == "approved"
    assert mutation.updated_retry_approval.approval.approved_by == "alec"
    assert mutation.updated_retry_approval.retry_execution_run_id is None
    assert mutation.refreshed_chain is not None
    assert mutation.refreshed_chain["terminal_status"] == (
        "executable_approved_retry_available"
    )
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_coding_loop_chain_reject_latest_uses_existing_pending_approval(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None

    mutation = reject_latest_pending_coding_loop_retry_approval(
        result.id,
        rejected_reason="Not this retry.",
        rejected_by="alec",
        db_path=db_path,
    )

    assert mutation.root_coding_loop_result_id == result.id
    assert mutation.action_taken == "rejected_latest"
    assert mutation.updated_retry_approval.approval_id == result.retry_approval.approval_id
    assert mutation.updated_retry_approval.approval_status == "rejected"
    assert mutation.updated_retry_approval.rejected_by == "alec"
    assert mutation.updated_retry_approval.retry_execution_run_id is None
    assert mutation.refreshed_chain is not None
    assert mutation.refreshed_chain["terminal_status"] == "rejected"
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"


def test_coding_loop_chain_approve_latest_targets_latest_pending_approval(
    tmp_path: Path,
) -> None:
    result, _root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)
    next_approval = create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )

    mutation = approve_latest_pending_coding_loop_retry_approval(
        result.id,
        approved_by="alec",
        db_path=db_path,
    )

    assert mutation.updated_retry_approval.approval_id == next_approval.approval_id
    assert mutation.updated_retry_approval.approval_status == "approved"
    assert mutation.updated_retry_approval.retry_execution_run_id is None
    assert mutation.refreshed_chain is not None
    assert mutation.refreshed_chain["terminal_status"] == (
        "executable_approved_retry_available"
    )
    prior = get_coding_loop_retry_approval(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    assert prior is not None
    assert prior.retry_execution_run_id == result.execution_run_id


def test_coding_loop_chain_latest_approval_mutation_refuses_invalid_chains(
    tmp_path: Path,
) -> None:
    success_db = tmp_path / "success" / "state" / "networking.db"
    success_root = tmp_path / "success" / "repo"
    success_root.mkdir(parents=True)
    success = run_one_step_coding_loop(
        "write file done.txt with done",
        execution_root=success_root,
        db_path=success_db,
    )
    with pytest.raises(ValueError, match="no pending retry approval"):
        approve_latest_pending_coding_loop_retry_approval(
            success.id,
            approved_by="alec",
            db_path=success_db,
        )

    approved_parent = tmp_path / "pending-then-approved"
    approved_parent.mkdir()
    result, _root, db_path = _retry_failure_result(approved_parent)
    assert result.retry_approval is not None
    approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    with pytest.raises(ValueError, match="no pending retry approval"):
        reject_latest_pending_coding_loop_retry_approval(
            result.id,
            rejected_reason="Too late.",
            db_path=db_path,
        )

    deep_parent = tmp_path / "truncated-approval"
    deep_parent.mkdir()
    deep_result, _root, deep_db = _retry_failure_result(deep_parent)
    assert deep_result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        deep_result.retry_approval.approval_id,
        approved_by="alec",
        db_path=deep_db,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=deep_result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=deep_db)
    create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=deep_db,
    )
    with pytest.raises(ValueError, match="truncated"):
        approve_latest_pending_coding_loop_retry_approval(
            deep_result.id,
            approved_by="alec",
            max_depth=1,
            db_path=deep_db,
        )

    with pytest.raises(ValueError, match="not found"):
        approve_latest_pending_coding_loop_retry_approval(
            "coding-loop-result-missing",
            approved_by="alec",
            db_path=deep_db,
        )


def test_coding_loop_chain_propose_next_creates_pending_approval(
    tmp_path: Path,
) -> None:
    result, root, db_path = _retry_failure_result(tmp_path)
    assert result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=db_path)

    proposal = propose_next_coding_loop_retry_approval_from_chain(
        result.id,
        db_path=db_path,
    )

    next_approval = proposal.new_retry_approval
    assert proposal.root_coding_loop_result_id == result.id
    assert next_approval.approval_status == "pending"
    assert next_approval.retry_execution_run_id is None
    assert next_approval.prior_retry_approval_id == reviewed_failed_retry.approval_id
    assert next_approval.prior_retry_execution_run_id == result.execution_run_id
    assert next_approval.source_coding_loop_result_id == result.id
    assert next_approval.original_goal == "Create a proof file"
    assert next_approval.proposed_retry_goal == "write file proof.txt with right\n"
    assert next_approval.proposed_retry_action == {
        "type": "write_file",
        "path": "proof.txt",
        "content": "right\n",
    }
    assert proposal.refreshed_chain is not None
    assert proposal.refreshed_chain["terminal_status"] == "pending_approval"
    assert proposal.refreshed_chain["chain_depth"] == 2
    assert (root / "proof.txt").read_text(encoding="utf-8") == "wrong\n"

    prior = get_coding_loop_retry_approval(
        reviewed_failed_retry.approval_id,
        db_path=db_path,
    )
    assert prior is not None
    assert prior.next_retry_approval_id == next_approval.approval_id

    with pytest.raises(ValueError, match="already produced"):
        propose_next_coding_loop_retry_approval_from_chain(result.id, db_path=db_path)


def test_coding_loop_chain_propose_next_refuses_non_eligible_chains(
    tmp_path: Path,
) -> None:
    pending_parent = tmp_path / "pending-propose"
    pending_parent.mkdir()
    pending_result, _root, db_path = _retry_failure_result(pending_parent)
    with pytest.raises(ValueError, match="no eligible propose_retry"):
        propose_next_coding_loop_retry_approval_from_chain(
            pending_result.id,
            db_path=db_path,
        )

    rejected_parent = tmp_path / "rejected-propose"
    rejected_parent.mkdir()
    rejected_result, _root, db_path = _retry_failure_result(rejected_parent)
    assert rejected_result.retry_approval is not None
    reject_latest_pending_coding_loop_retry_approval(
        rejected_result.id,
        rejected_reason="No retry.",
        db_path=db_path,
    )
    with pytest.raises(ValueError, match="no eligible propose_retry"):
        propose_next_coding_loop_retry_approval_from_chain(
            rejected_result.id,
            db_path=db_path,
        )

    stopped_parent = tmp_path / "stopped-propose"
    stopped_parent.mkdir()
    stopped_result, _root, db_path = _retry_failure_result(stopped_parent)
    assert stopped_result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        stopped_result.retry_approval.approval_id,
        approved_by="alec",
        db_path=db_path,
    )
    execute_approved_coding_loop_retry_approval(approved.approval_id, db_path=db_path)
    with pytest.raises(ValueError, match="no eligible propose_retry"):
        propose_next_coding_loop_retry_approval_from_chain(
            stopped_result.id,
            db_path=db_path,
        )

    unsafe_root = tmp_path / "unsafe-propose" / "repo"
    unsafe_db = tmp_path / "unsafe-propose" / "state" / "networking.db"
    unsafe_root.mkdir(parents=True)
    unsafe_result = run_one_step_coding_loop(
        "run rm -rf .",
        execution_root=unsafe_root,
        db_path=unsafe_db,
    )
    with pytest.raises(ValueError, match="no eligible propose_retry"):
        propose_next_coding_loop_retry_approval_from_chain(
            unsafe_result.id,
            db_path=unsafe_db,
        )

    deep_parent = tmp_path / "truncated-propose"
    deep_parent.mkdir()
    deep_result, _root, deep_db = _retry_failure_result(deep_parent)
    assert deep_result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        deep_result.retry_approval.approval_id,
        approved_by="alec",
        db_path=deep_db,
    )
    reviewed_failed_retry = replace(
        approved,
        retry_execution_run_id=deep_result.execution_run_id,
        retry_execution_status="exhausted",
        retry_execution_reason="Retryable execution failed until max_cycles was exhausted.",
        executed_at="2026-05-04T14:00:00Z",
    )
    store_coding_loop_retry_approval(reviewed_failed_retry, db_path=deep_db)
    create_coding_loop_retry_approval_from_review(
        reviewed_failed_retry.approval_id,
        db_path=deep_db,
    )
    with pytest.raises(ValueError, match="truncated"):
        propose_next_coding_loop_retry_approval_from_chain(
            deep_result.id,
            max_depth=1,
            db_path=deep_db,
        )

    with pytest.raises(ValueError, match="not found"):
        propose_next_coding_loop_retry_approval_from_chain(
            "coding-loop-result-missing",
            db_path=deep_db,
        )


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
