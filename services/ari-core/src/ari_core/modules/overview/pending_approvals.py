from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ari_core.core.paths import DB_PATH
from ari_core.modules.execution.coding_loop import list_coding_loop_retry_approvals


@dataclass(frozen=True, slots=True)
class PendingApprovalSummary:
    approval_id: str
    approval_type: str
    status: str
    source: str
    original_goal: str
    proposed_goal: str
    proposed_action_summary: str
    reason: str
    failed_verification_summary: str
    created_at: str
    linked_coding_loop_result_id: str | None
    linked_execution_run_id: str | None
    requires_user_authority: bool
    inspection_hint: str


@dataclass(frozen=True, slots=True)
class PendingApprovalsReadModel:
    generated_at: str
    total_pending_count: int
    approvals: tuple[PendingApprovalSummary, ...]
    unavailable_reason: str | None
    source_of_truth: str
    authority_warning: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_pending_approvals_read_model(
    *,
    db_path: Path = DB_PATH,
    limit: int = 20,
) -> PendingApprovalsReadModel:
    source_of_truth = "durable coding-loop retry approval registry"
    authority_warning = (
        "This read model is inspection-only. ACE may display pending approvals but "
        "must not approve, reject, execute, advance chains, or own approval state."
    )
    try:
        approvals = list_coding_loop_retry_approvals(limit=limit, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through tests via monkeypatch.
        return PendingApprovalsReadModel(
            generated_at=_now_iso(),
            total_pending_count=0,
            approvals=(),
            unavailable_reason=(
                f"Pending approvals are unavailable: {type(error).__name__}: {error}"
            ),
            source_of_truth=source_of_truth,
            authority_warning=authority_warning,
        )

    pending = tuple(
        _summarize_retry_approval(approval.to_dict())
        for approval in approvals
        if approval.approval_status == "pending"
    )
    return PendingApprovalsReadModel(
        generated_at=_now_iso(),
        total_pending_count=len(pending),
        approvals=pending,
        unavailable_reason=None,
        source_of_truth=source_of_truth,
        authority_warning=authority_warning,
    )


def _summarize_retry_approval(payload: dict[str, Any]) -> PendingApprovalSummary:
    approval_id = str(payload.get("approval_id") or "")
    action = payload.get("proposed_retry_action")
    return PendingApprovalSummary(
        approval_id=approval_id,
        approval_type="coding_loop_retry",
        status=str(payload.get("approval_status") or "pending"),
        source="coding_loop_retry_approval",
        original_goal=str(payload.get("original_goal") or ""),
        proposed_goal=str(payload.get("proposed_retry_goal") or ""),
        proposed_action_summary=_action_summary(
            str(payload.get("proposed_retry_action_description") or ""),
            action,
        ),
        reason=str(payload.get("reason") or ""),
        failed_verification_summary=str(payload.get("failed_verification_summary") or ""),
        created_at=str(payload.get("created_at") or ""),
        linked_coding_loop_result_id=_string_or_none(
            payload.get("source_coding_loop_result_id")
        ),
        linked_execution_run_id=_string_or_none(payload.get("source_execution_run_id")),
        requires_user_authority=bool(payload.get("retry_execution_requires_approval", True)),
        inspection_hint=f"api execution retry-approvals show --id {approval_id}",
    )


def _action_summary(description: str, action: object) -> str:
    if description:
        return description
    if isinstance(action, dict):
        action_type = str(action.get("type") or action.get("action_type") or "action")
        target = action.get("path") or action.get("target")
        if target is not None:
            return f"{action_type} {target}"
        return action_type
    return "No proposed action summary is available."


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
