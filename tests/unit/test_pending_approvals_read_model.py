from __future__ import annotations

import importlib
import json

from ari_core.modules.execution.coding_loop import CodingLoopRetryApproval
from ari_core.modules.execution.models import ApprovalRequirement


def test_pending_approvals_read_model_is_json_serializable(monkeypatch) -> None:
    pending_approvals = _pending_approvals_module()
    monkeypatch.setattr(
        pending_approvals,
        "list_coding_loop_retry_approvals",
        lambda *, limit, db_path: (_pending_retry_approval(),),
    )

    model = pending_approvals.get_pending_approvals_read_model()

    payload = model.to_dict()
    assert payload["total_pending_count"] == 1
    assert json.loads(json.dumps(payload))["approvals"][0]["approval_id"] == "approval-1"


def test_pending_approvals_read_model_includes_approval_summaries(monkeypatch) -> None:
    pending_approvals = _pending_approvals_module()
    monkeypatch.setattr(
        pending_approvals,
        "list_coding_loop_retry_approvals",
        lambda *, limit, db_path: (
            _pending_retry_approval(),
            _approved_retry_approval(),
        ),
    )

    payload = pending_approvals.get_pending_approvals_read_model().to_dict()

    assert payload["total_pending_count"] == 1
    approval = payload["approvals"][0]
    assert approval["approval_id"] == "approval-1"
    assert approval["approval_type"] == "coding_loop_retry"
    assert approval["status"] == "pending"
    assert approval["source"] == "coding_loop_retry_approval"
    assert approval["original_goal"] == "Fix a failing proof"
    assert approval["proposed_goal"] == "write file proof.txt with ready"
    assert approval["proposed_action_summary"] == "write_file proof.txt"
    assert approval["reason"] == "Verification failed; propose one retry."
    assert approval["failed_verification_summary"] == "proof.txt did not contain ready"
    assert approval["linked_coding_loop_result_id"] == "coding-loop-result-1"
    assert approval["linked_execution_run_id"] == "execution-run-1"
    assert approval["requires_user_authority"] is True
    assert approval["inspection_hint"] == "api execution retry-approvals show --id approval-1"


def test_pending_approvals_read_model_represents_unavailable_source(monkeypatch) -> None:
    pending_approvals = _pending_approvals_module()

    def raise_unavailable(*, limit, db_path):
        raise RuntimeError("store offline")

    monkeypatch.setattr(
        pending_approvals,
        "list_coding_loop_retry_approvals",
        raise_unavailable,
    )

    payload = pending_approvals.get_pending_approvals_read_model().to_dict()

    assert payload["total_pending_count"] == 0
    assert payload["approvals"] == ()
    assert "RuntimeError: store offline" in payload["unavailable_reason"]
    assert payload["source_of_truth"] == "durable coding-loop retry approval registry"


def test_pending_approvals_read_model_is_read_only(monkeypatch) -> None:
    pending_approvals = _pending_approvals_module()
    calls: list[tuple[int, object]] = []

    def list_only(*, limit, db_path):
        calls.append((limit, db_path))
        return (_pending_retry_approval(),)

    monkeypatch.setattr(
        pending_approvals,
        "list_coding_loop_retry_approvals",
        list_only,
    )

    payload = pending_approvals.get_pending_approvals_read_model().to_dict()

    assert calls
    assert "inspection-only" in payload["authority_warning"]
    assert "must not approve, reject, execute" in payload["authority_warning"]


def _pending_approvals_module():
    return importlib.import_module("ari_core.modules.overview.pending_approvals")


def _pending_retry_approval() -> CodingLoopRetryApproval:
    return CodingLoopRetryApproval(
        approval_id="approval-1",
        source_coding_loop_result_id="coding-loop-result-1",
        source_preview_id="preview-1",
        source_execution_run_id="execution-run-1",
        original_goal="Fix a failing proof",
        proposed_retry_goal="write file proof.txt with ready",
        proposed_retry_action={"type": "write_file", "path": "proof.txt", "content": "ready"},
        proposed_retry_action_description="write_file proof.txt",
        reason="Verification failed; propose one retry.",
        failed_verification_summary="proof.txt did not contain ready",
        approval=ApprovalRequirement.pending(reason="User authority required for retry."),
        approval_status="pending",
        retry_execution_requires_approval=True,
        proposed_action_requires_approval=False,
        created_at="2026-05-06T00:00:00Z",
    )


def _approved_retry_approval() -> CodingLoopRetryApproval:
    approval = _pending_retry_approval()
    return CodingLoopRetryApproval(
        approval_id="approval-2",
        source_coding_loop_result_id=approval.source_coding_loop_result_id,
        source_preview_id=approval.source_preview_id,
        source_execution_run_id=approval.source_execution_run_id,
        original_goal=approval.original_goal,
        proposed_retry_goal=approval.proposed_retry_goal,
        proposed_retry_action=approval.proposed_retry_action,
        proposed_retry_action_description=approval.proposed_retry_action_description,
        reason=approval.reason,
        failed_verification_summary=approval.failed_verification_summary,
        approval=ApprovalRequirement(
            approval_required=True,
            status="approved",
            reason="Approved for test.",
            approved_by="alec",
            approved_at="2026-05-06T00:01:00Z",
        ),
        approval_status="approved",
        retry_execution_requires_approval=True,
        proposed_action_requires_approval=False,
        created_at=approval.created_at,
    )
