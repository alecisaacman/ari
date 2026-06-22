from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.paths import DB_PATH

if TYPE_CHECKING:
    from .coding_loop import (
        CodingLoopChainAdvancement,
        CodingLoopChainApprovalMutation,
        CodingLoopChainNextApprovalProposal,
        CodingLoopRetryApproval,
    )


def approve_latest_pending_coding_loop_retry_approval(
    result_id: str,
    *,
    approved_by: str,
    approved_at: str | None = None,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> CodingLoopChainApprovalMutation:
    from .coding_loop import (
        approve_stored_coding_loop_retry_approval,
    )

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
    from .coding_loop import (
        reject_stored_coding_loop_retry_approval,
    )

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
    from .coding_loop import (
        CodingLoopChainNextApprovalProposal,
        create_coding_loop_retry_approval_from_review,
    )
    from .inspection import inspect_coding_loop_chain

    approval_id = _latest_eligible_propose_retry_approval_id(
        result_id,
        max_depth=max_depth,
        db_path=db_path,
    )
    approval = create_coding_loop_retry_approval_from_review(
        approval_id,
        db_path=db_path,
    )
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


def advance_coding_loop_retry_chain(
    result_id: str,
    *,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> CodingLoopChainAdvancement:
    from .coding_loop import (
        CodingLoopChainAdvancement,
        _string_or_none,
        execute_approved_coding_loop_retry_approval,
    )
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


def _chain_advancement_result(
    result_id: str,
    prior_status: str,
    action_taken: str,
    reason: str,
    *,
    refreshed_chain: dict[str, Any] | None,
) -> CodingLoopChainAdvancement:
    from .coding_loop import CodingLoopChainAdvancement, _string_or_none

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
    from .coding_loop import _string_or_none
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
    from .coding_loop import _string_or_none
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
    action_taken: str,
    reason: str,
    approval: CodingLoopRetryApproval,
    *,
    max_depth: int,
    db_path: Path,
) -> CodingLoopChainApprovalMutation:
    from .coding_loop import CodingLoopChainApprovalMutation
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
