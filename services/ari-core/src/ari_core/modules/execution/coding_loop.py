from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from ...core.paths import DB_PATH
from ..coordination.db import (
    get_coordination_entity,
    list_coordination_entities,
    put_coordination_entity,
)
from .controller import plan_execution_goal, run_execution_goal
from .models import (
    ApprovalRequirement,
    ExecutionGoal,
    FailureContext,
    PlannerResult,
    RepoContext,
    VerificationExpectation,
    VerificationExpectationType,
    WorkerAction,
    WorkerActionType,
    WorkerPlan,
    _now_iso,
)
from .planners import ExecutionPlanner

CodingLoopStatus = Literal[
    "success",
    "retryable_failure",
    "blocked",
    "unsafe",
    "ask_user",
    "requires_approval",
]

CodingLoopRetryExecutionReviewStatus = Literal[
    "not_executed",
    "stop",
    "propose_retry",
    "blocked",
    "unsafe",
    "ask_user",
]

CodingLoopContinuationStatus = Literal[
    "create_pending_approval",
    "not_executed",
    "stop",
    "blocked",
    "unsafe",
    "ask_user",
    "duplicate_exists",
]

CodingLoopChainAdvancementAction = Literal[
    "executed_approved_retry",
    "no_action",
    "rejected",
]

CodingLoopChainApprovalAction = Literal[
    "approved_latest",
    "rejected_latest",
]


@dataclass(frozen=True, slots=True)
class CodingLoopRequest:
    goal: str
    execution_root: str | None = None
    id: str = field(default_factory=lambda: f"coding-loop-request-{uuid4()}")
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodingLoopResult:
    id: str
    request: CodingLoopRequest
    status: CodingLoopStatus
    reason: str
    preview_id: str | None
    execution_run_id: str | None
    preview: dict[str, Any] | None
    execution_run: dict[str, Any] | None
    approval_required_reason: str | None
    retry_proposal: dict[str, Any] | None
    retry_approval: CodingLoopRetryApproval | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "request": self.request.to_dict(),
            "status": self.status,
            "reason": self.reason,
            "preview_id": self.preview_id,
            "execution_run_id": self.execution_run_id,
            "preview": self.preview,
            "execution_run": self.execution_run,
            "approval_required_reason": self.approval_required_reason,
            "retry_proposal": self.retry_proposal,
            "retry_approval": (
                None if self.retry_approval is None else self.retry_approval.to_dict()
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class CodingLoopRetryApproval:
    approval_id: str
    source_coding_loop_result_id: str
    source_preview_id: str | None
    source_execution_run_id: str | None
    original_goal: str
    proposed_retry_goal: str
    proposed_retry_action: dict[str, Any] | None
    proposed_retry_action_description: str
    reason: str
    failed_verification_summary: str
    approval: ApprovalRequirement
    approval_status: str
    retry_execution_requires_approval: bool
    proposed_action_requires_approval: bool
    created_at: str
    retry_execution_run_id: str | None = None
    retry_execution_status: str | None = None
    retry_execution_reason: str | None = None
    prior_retry_approval_id: str | None = None
    prior_retry_execution_run_id: str | None = None
    next_retry_approval_id: str | None = None
    updated_at: str | None = None
    executed_at: str | None = None
    rejected_by: str | None = None
    rejected_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "source_coding_loop_result_id": self.source_coding_loop_result_id,
            "source_preview_id": self.source_preview_id,
            "source_execution_run_id": self.source_execution_run_id,
            "original_goal": self.original_goal,
            "proposed_retry_goal": self.proposed_retry_goal,
            "proposed_retry_action": self.proposed_retry_action,
            "proposed_retry_action_description": self.proposed_retry_action_description,
            "reason": self.reason,
            "failed_verification_summary": self.failed_verification_summary,
            "approval": self.approval.to_dict(),
            "approval_status": self.approval_status,
            "retry_execution_requires_approval": self.retry_execution_requires_approval,
            "proposed_action_requires_approval": self.proposed_action_requires_approval,
            "retry_execution_run_id": self.retry_execution_run_id,
            "retry_execution_status": self.retry_execution_status,
            "retry_execution_reason": self.retry_execution_reason,
            "prior_retry_approval_id": self.prior_retry_approval_id,
            "prior_retry_execution_run_id": self.prior_retry_execution_run_id,
            "next_retry_approval_id": self.next_retry_approval_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "executed_at": self.executed_at,
            "rejected_by": self.rejected_by,
            "rejected_at": self.rejected_at,
        }


@dataclass(frozen=True, slots=True)
class CodingLoopRetryExecutionReview:
    approval_id: str
    status: CodingLoopRetryExecutionReviewStatus
    reason: str
    retry_execution_run_id: str | None
    retry_execution_status: str | None
    suggested_next_goal: str | None
    suggested_next_action: dict[str, Any] | None
    approval_required: bool | None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodingLoopContinuationDecision:
    approval_id: str
    eligible: bool
    status: CodingLoopContinuationStatus
    reason: str
    review_status: CodingLoopRetryExecutionReviewStatus | None
    retry_execution_run_id: str | None
    next_retry_approval_id: str | None
    suggested_next_goal: str | None
    suggested_next_action: dict[str, Any] | None
    approval_required: bool | None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodingLoopChainAdvancement:
    root_coding_loop_result_id: str
    prior_terminal_status: str
    action_taken: CodingLoopChainAdvancementAction
    reason: str
    executed_retry_approval_id: str | None
    retry_execution_run_id: str | None
    refreshed_terminal_status: str | None
    refreshed_chain: dict[str, Any] | None
    stop_reason: str | None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodingLoopChainApprovalMutation:
    root_coding_loop_result_id: str
    action_taken: CodingLoopChainApprovalAction
    reason: str
    updated_retry_approval: CodingLoopRetryApproval
    refreshed_chain: dict[str, Any] | None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "root_coding_loop_result_id": self.root_coding_loop_result_id,
            "action_taken": self.action_taken,
            "reason": self.reason,
            "updated_retry_approval": self.updated_retry_approval.to_dict(),
            "refreshed_chain": self.refreshed_chain,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class CodingLoopChainNextApprovalProposal:
    root_coding_loop_result_id: str
    reason: str
    new_retry_approval: CodingLoopRetryApproval
    refreshed_chain: dict[str, Any] | None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return {
            "root_coding_loop_result_id": self.root_coding_loop_result_id,
            "reason": self.reason,
            "new_retry_approval": self.new_retry_approval.to_dict(),
            "refreshed_chain": self.refreshed_chain,
            "created_at": self.created_at,
        }


def run_one_step_coding_loop(
    request: CodingLoopRequest | str,
    *,
    execution_root: Path | str | None = None,
    db_path: Path = DB_PATH,
    planner: ExecutionPlanner | None = None,
    planner_mode: str | None = None,
    planner_completion_fn: Any | None = None,
) -> CodingLoopResult:
    loop_request = _coerce_request(request, execution_root)
    created_at = _now_iso()
    goal = ExecutionGoal(objective=loop_request.goal, max_cycles=1)
    root = execution_root or loop_request.execution_root

    preview = plan_execution_goal(
        goal,
        execution_root=root,
        db_path=db_path,
        planner=planner,
        planner_mode=planner_mode,
        planner_completion_fn=planner_completion_fn,
    )
    preview_id = _string_or_none(preview.get("id"))
    approval_required_reason = _approval_required_reason(preview)
    if approval_required_reason is not None:
        return _result(
            loop_request,
            "requires_approval",
            approval_required_reason,
            preview_id=preview_id,
            preview=preview,
            approval_required_reason=approval_required_reason,
            created_at=created_at,
            db_path=db_path,
        )

    preview_block = _preview_block_reason(preview)
    if preview_block is not None:
        return _result(
            loop_request,
            _classify_block(preview_block),
            preview_block,
            preview_id=preview_id,
            preview=preview,
            created_at=created_at,
            db_path=db_path,
        )

    plan = _plan_from_preview(preview)
    if isinstance(plan, str):
        return _result(
            loop_request,
            _classify_block(plan),
            plan,
            preview_id=preview_id,
            preview=preview,
            created_at=created_at,
            db_path=db_path,
        )

    execution_run = run_execution_goal(
        goal,
        execution_root=root,
        db_path=db_path,
        planner=_FrozenPlanPlanner(plan, preview),
    )
    execution_run_payload = execution_run.to_dict()
    status, reason = _classify_execution_run(execution_run_payload)
    retry_proposal = (
        _retry_proposal(execution_run_payload)
        if status == "retryable_failure"
        else None
    )
    return _result(
        loop_request,
        status,
        reason,
        preview_id=preview_id,
        execution_run_id=execution_run.id,
        preview=preview,
        execution_run=execution_run_payload,
        retry_proposal=retry_proposal,
        created_at=created_at,
        db_path=db_path,
    )


def approve_coding_loop_retry_approval(
    retry_approval: CodingLoopRetryApproval,
    *,
    approval_id: str,
    approved_by: str,
    approved_at: str | None = None,
) -> CodingLoopRetryApproval:
    _validate_retry_approval_mutation(retry_approval, approval_id)
    approval = ApprovalRequirement.approved(
        approved_by=approved_by,
        approved_at=approved_at,
        reason="Coding-loop retry proposal approved.",
        authority_note=(
            "Approval records authority only; it does not execute the retry proposal."
        ),
    )
    return replace(
        retry_approval,
        approval=approval,
        approval_status=approval.status,
        updated_at=approval.approved_at,
    )


def reject_coding_loop_retry_approval(
    retry_approval: CodingLoopRetryApproval,
    *,
    approval_id: str,
    rejected_reason: str,
    rejected_by: str | None = None,
    rejected_at: str | None = None,
) -> CodingLoopRetryApproval:
    _validate_retry_approval_mutation(retry_approval, approval_id)
    if not rejected_reason.strip():
        raise ValueError("rejected_reason is required.")
    rejection_time = rejected_at or _now_iso()
    approval = ApprovalRequirement.rejected(
        rejected_reason=rejected_reason,
        reason="Coding-loop retry proposal rejected.",
        authority_note=(
            "Rejection records authority only; it does not execute the retry proposal."
        ),
    )
    return replace(
        retry_approval,
        approval=approval,
        approval_status=approval.status,
        updated_at=rejection_time,
        rejected_by=rejected_by,
        rejected_at=rejection_time,
    )


def _validate_retry_approval_mutation(
    retry_approval: CodingLoopRetryApproval,
    approval_id: str,
) -> None:
    if retry_approval.approval_id != approval_id:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")
    if retry_approval.approval.status != "pending":
        raise ValueError(
            "Coding-loop retry approval is already terminal: "
            f"{retry_approval.approval.status}."
        )


def store_coding_loop_retry_approval(
    retry_approval: CodingLoopRetryApproval,
    *,
    db_path: Path = DB_PATH,
) -> CodingLoopRetryApproval:
    row = put_coordination_entity(
        "runtime_coding_loop_retry_approval",
        _retry_approval_record(retry_approval),
        db_path=db_path,
    )
    return _retry_approval_from_row(row)


def get_coding_loop_retry_approval(
    approval_id: str,
    *,
    db_path: Path = DB_PATH,
) -> CodingLoopRetryApproval | None:
    row = get_coordination_entity(
        "runtime_coding_loop_retry_approval",
        approval_id,
        db_path=db_path,
    )
    if row is None:
        return None
    return _retry_approval_from_row(row)


def list_coding_loop_retry_approvals(
    *,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> list[CodingLoopRetryApproval]:
    rows = list_coordination_entities(
        "runtime_coding_loop_retry_approval",
        limit=limit,
        db_path=db_path,
    )
    return [_retry_approval_from_row(row) for row in rows]


def approve_stored_coding_loop_retry_approval(
    approval_id: str,
    *,
    approved_by: str,
    approved_at: str | None = None,
    db_path: Path = DB_PATH,
) -> CodingLoopRetryApproval:
    current = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if current is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")
    approved = approve_coding_loop_retry_approval(
        current,
        approval_id=approval_id,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    stored = store_coding_loop_retry_approval(approved, db_path=db_path)
    refresh_coding_loop_result_links(stored.source_coding_loop_result_id, db_path=db_path)
    return stored


def approve_latest_pending_coding_loop_retry_approval(
    result_id: str,
    *,
    approved_by: str,
    approved_at: str | None = None,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> CodingLoopChainApprovalMutation:
    approval_id = _latest_pending_chain_approval_id(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    approval = approve_stored_coding_loop_retry_approval(
        approval_id,
        approved_by=approved_by,
        approved_at=approved_at,
        db_path=db_path,
    )
    return _chain_approval_mutation_result(
        result_id,
        "approved_latest",
        "Approved the latest pending retry approval in the chain.",
        approval,
        max_depth=max_depth,
        db_path=db_path,
    )


def reject_latest_pending_coding_loop_retry_approval(
    result_id: str,
    *,
    rejected_reason: str,
    rejected_by: str | None = None,
    rejected_at: str | None = None,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> CodingLoopChainApprovalMutation:
    approval_id = _latest_pending_chain_approval_id(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    approval = reject_stored_coding_loop_retry_approval(
        approval_id,
        rejected_reason=rejected_reason,
        rejected_by=rejected_by,
        rejected_at=rejected_at,
        db_path=db_path,
    )
    return _chain_approval_mutation_result(
        result_id,
        "rejected_latest",
        "Rejected the latest pending retry approval in the chain.",
        approval,
        max_depth=max_depth,
        db_path=db_path,
    )


def propose_next_coding_loop_retry_approval_from_chain(
    result_id: str,
    *,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> CodingLoopChainNextApprovalProposal:
    approval_id = _latest_eligible_propose_retry_approval_id(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    approval = create_coding_loop_retry_approval_from_review(
        approval_id,
        db_path=db_path,
    )
    from .inspection import inspect_coding_loop_chain

    return CodingLoopChainNextApprovalProposal(
        root_coding_loop_result_id=result_id,
        reason="Created the next pending retry approval from an eligible chain review.",
        new_retry_approval=approval,
        refreshed_chain=inspect_coding_loop_chain(
            result_id,
            max_depth=max_depth,
            db_path=db_path,
        ),
    )


def execute_approved_coding_loop_retry_approval(
    approval_id: str,
    *,
    db_path: Path = DB_PATH,
) -> tuple[CodingLoopRetryApproval, dict[str, Any]]:
    current = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if current is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")
    _validate_retry_execution_boundary(current)

    source_run = _source_execution_run(current, db_path=db_path)
    retry_goal = ExecutionGoal(
        objective=current.proposed_retry_goal,
        max_cycles=1,
        metadata={
            "source": "coding_loop_retry_approval",
            "approval_id": current.approval_id,
            "source_execution_run_id": current.source_execution_run_id,
        },
    )
    execution_run = run_execution_goal(
        retry_goal,
        execution_root=source_run["repo_root"],
        db_path=db_path,
    )
    execution_payload = execution_run.to_dict()
    executed_at = _now_iso()
    updated = replace(
        current,
        retry_execution_run_id=execution_run.id,
        retry_execution_status=str(execution_payload.get("status") or ""),
        retry_execution_reason=str(execution_payload.get("reason") or ""),
        executed_at=executed_at,
        updated_at=executed_at,
    )
    stored = store_coding_loop_retry_approval(updated, db_path=db_path)
    refresh_coding_loop_result_links(stored.source_coding_loop_result_id, db_path=db_path)
    return stored, execution_payload


def advance_coding_loop_retry_chain(
    result_id: str,
    *,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> CodingLoopChainAdvancement:
    from .inspection import inspect_coding_loop_chain

    prior_chain = inspect_coding_loop_chain(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    if prior_chain is None:
        raise ValueError(f"Coding-loop result {result_id} not found.")

    prior_status = str(prior_chain.get("terminal_status") or "unknown/incomplete")
    if prior_chain.get("truncated") is True:
        return _chain_advancement_result(
            result_id,
            prior_status,
            "rejected",
            "Coding-loop retry chain traversal was truncated.",
            refreshed_chain=prior_chain,
        )
    if prior_chain.get("cycle_detected") is True:
        return _chain_advancement_result(
            result_id,
            prior_status,
            "rejected",
            "Coding-loop retry chain traversal detected a cycle.",
            refreshed_chain=prior_chain,
        )
    if prior_status != "executable_approved_retry_available":
        return _chain_advancement_result(
            result_id,
            prior_status,
            "no_action",
            f"Coding-loop retry chain is not executable: {prior_status}.",
            refreshed_chain=prior_chain,
        )

    approval_id = _string_or_none(prior_chain.get("latest_retry_approval_id"))
    if approval_id is None:
        return _chain_advancement_result(
            result_id,
            prior_status,
            "rejected",
            "Coding-loop retry chain has no latest retry approval to execute.",
            refreshed_chain=prior_chain,
        )

    approval, execution_run = execute_approved_coding_loop_retry_approval(
        approval_id,
        db_path=db_path,
    )
    refreshed_chain = inspect_coding_loop_chain(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    refreshed_status = (
        None
        if refreshed_chain is None
        else _string_or_none(refreshed_chain.get("terminal_status"))
    )
    return CodingLoopChainAdvancement(
        root_coding_loop_result_id=result_id,
        prior_terminal_status=prior_status,
        action_taken="executed_approved_retry",
        reason="Executed one approved retry approval and stopped.",
        executed_retry_approval_id=approval.approval_id,
        retry_execution_run_id=_string_or_none(execution_run.get("id")),
        refreshed_terminal_status=refreshed_status,
        refreshed_chain=refreshed_chain,
        stop_reason="One approved retry was executed; chain advancement stops here.",
    )


def review_coding_loop_retry_execution(
    approval_id: str,
    *,
    db_path: Path = DB_PATH,
) -> CodingLoopRetryExecutionReview:
    approval = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if approval is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")
    if approval.retry_execution_run_id is None:
        return CodingLoopRetryExecutionReview(
            approval_id=approval.approval_id,
            status="not_executed",
            reason="Retry approval has not executed.",
            retry_execution_run_id=None,
            retry_execution_status=approval.retry_execution_status,
            suggested_next_goal=None,
            suggested_next_action=None,
            approval_required=None,
        )

    from .inspection import get_execution_run

    execution_run = get_execution_run(approval.retry_execution_run_id, db_path=db_path)
    if execution_run is None:
        return CodingLoopRetryExecutionReview(
            approval_id=approval.approval_id,
            status="blocked",
            reason=(
                "Retry execution run is referenced by approval but was not found: "
                f"{approval.retry_execution_run_id}."
            ),
            retry_execution_run_id=approval.retry_execution_run_id,
            retry_execution_status=approval.retry_execution_status,
            suggested_next_goal=None,
            suggested_next_action=None,
            approval_required=None,
        )

    loop_status, reason = _classify_execution_run(execution_run)
    if loop_status == "success":
        return CodingLoopRetryExecutionReview(
            approval_id=approval.approval_id,
            status="stop",
            reason=reason,
            retry_execution_run_id=approval.retry_execution_run_id,
            retry_execution_status=approval.retry_execution_status,
            suggested_next_goal=None,
            suggested_next_action=None,
            approval_required=False,
        )
    if loop_status == "unsafe":
        return CodingLoopRetryExecutionReview(
            approval_id=approval.approval_id,
            status="unsafe",
            reason=reason,
            retry_execution_run_id=approval.retry_execution_run_id,
            retry_execution_status=approval.retry_execution_status,
            suggested_next_goal=None,
            suggested_next_action=None,
            approval_required=None,
        )
    if loop_status == "retryable_failure":
        proposal = _retry_proposal(execution_run)
        if proposal is None:
            return CodingLoopRetryExecutionReview(
                approval_id=approval.approval_id,
                status="ask_user",
                reason=(
                    "Retry execution failed, but ARI could not derive a bounded "
                    "follow-up proposal."
                ),
                retry_execution_run_id=approval.retry_execution_run_id,
                retry_execution_status=approval.retry_execution_status,
                suggested_next_goal=None,
                suggested_next_action=None,
                approval_required=True,
            )
        return CodingLoopRetryExecutionReview(
            approval_id=approval.approval_id,
            status="propose_retry",
            reason="Retry execution failed verification; propose a new approval item only.",
            retry_execution_run_id=approval.retry_execution_run_id,
            retry_execution_status=approval.retry_execution_status,
            suggested_next_goal=_string_or_none(proposal.get("suggested_next_goal")),
            suggested_next_action=(
                proposal.get("suggested_next_action")
                if isinstance(proposal.get("suggested_next_action"), dict)
                else None
            ),
            approval_required=True,
        )

    review_status: CodingLoopRetryExecutionReviewStatus = (
        "ask_user" if loop_status == "ask_user" else "blocked"
    )
    return CodingLoopRetryExecutionReview(
        approval_id=approval.approval_id,
        status=review_status,
        reason=reason,
        retry_execution_run_id=approval.retry_execution_run_id,
        retry_execution_status=approval.retry_execution_status,
        suggested_next_goal=None,
        suggested_next_action=None,
        approval_required=None,
    )


def create_coding_loop_retry_approval_from_review(
    approval_id: str,
    *,
    db_path: Path = DB_PATH,
) -> CodingLoopRetryApproval:
    approval = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if approval is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")

    continuation = decide_coding_loop_retry_continuation(
        approval_id,
        db_path=db_path,
    )
    if continuation.status == "not_executed":
        raise ValueError("Coding-loop retry approval has not executed.")
    if continuation.status == "duplicate_exists":
        raise ValueError(
            "Coding-loop retry approval review already produced a next approval: "
            f"{continuation.next_retry_approval_id}."
        )
    if not continuation.eligible:
        raise ValueError(
            "Coding-loop retry execution review is not propose_retry: "
            f"{continuation.review_status or continuation.status}."
        )

    review = review_coding_loop_retry_execution(approval_id, db_path=db_path)
    if not continuation.suggested_next_goal or continuation.suggested_next_action is None:
        raise ValueError("Coding-loop retry execution review has no next retry proposal.")

    created_at = _now_iso()
    next_approval = CodingLoopRetryApproval(
        approval_id=f"coding-loop-retry-approval-{uuid4()}",
        source_coding_loop_result_id=approval.source_coding_loop_result_id,
        source_preview_id=approval.source_preview_id,
        source_execution_run_id=approval.retry_execution_run_id,
        original_goal=approval.original_goal,
        proposed_retry_goal=continuation.suggested_next_goal,
        proposed_retry_action=continuation.suggested_next_action,
        proposed_retry_action_description=_describe_retry_action(
            continuation.suggested_next_action
        ),
        reason=review.reason,
        failed_verification_summary=_review_failure_summary(approval, review),
        approval=ApprovalRequirement.pending(
            reason="Approval is required before executing a follow-up retry proposal.",
            authority_note=(
                "ARI produced this proposal from a post-run retry review; "
                "the follow-up retry has not been executed."
            ),
        ),
        approval_status="pending",
        retry_execution_requires_approval=True,
        proposed_action_requires_approval=bool(continuation.approval_required),
        created_at=created_at,
        prior_retry_approval_id=approval.approval_id,
        prior_retry_execution_run_id=approval.retry_execution_run_id,
    )
    stored_next = store_coding_loop_retry_approval(next_approval, db_path=db_path)
    updated_prior = replace(
        approval,
        next_retry_approval_id=stored_next.approval_id,
        updated_at=created_at,
    )
    store_coding_loop_retry_approval(updated_prior, db_path=db_path)
    refresh_coding_loop_result_links(approval.source_coding_loop_result_id, db_path=db_path)
    return stored_next


def decide_coding_loop_retry_continuation(
    approval_id: str,
    *,
    db_path: Path = DB_PATH,
) -> CodingLoopContinuationDecision:
    approval = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if approval is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")

    if approval.next_retry_approval_id is not None:
        return CodingLoopContinuationDecision(
            approval_id=approval.approval_id,
            eligible=False,
            status="duplicate_exists",
            reason=(
                "This retry execution review already produced a follow-up approval: "
                f"{approval.next_retry_approval_id}."
            ),
            review_status=None,
            retry_execution_run_id=approval.retry_execution_run_id,
            next_retry_approval_id=approval.next_retry_approval_id,
            suggested_next_goal=None,
            suggested_next_action=None,
            approval_required=None,
        )

    review = review_coding_loop_retry_execution(approval_id, db_path=db_path)
    if review.status == "propose_retry":
        if review.suggested_next_goal and review.suggested_next_action is not None:
            return CodingLoopContinuationDecision(
                approval_id=approval.approval_id,
                eligible=True,
                status="create_pending_approval",
                reason="Review is eligible to create one pending follow-up approval.",
                review_status=review.status,
                retry_execution_run_id=review.retry_execution_run_id,
                next_retry_approval_id=None,
                suggested_next_goal=review.suggested_next_goal,
                suggested_next_action=review.suggested_next_action,
                approval_required=review.approval_required,
            )
        return CodingLoopContinuationDecision(
            approval_id=approval.approval_id,
            eligible=False,
            status="ask_user",
            reason="Review proposed a retry but did not include a bounded next action.",
            review_status=review.status,
            retry_execution_run_id=review.retry_execution_run_id,
            next_retry_approval_id=None,
            suggested_next_goal=None,
            suggested_next_action=None,
            approval_required=True,
        )

    status = _continuation_status_from_review(review.status)
    return CodingLoopContinuationDecision(
        approval_id=approval.approval_id,
        eligible=False,
        status=status,
        reason=review.reason,
        review_status=review.status,
        retry_execution_run_id=review.retry_execution_run_id,
        next_retry_approval_id=None,
        suggested_next_goal=review.suggested_next_goal,
        suggested_next_action=review.suggested_next_action,
        approval_required=review.approval_required,
    )


def _continuation_status_from_review(
    status: CodingLoopRetryExecutionReviewStatus,
) -> CodingLoopContinuationStatus:
    if status in {"not_executed", "stop", "blocked", "unsafe", "ask_user"}:
        return status
    return "ask_user"


def _chain_advancement_result(
    result_id: str,
    prior_status: str,
    action_taken: CodingLoopChainAdvancementAction,
    reason: str,
    *,
    refreshed_chain: dict[str, Any] | None,
) -> CodingLoopChainAdvancement:
    refreshed_status = (
        None
        if refreshed_chain is None
        else _string_or_none(refreshed_chain.get("terminal_status"))
    )
    return CodingLoopChainAdvancement(
        root_coding_loop_result_id=result_id,
        prior_terminal_status=prior_status,
        action_taken=action_taken,
        reason=reason,
        executed_retry_approval_id=None,
        retry_execution_run_id=None,
        refreshed_terminal_status=refreshed_status,
        refreshed_chain=refreshed_chain,
        stop_reason=reason,
    )


def _latest_pending_chain_approval_id(
    result_id: str,
    *,
    max_depth: int,
    db_path: Path,
) -> str:
    from .inspection import inspect_coding_loop_chain

    chain = inspect_coding_loop_chain(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    if chain is None:
        raise ValueError(f"Coding-loop result {result_id} not found.")
    if chain.get("truncated") is True:
        raise ValueError("Coding-loop retry chain traversal was truncated.")
    if chain.get("cycle_detected") is True:
        raise ValueError("Coding-loop retry chain traversal detected a cycle.")
    if chain.get("terminal_status") != "pending_approval":
        raise ValueError(
            "Coding-loop retry chain has no pending retry approval: "
            f"{chain.get('terminal_status')}."
        )

    latest_approval_id = _string_or_none(chain.get("latest_retry_approval_id"))
    if latest_approval_id is None:
        raise ValueError("Coding-loop retry chain has no pending retry approval.")

    approvals = chain.get("retry_approvals")
    latest = approvals[-1] if isinstance(approvals, list) and approvals else None
    if not isinstance(latest, dict) or latest.get("approval_status") != "pending":
        raise ValueError("Coding-loop retry chain has no pending retry approval.")
    if latest.get("retry_execution_run_id") is not None:
        raise ValueError("Coding-loop retry chain pending approval already executed.")
    return latest_approval_id


def _latest_eligible_propose_retry_approval_id(
    result_id: str,
    *,
    max_depth: int,
    db_path: Path,
) -> str:
    from .inspection import inspect_coding_loop_chain

    chain = inspect_coding_loop_chain(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    if chain is None:
        raise ValueError(f"Coding-loop result {result_id} not found.")
    if chain.get("truncated") is True:
        raise ValueError("Coding-loop retry chain traversal was truncated.")
    if chain.get("cycle_detected") is True:
        raise ValueError("Coding-loop retry chain traversal detected a cycle.")

    approvals = chain.get("retry_approvals")
    latest = approvals[-1] if isinstance(approvals, list) and approvals else None
    if not isinstance(latest, dict):
        raise ValueError(
            "Coding-loop retry chain has no eligible propose_retry review: "
            f"{chain.get('terminal_status')}."
        )
    continuation = latest.get("continuation")
    if not isinstance(continuation, dict):
        raise ValueError("Coding-loop retry chain has no inspectable continuation.")
    if continuation.get("status") != "create_pending_approval":
        duplicate = _first_duplicate_continuation(approvals)
        if duplicate is not None:
            raise ValueError(
                "Coding-loop retry approval review already produced a next approval: "
                f"{duplicate.get('next_retry_approval_id')}."
            )
        raise ValueError(
            "Coding-loop retry chain has no eligible propose_retry review: "
            f"{continuation.get('review_status') or chain.get('terminal_status')}."
        )

    approval_id = _string_or_none(latest.get("approval_id"))
    if approval_id is None:
        raise ValueError("Coding-loop retry chain has no latest retry approval.")
    return approval_id


def _first_duplicate_continuation(approvals: object) -> dict[str, Any] | None:
    if not isinstance(approvals, list):
        return None
    for approval in reversed(approvals):
        if not isinstance(approval, dict):
            continue
        continuation = approval.get("continuation")
        if isinstance(continuation, dict) and continuation.get("status") == "duplicate_exists":
            return continuation
    return None


def _chain_approval_mutation_result(
    result_id: str,
    action_taken: CodingLoopChainApprovalAction,
    reason: str,
    approval: CodingLoopRetryApproval,
    *,
    max_depth: int,
    db_path: Path,
) -> CodingLoopChainApprovalMutation:
    from .inspection import inspect_coding_loop_chain

    return CodingLoopChainApprovalMutation(
        root_coding_loop_result_id=result_id,
        action_taken=action_taken,
        reason=reason,
        updated_retry_approval=approval,
        refreshed_chain=inspect_coding_loop_chain(
            result_id,
            max_depth=max_depth,
            db_path=db_path,
        ),
    )


def refresh_coding_loop_result_links(
    result_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    from .inspection import get_coding_loop_result

    persisted = get_coding_loop_result(result_id, db_path=db_path)
    if persisted is None:
        return None
    retry_approval_id = _string_or_none(persisted.get("retry_approval_id"))
    if retry_approval_id is None:
        return persisted
    retry_approval = get_coding_loop_retry_approval(retry_approval_id, db_path=db_path)
    if retry_approval is None:
        return persisted
    return _persist_coding_loop_result_record(
        _coding_loop_result_record_from_payload(
            persisted,
            retry_approval=retry_approval,
            db_path=db_path,
        ),
        db_path=db_path,
    )


def _review_failure_summary(
    approval: CodingLoopRetryApproval,
    review: CodingLoopRetryExecutionReview,
) -> str:
    parts = [
        review.reason,
        f"Prior retry execution status: {review.retry_execution_status}.",
    ]
    if approval.retry_execution_reason:
        parts.append(f"Prior retry execution reason: {approval.retry_execution_reason}")
    return " ".join(parts)


def _validate_retry_execution_boundary(approval: CodingLoopRetryApproval) -> None:
    if approval.approval.status != "approved":
        raise ValueError(
            "Coding-loop retry approval must be approved before execution; "
            f"current status is {approval.approval.status}."
        )
    if approval.retry_execution_run_id is not None or approval.executed_at is not None:
        raise ValueError("Coding-loop retry approval has already been executed.")
    if not approval.proposed_retry_goal.strip():
        raise ValueError("Coding-loop retry approval does not include a retry goal.")


def _source_execution_run(
    approval: CodingLoopRetryApproval,
    *,
    db_path: Path,
) -> dict[str, Any]:
    if approval.source_execution_run_id is None:
        raise ValueError("Coding-loop retry approval has no source execution run.")
    row = get_coordination_entity(
        "runtime_execution_run",
        approval.source_execution_run_id,
        db_path=db_path,
    )
    if row is None:
        raise ValueError(
            "Source execution run not found for coding-loop retry approval: "
            f"{approval.source_execution_run_id}."
        )
    return {
        "id": row["id"],
        "repo_root": row["repo_root"],
    }


def reject_stored_coding_loop_retry_approval(
    approval_id: str,
    *,
    rejected_reason: str,
    rejected_by: str | None = None,
    rejected_at: str | None = None,
    db_path: Path = DB_PATH,
) -> CodingLoopRetryApproval:
    current = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if current is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} not found.")
    rejected = reject_coding_loop_retry_approval(
        current,
        approval_id=approval_id,
        rejected_reason=rejected_reason,
        rejected_by=rejected_by,
        rejected_at=rejected_at,
    )
    stored = store_coding_loop_retry_approval(rejected, db_path=db_path)
    refresh_coding_loop_result_links(stored.source_coding_loop_result_id, db_path=db_path)
    return stored


def _retry_approval_record(approval: CodingLoopRetryApproval) -> dict[str, object]:
    return {
        "approval_id": approval.approval_id,
        "source_coding_loop_result_id": approval.source_coding_loop_result_id,
        "source_preview_id": approval.source_preview_id,
        "source_execution_run_id": approval.source_execution_run_id,
        "original_goal": approval.original_goal,
        "proposed_retry_goal": approval.proposed_retry_goal,
        "proposed_retry_action_json": json.dumps(approval.proposed_retry_action),
        "proposed_retry_action_description": approval.proposed_retry_action_description,
        "reason": approval.reason,
        "failed_verification_summary": approval.failed_verification_summary,
        "approval_status": approval.approval_status,
        "approval_json": json.dumps(approval.approval.to_dict()),
        "retry_execution_requires_approval": int(approval.retry_execution_requires_approval),
        "proposed_action_requires_approval": int(approval.proposed_action_requires_approval),
        "retry_execution_run_id": approval.retry_execution_run_id,
        "retry_execution_status": approval.retry_execution_status,
        "retry_execution_reason": approval.retry_execution_reason,
        "prior_retry_approval_id": approval.prior_retry_approval_id,
        "prior_retry_execution_run_id": approval.prior_retry_execution_run_id,
        "next_retry_approval_id": approval.next_retry_approval_id,
        "created_at": approval.created_at,
        "updated_at": approval.updated_at,
        "executed_at": approval.executed_at,
        "rejected_by": approval.rejected_by,
        "rejected_at": approval.rejected_at,
    }


def _retry_approval_from_row(row: Any) -> CodingLoopRetryApproval:
    approval_payload = _json_object(row["approval_json"])
    proposed_action = _json_value(row["proposed_retry_action_json"])
    return CodingLoopRetryApproval(
        approval_id=str(row["approval_id"]),
        source_coding_loop_result_id=str(row["source_coding_loop_result_id"]),
        source_preview_id=_string_or_none(row["source_preview_id"]),
        source_execution_run_id=_string_or_none(row["source_execution_run_id"]),
        original_goal=str(row["original_goal"]),
        proposed_retry_goal=str(row["proposed_retry_goal"]),
        proposed_retry_action=proposed_action if isinstance(proposed_action, dict) else None,
        proposed_retry_action_description=str(row["proposed_retry_action_description"]),
        reason=str(row["reason"]),
        failed_verification_summary=str(row["failed_verification_summary"]),
        approval=ApprovalRequirement(**approval_payload),
        approval_status=str(row["approval_status"]),
        retry_execution_requires_approval=bool(row["retry_execution_requires_approval"]),
        proposed_action_requires_approval=bool(row["proposed_action_requires_approval"]),
        created_at=str(row["created_at"]),
        retry_execution_run_id=_string_or_none(row["retry_execution_run_id"]),
        retry_execution_status=_string_or_none(row["retry_execution_status"]),
        retry_execution_reason=_string_or_none(row["retry_execution_reason"]),
        prior_retry_approval_id=_string_or_none(row["prior_retry_approval_id"]),
        prior_retry_execution_run_id=_string_or_none(row["prior_retry_execution_run_id"]),
        next_retry_approval_id=_string_or_none(row["next_retry_approval_id"]),
        updated_at=_string_or_none(row["updated_at"]),
        executed_at=_string_or_none(row["executed_at"]),
        rejected_by=_string_or_none(row["rejected_by"]),
        rejected_at=_string_or_none(row["rejected_at"]),
    )


def _json_value(raw: object) -> object:
    if not isinstance(raw, str):
        return None
    return json.loads(raw or "null")


def _json_object(raw: object) -> dict[str, Any]:
    decoded = _json_value(raw)
    return decoded if isinstance(decoded, dict) else {}


class _FrozenPlanPlanner:
    planner_name = "coding_loop_preview"

    def __init__(self, plan: WorkerPlan, preview: dict[str, Any]) -> None:
        self.selected_plan = plan
        self.preview = preview

    def plan(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: FailureContext | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        del goal, repo_context, failure_context, memory_context
        decision = self.preview.get("decision")
        reason = self.preview.get("reason")
        confidence = 0.0
        if isinstance(decision, dict):
            confidence = _float_or_zero(decision.get("confidence"))
        return PlannerResult(
            status="act",
            reason=str(reason or "Execute the single validated preview action."),
            confidence=confidence,
            planner_name=self.planner_name,
            plan=self.selected_plan,
        )


def _coerce_request(
    request: CodingLoopRequest | str,
    execution_root: Path | str | None,
) -> CodingLoopRequest:
    if isinstance(request, CodingLoopRequest):
        return request
    return CodingLoopRequest(
        goal=request,
        execution_root=None if execution_root is None else str(execution_root),
    )


def _preview_block_reason(preview: dict[str, Any]) -> str | None:
    status = str(preview.get("status") or "")
    if status != "planned":
        return str(preview.get("reason") or "Planner did not produce a runnable action.")
    decision = preview.get("decision")
    if not isinstance(decision, dict):
        return "Planner preview did not include an inspectable decision."
    plan = decision.get("plan")
    if not isinstance(plan, dict):
        return "Planner preview did not include a bounded action plan."
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        return "Planner preview did not include a candidate action."
    if len(actions) != 1:
        return "One-step coding loop requires exactly one candidate action."
    return None


def _approval_required_reason(preview: dict[str, Any]) -> str | None:
    action = _single_preview_action(preview)
    if action is None:
        return None
    if not bool(action.get("requires_approval")):
        return None
    reason = str(
        action.get("reason")
        or preview.get("validation_error")
        or preview.get("reason")
        or "Action requires approval before execution."
    )
    return f"Approval required before one-step execution: {reason}"


def _single_preview_action(preview: dict[str, Any]) -> dict[str, Any] | None:
    decision = preview.get("decision")
    if not isinstance(decision, dict):
        return None
    plan = decision.get("plan")
    if not isinstance(plan, dict):
        return None
    actions = plan.get("actions")
    if not isinstance(actions, list) or len(actions) != 1:
        return None
    action = actions[0]
    return action if isinstance(action, dict) else None


def _plan_from_preview(preview: dict[str, Any]) -> WorkerPlan | str:
    decision = cast(dict[str, Any], preview["decision"])
    raw_plan = decision.get("plan")
    if not isinstance(raw_plan, dict):
        return "Planner preview did not include a bounded action plan."

    raw_actions = raw_plan.get("actions")
    if not isinstance(raw_actions, list) or len(raw_actions) != 1:
        return "One-step coding loop requires exactly one candidate action."

    action = _action_from_payload(raw_actions[0])
    if isinstance(action, str):
        return action

    raw_verification = raw_plan.get("verification")
    verification = _verification_from_payload(raw_verification)
    if isinstance(verification, str):
        return verification

    return WorkerPlan(
        actions=(action,),
        verification=tuple(verification),
        reason=str(raw_plan.get("reason") or preview.get("reason") or "One-step preview plan."),
    )


def _action_from_payload(raw_action: object) -> WorkerAction | str:
    if not isinstance(raw_action, dict):
        return "Planner preview action was not inspectable."
    payload = raw_action.get("payload")
    if not isinstance(payload, dict):
        return "Planner preview action did not include a payload."
    return WorkerAction(
        action_type=cast(WorkerActionType, str(raw_action.get("action_type") or "")),
        payload=dict(payload),
        reason=str(raw_action.get("reason") or "Execute one validated coding action."),
        requires_approval=bool(raw_action.get("requires_approval")),
    )


def _verification_from_payload(raw_verification: object) -> list[VerificationExpectation] | str:
    if raw_verification is None:
        return []
    if not isinstance(raw_verification, list):
        return "Planner preview verification was not inspectable."
    expectations: list[VerificationExpectation] = []
    for raw_expectation in raw_verification:
        if not isinstance(raw_expectation, dict):
            return "Planner preview verification item was not inspectable."
        expectations.append(
            VerificationExpectation(
                expectation_type=cast(
                    VerificationExpectationType,
                    str(
                        raw_expectation.get("expectation_type")
                        or raw_expectation.get("type")
                        or ""
                    ),
                ),
                target=str(raw_expectation.get("target") or ""),
                expected=(
                    None
                    if raw_expectation.get("expected") is None
                    else str(raw_expectation["expected"])
                ),
                reason=str(raw_expectation.get("reason") or "Verify one-step action."),
            )
        )
    return expectations


def _classify_execution_run(run: dict[str, Any]) -> tuple[CodingLoopStatus, str]:
    status = str(run.get("status") or "")
    if status == "completed":
        return "success", str(run.get("reason") or "One-step coding loop completed.")

    results = run.get("results")
    first_result = results[0] if isinstance(results, list) and results else {}
    if isinstance(first_result, dict) and bool(first_result.get("retryable")):
        return "retryable_failure", str(
            first_result.get("error") or run.get("reason") or "Retryable execution failure."
        )
    if _verification_failed(run):
        return "retryable_failure", str(
            run.get("reason") or "Action executed but verification failed."
        )
    reason = str(run.get("reason") or "One-step coding loop was blocked.")
    if status == "rejected" and _looks_unsafe(reason):
        return "unsafe", reason
    return "blocked", reason


def _verification_failed(run: dict[str, Any]) -> bool:
    results = run.get("results")
    if not isinstance(results, list) or not results:
        return False
    for result in results:
        if not isinstance(result, dict):
            continue
        action_results = result.get("action_results")
        if isinstance(action_results, list) and any(
            isinstance(item, dict) and not bool(item.get("verified", True))
            for item in action_results
        ):
            return True
        verification_results = result.get("verification_results")
        if isinstance(verification_results, list) and any(
            isinstance(item, dict) and not bool(item.get("verified", True))
            for item in verification_results
        ):
            return True
        if bool(result.get("success")) and not bool(result.get("verified")):
            return True
    return False


def _retry_proposal(run: dict[str, Any]) -> dict[str, Any] | None:
    results = run.get("results")
    first_result = results[0] if isinstance(results, list) and results else None
    if not isinstance(first_result, dict):
        return None

    failed_summary = _failed_verification_summary(first_result)
    suggested_next_action = _suggested_next_action(first_result)
    suggested_next_goal = _suggested_next_goal(first_result, failed_summary)
    approval_required = bool(_action_requires_approval(first_result))
    return {
        "reason": "Verification failed after one controlled action; propose one refined retry.",
        "failed_verification_summary": failed_summary,
        "suggested_next_goal": suggested_next_goal,
        "suggested_next_action": suggested_next_action,
        "approval_required": approval_required,
    }


def _suggested_next_action(result: dict[str, Any]) -> dict[str, Any] | None:
    action = _first_action(result)
    if action is None:
        return None
    suggested = dict(action)
    if str(suggested.get("type") or "") == "write_file":
        expected = _first_failed_expected(result)
        if expected is not None:
            suggested["content"] = expected
    return suggested


def _failed_verification_summary(result: dict[str, Any]) -> str:
    verification_results = result.get("verification_results")
    if isinstance(verification_results, list):
        for item in verification_results:
            if isinstance(item, dict) and not bool(item.get("verified", True)):
                expectation = item.get("expectation")
                if isinstance(expectation, dict):
                    target = str(expectation.get("target") or "<unknown>")
                    expected = expectation.get("expected")
                    if expected is not None:
                        return f"Verification failed for {target}; expected {expected!r}."
                    return f"Verification failed for {target}."
                return str(item.get("reason") or "Verification expectation failed.")

    action_results = result.get("action_results")
    if isinstance(action_results, list):
        for item in action_results:
            if isinstance(item, dict) and not bool(item.get("verified", True)):
                action = item.get("action")
                if isinstance(action, dict):
                    return f"Action verification failed for {action.get('type', '<unknown>')}."
                return str(item.get("error") or "Action verification failed.")

    return str(result.get("error") or "Verification failed.")


def _suggested_next_goal(result: dict[str, Any], failed_summary: str) -> str:
    action = _first_action(result)
    if action is None:
        return f"Propose one corrected action that addresses: {failed_summary}"
    action_type = str(action.get("type") or "<unknown>")
    if action_type == "write_file":
        path = str(action.get("path") or "<unknown>")
        expected = _first_failed_expected(result)
        if expected is not None:
            return f"write file {path} with {expected}"
        return f"Propose one corrected write_file action for {path}."
    return f"Propose one corrected {action_type} action that addresses: {failed_summary}"


def _first_failed_expected(result: dict[str, Any]) -> str | None:
    verification_results = result.get("verification_results")
    if not isinstance(verification_results, list):
        return None
    for item in verification_results:
        if not isinstance(item, dict) or bool(item.get("verified", True)):
            continue
        expectation = item.get("expectation")
        if isinstance(expectation, dict) and expectation.get("expected") is not None:
            return str(expectation["expected"])
    return None


def _first_action(result: dict[str, Any]) -> dict[str, Any] | None:
    action = result.get("action")
    if isinstance(action, dict):
        return action
    action_results = result.get("action_results")
    if not isinstance(action_results, list):
        return None
    for item in action_results:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if isinstance(action, dict):
            return action
    return None


def _action_requires_approval(result: dict[str, Any]) -> bool:
    plan = result.get("plan")
    if not isinstance(plan, dict):
        return False
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        return False
    action = actions[0]
    return isinstance(action, dict) and bool(action.get("requires_approval"))


def _classify_block(reason: str) -> CodingLoopStatus:
    lowered = reason.lower()
    if "no bounded execution action matched" in lowered or "did not include" in lowered:
        return "ask_user"
    if _looks_unsafe(reason):
        return "unsafe"
    return "blocked"


def _looks_unsafe(reason: str) -> bool:
    lowered = reason.lower()
    return any(
        token in lowered
        for token in (
            "allowlist",
            "not allowed",
            "outside repocontext",
            "policy",
            "unsafe",
            "escapes execution root",
            "requires approval",
        )
    )


def _result(
    request: CodingLoopRequest,
    status: CodingLoopStatus,
    reason: str,
    *,
    preview_id: str | None = None,
    execution_run_id: str | None = None,
    preview: dict[str, Any] | None = None,
    execution_run: dict[str, Any] | None = None,
    approval_required_reason: str | None = None,
    retry_proposal: dict[str, Any] | None = None,
    created_at: str,
    db_path: Path | None = None,
) -> CodingLoopResult:
    result_id = f"coding-loop-result-{uuid4()}"
    retry_approval = (
        None
        if retry_proposal is None
        else _retry_approval_artifact(
            request,
            result_id,
            preview_id=preview_id,
            execution_run_id=execution_run_id,
            retry_proposal=retry_proposal,
            created_at=_now_iso(),
        )
    )
    result = CodingLoopResult(
        id=result_id,
        request=request,
        status=status,
        reason=reason,
        preview_id=preview_id,
        execution_run_id=execution_run_id,
        preview=preview,
        execution_run=execution_run,
        approval_required_reason=approval_required_reason,
        retry_proposal=retry_proposal,
        retry_approval=retry_approval,
        created_at=created_at,
        updated_at=_now_iso(),
    )
    if retry_approval is not None and db_path is not None:
        store_coding_loop_retry_approval(retry_approval, db_path=db_path)
    if db_path is not None:
        _persist_coding_loop_result(result, db_path=db_path)
    return result


def _persist_coding_loop_result(
    result: CodingLoopResult,
    *,
    db_path: Path,
) -> dict[str, Any]:
    retry_approval = result.retry_approval
    return _persist_coding_loop_result_record(
        _coding_loop_result_record_from_payload(
            result.to_dict(),
            retry_approval=retry_approval,
            db_path=db_path,
        ),
        db_path=db_path,
    )


def _persist_coding_loop_result_record(
    record: dict[str, object],
    *,
    db_path: Path,
) -> dict[str, Any]:
    row = put_coordination_entity(
        "runtime_coding_loop_result",
        record,
        db_path=db_path,
    )
    return {key: row[key] for key in row.keys()}


def _coding_loop_result_record_from_payload(
    payload: dict[str, Any],
    *,
    retry_approval: CodingLoopRetryApproval | None,
    db_path: Path,
) -> dict[str, object]:
    retry_approval_payload = (
        None if retry_approval is None else retry_approval.to_dict()
    )
    retry_proposal = payload.get("retry_proposal")
    retry_payload = retry_proposal if isinstance(retry_proposal, dict) else None
    retry_approval_id = _retry_approval_id(payload, retry_approval_payload)
    latest_retry_approval = (
        None
        if retry_approval_id is None
        else get_coding_loop_retry_approval(retry_approval_id, db_path=db_path)
    )
    latest_retry_payload = (
        retry_approval_payload
        if latest_retry_approval is None
        else latest_retry_approval.to_dict()
    )
    post_run_review = (
        None
        if latest_retry_approval is None or latest_retry_approval.retry_execution_run_id is None
        else review_coding_loop_retry_execution(
            latest_retry_approval.approval_id,
            db_path=db_path,
        ).to_dict()
    )
    execution_run_id = _string_or_none(payload.get("execution_run_id"))
    status = str(payload.get("status") or "")
    reason = str(payload.get("reason") or "")
    return {
        "id": str(payload["id"]),
        "original_goal": _original_goal(payload),
        "status": status,
        "reason": reason,
        "preview_id": _string_or_none(payload.get("preview_id")),
        "execution_run_id": execution_run_id,
        "execution_occurred": int(execution_run_id is not None),
        "approval_required_reason": _string_or_none(
            payload.get("approval_required_reason")
        ),
        "retry_proposal_json": json.dumps(retry_payload or {}),
        "retry_approval_id": retry_approval_id,
        "retry_approval_status": _string_or_none(
            None if latest_retry_payload is None else latest_retry_payload.get("approval_status")
        ),
        "retry_execution_run_id": _string_or_none(
            None
            if latest_retry_payload is None
            else latest_retry_payload.get("retry_execution_run_id")
        ),
        "retry_execution_status": _string_or_none(
            None
            if latest_retry_payload is None
            else latest_retry_payload.get("retry_execution_status")
        ),
        "retry_execution_reason": _string_or_none(
            None
            if latest_retry_payload is None
            else latest_retry_payload.get("retry_execution_reason")
        ),
        "post_run_review_json": json.dumps(post_run_review or {}),
        "next_retry_approval_id": _string_or_none(
            None
            if latest_retry_payload is None
            else latest_retry_payload.get("next_retry_approval_id")
        ),
        "suggested_next_goal": _suggested_goal(retry_payload, post_run_review),
        "suggested_next_action_json": json.dumps(
            _suggested_action(retry_payload, post_run_review) or {}
        ),
        "stop_reason": reason if status == "success" else None,
        "created_at": str(payload.get("created_at") or _now_iso()),
        "updated_at": _now_iso(),
    }


def _retry_approval_id(
    payload: dict[str, Any],
    retry_approval_payload: dict[str, Any] | None,
) -> str | None:
    if retry_approval_payload is not None:
        return _string_or_none(retry_approval_payload.get("approval_id"))
    return _string_or_none(payload.get("retry_approval_id"))


def _original_goal(payload: dict[str, Any]) -> str:
    request = payload.get("request")
    if isinstance(request, dict):
        goal = request.get("goal")
        if isinstance(goal, str):
            return goal
    goal = payload.get("original_goal")
    return goal if isinstance(goal, str) else ""


def _suggested_goal(
    retry_payload: dict[str, Any] | None,
    post_run_review: dict[str, Any] | None,
) -> str | None:
    if post_run_review is not None:
        reviewed = _string_or_none(post_run_review.get("suggested_next_goal"))
        if reviewed is not None:
            return reviewed
    if retry_payload is not None:
        return _string_or_none(retry_payload.get("suggested_next_goal"))
    return None


def _suggested_action(
    retry_payload: dict[str, Any] | None,
    post_run_review: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if post_run_review is not None and isinstance(
        post_run_review.get("suggested_next_action"),
        dict,
    ):
        return post_run_review["suggested_next_action"]
    if retry_payload is not None and isinstance(
        retry_payload.get("suggested_next_action"),
        dict,
    ):
        return retry_payload["suggested_next_action"]
    return None


def _retry_approval_artifact(
    request: CodingLoopRequest,
    result_id: str,
    *,
    preview_id: str | None,
    execution_run_id: str | None,
    retry_proposal: dict[str, Any],
    created_at: str,
) -> CodingLoopRetryApproval:
    proposed_action = retry_proposal.get("suggested_next_action")
    proposed_retry_action = proposed_action if isinstance(proposed_action, dict) else None
    proposed_action_requires_approval = bool(retry_proposal.get("approval_required"))
    approval = ApprovalRequirement.pending(
        reason="Approval is required before executing a coding-loop retry proposal.",
        authority_note=(
            "ARI produced this retry proposal after verification failed; "
            "the retry has not been executed."
        ),
    )
    return CodingLoopRetryApproval(
        approval_id=f"coding-loop-retry-approval-{result_id.removeprefix('coding-loop-result-')}",
        source_coding_loop_result_id=result_id,
        source_preview_id=preview_id,
        source_execution_run_id=execution_run_id,
        original_goal=request.goal,
        proposed_retry_goal=str(retry_proposal.get("suggested_next_goal") or ""),
        proposed_retry_action=proposed_retry_action,
        proposed_retry_action_description=_describe_retry_action(proposed_retry_action),
        reason=str(retry_proposal.get("reason") or "Retry proposal requires approval."),
        failed_verification_summary=str(
            retry_proposal.get("failed_verification_summary") or ""
        ),
        approval=approval,
        approval_status=approval.status,
        retry_execution_requires_approval=True,
        proposed_action_requires_approval=proposed_action_requires_approval,
        created_at=created_at,
        retry_execution_run_id=None,
        retry_execution_status=None,
        retry_execution_reason=None,
        prior_retry_approval_id=None,
        prior_retry_execution_run_id=None,
        next_retry_approval_id=None,
        updated_at=None,
        executed_at=None,
        rejected_by=None,
        rejected_at=None,
    )


def _describe_retry_action(action: dict[str, Any] | None) -> str:
    if action is None:
        return "No concrete retry action was proposed."
    action_type = str(action.get("type") or "<unknown>")
    if action_type in {"read_file", "write_file", "patch_file"}:
        return f"{action_type} {action.get('path', '<unknown>')}"
    if action_type == "run_command":
        command = action.get("command")
        return f"run_command {command}" if command is not None else "run_command <unknown>"
    return action_type


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def _float_or_zero(raw: object) -> float:
    if isinstance(raw, bool):
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
