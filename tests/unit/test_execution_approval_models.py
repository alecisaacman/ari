from __future__ import annotations

import pytest
from ari_core.modules.execution.models import ApprovalRequirement


def test_approval_requirement_defaults_to_pending_authority_state() -> None:
    approval = ApprovalRequirement()

    assert approval.approval_required is True
    assert approval.status == "pending"
    assert approval.approved_by is None
    assert approval.approved_at is None
    assert approval.rejected_reason is None
    assert approval.to_dict()["status"] == "pending"


def test_approval_requirement_not_required_state_serializes() -> None:
    approval = ApprovalRequirement.not_required(
        reason="Pure read-only preview.",
        authority_note="No verification command or mutation is present.",
    )

    assert approval.approval_required is False
    assert approval.status == "not_required"
    assert approval.to_dict() == {
        "approval_required": False,
        "status": "not_required",
        "reason": "Pure read-only preview.",
        "authority_note": "No verification command or mutation is present.",
        "approved_by": None,
        "approved_at": None,
        "rejected_reason": None,
    }


def test_approval_requirement_approved_state_is_explicit() -> None:
    approval = ApprovalRequirement.approved(
        approved_by="alec",
        approved_at="2026-04-24T12:00:00Z",
        reason="Alec approved safe verification.",
    )

    assert approval.status == "approved"
    assert approval.approved_by == "alec"
    assert approval.approved_at == "2026-04-24T12:00:00Z"
    assert approval.rejected_reason is None


def test_approval_requirement_rejected_state_is_explicit() -> None:
    approval = ApprovalRequirement.rejected(
        rejected_reason="Command is not worth running.",
        authority_note="Rejected by user authority.",
    )

    assert approval.status == "rejected"
    assert approval.approval_required is True
    assert approval.rejected_reason == "Command is not worth running."
    assert approval.authority_note == "Rejected by user authority."


def test_approval_requirement_rejects_inconsistent_states() -> None:
    with pytest.raises(ValueError, match="not_required"):
        ApprovalRequirement(approval_required=True, status="not_required")

    with pytest.raises(ValueError, match="approved_by"):
        ApprovalRequirement(status="approved")

    with pytest.raises(ValueError, match="rejected_reason"):
        ApprovalRequirement(status="rejected")

    with pytest.raises(ValueError, match="pending"):
        ApprovalRequirement(status="pending", approved_by="alec")
