from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.paths import DB_PATH
from ..execution.inspection import (
    get_execution_run,
    inspect_coding_loop_chain,
    list_execution_runs,
)
from .db import create_memory_block, memory_block_to_payload


def capture_execution_run_memory(
    run_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    run = get_execution_run(run_id, db_path=db_path)
    if run is None:
        raise ValueError(f"Execution run {run_id} was not found.")
    return _capture_run(run, db_path=db_path)


def capture_recent_execution_run_memories(
    *,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> list[dict[str, object]]:
    runs = list_execution_runs(limit=limit, db_path=db_path)
    return [_capture_run(run, db_path=db_path) for run in runs]


def capture_coding_loop_retry_approval_memory(
    approval_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    from ..execution.coding_loop import get_coding_loop_retry_approval
    from ..execution.inspection import inspect_coding_loop_retry_approval

    approval = get_coding_loop_retry_approval(approval_id, db_path=db_path)
    if approval is None:
        raise ValueError(f"Coding-loop retry approval {approval_id} was not found.")
    payload = inspect_coding_loop_retry_approval(approval)
    block = create_memory_block(
        block_id=f"memory-block-coding-loop-retry-approval-{approval_id}",
        replace_existing=True,
        layer="session",
        kind="coding_loop_retry_execution_summary",
        title=_retry_title(payload),
        body=_retry_body(payload),
        source=approval_id,
        importance=_retry_importance(payload),
        confidence=0.95,
        tags=_retry_tags(payload),
        subject_ids=_retry_subject_ids(payload),
        evidence=[_retry_evidence(payload)],
        db_path=db_path,
    )
    return memory_block_to_payload(block)


def capture_coding_loop_chain_lifecycle_memory(
    result_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    chain = inspect_coding_loop_chain(result_id, db_path=db_path)
    if chain is None:
        raise ValueError(f"Coding-loop result {result_id} was not found.")

    summary = _chain_summary(chain)
    block = create_memory_block(
        block_id=f"memory-block-coding-loop-chain-{result_id}",
        replace_existing=True,
        layer="session",
        kind="coding_loop_chain_lifecycle_summary",
        title=_chain_title(summary),
        body=_chain_body(summary),
        source=result_id,
        importance=_chain_importance(summary),
        confidence=0.95,
        tags=_chain_tags(summary),
        subject_ids=_chain_subject_ids(summary),
        evidence=[_chain_evidence(summary)],
        db_path=db_path,
    )
    return memory_block_to_payload(block)


def _capture_run(run: dict[str, Any], *, db_path: Path) -> dict[str, object]:
    run_id = str(run["id"])
    status = str(run.get("status") or "unknown")
    objective = str(run.get("objective") or "").strip()
    planner_config = (
        run.get("planner_config") if isinstance(run.get("planner_config"), dict) else {}
    )
    selected_planner = str(planner_config.get("selected") or "unknown")
    fallback_reason = planner_config.get("fallback_reason")
    block = create_memory_block(
        block_id=f"memory-block-execution-run-{run_id}",
        replace_existing=True,
        layer="session",
        kind="execution_run_summary",
        title=_title(status, objective),
        body=_body(run, selected_planner, fallback_reason),
        source=run_id,
        importance=_importance(status),
        confidence=0.95,
        tags=_tags(status, selected_planner),
        subject_ids=[run_id, str(run.get("goal_id") or "")],
        evidence=[_evidence(run, selected_planner, fallback_reason)],
        db_path=db_path,
    )
    return memory_block_to_payload(block)


def _retry_title(approval: dict[str, Any]) -> str:
    status = str(approval.get("approval_status") or "unknown")
    execution_status = str(approval.get("retry_execution_status") or "not_executed")
    return f"Coding-loop retry {status}/{execution_status}: {approval.get('approval_id')}"


def _retry_body(approval: dict[str, Any]) -> str:
    lines = [
        f"Original goal: {approval.get('original_goal')}",
        f"Proposed retry goal: {approval.get('proposed_retry_goal')}",
        f"Proposed retry action: {approval.get('proposed_retry_action_description')}",
        f"Failed verification: {approval.get('failed_verification_summary')}",
        f"Approval status: {approval.get('approval_status')}",
        f"Retry execution run: {approval.get('retry_execution_run_id')}",
        f"Retry execution status: {approval.get('retry_execution_status')}",
        f"Retry execution reason: {approval.get('retry_execution_reason')}",
    ]
    approval_payload = approval.get("approval")
    if isinstance(approval_payload, dict):
        approved_by = approval_payload.get("approved_by")
        approved_at = approval_payload.get("approved_at")
        rejected_reason = approval_payload.get("rejected_reason")
        if approved_by:
            lines.append(f"Approved by: {approved_by}")
        if approved_at:
            lines.append(f"Approved at: {approved_at}")
        if rejected_reason:
            lines.append(f"Rejected reason: {rejected_reason}")
    return "\n".join(lines)


def _retry_importance(approval: dict[str, Any]) -> int:
    execution_status = approval.get("retry_execution_status")
    if execution_status in {"failed", "rejected", "exhausted"}:
        return 4
    if execution_status == "completed":
        return 3
    return 2


def _retry_tags(approval: dict[str, Any]) -> list[str]:
    tags = [
        "execution",
        "coding-loop",
        "retry-approval",
        f"approval:{approval.get('approval_status') or 'unknown'}",
    ]
    execution_status = approval.get("retry_execution_status")
    if execution_status:
        tags.append(f"retry-execution:{execution_status}")
    return tags


def _retry_subject_ids(approval: dict[str, Any]) -> list[str]:
    ids = [
        str(approval.get("approval_id") or ""),
        str(approval.get("source_coding_loop_result_id") or ""),
        str(approval.get("source_preview_id") or ""),
        str(approval.get("source_execution_run_id") or ""),
        str(approval.get("retry_execution_run_id") or ""),
    ]
    return [value for value in ids if value]


def _retry_evidence(approval: dict[str, Any]) -> dict[str, object]:
    return {
        "type": "coding_loop_retry_approval",
        "approval_id": approval.get("approval_id"),
        "approval_status": approval.get("approval_status"),
        "source_coding_loop_result_id": approval.get("source_coding_loop_result_id"),
        "source_preview_id": approval.get("source_preview_id"),
        "source_execution_run_id": approval.get("source_execution_run_id"),
        "retry_execution_run_id": approval.get("retry_execution_run_id"),
        "retry_execution_status": approval.get("retry_execution_status"),
        "retry_execution_reason": approval.get("retry_execution_reason"),
        "failed_verification_summary": approval.get("failed_verification_summary"),
        "proposed_retry_goal": approval.get("proposed_retry_goal"),
        "proposed_retry_action": approval.get("proposed_retry_action"),
    }


def _chain_summary(chain: dict[str, Any]) -> dict[str, object]:
    approvals = chain.get("retry_approvals")
    approval_items = [item for item in approvals if isinstance(item, dict)] if isinstance(
        approvals,
        list,
    ) else []
    approval_payloads = [
        item.get("retry_approval")
        for item in approval_items
        if isinstance(item.get("retry_approval"), dict)
    ]
    latest = approval_items[-1] if approval_items else {}
    latest_approval = (
        latest.get("retry_approval") if isinstance(latest.get("retry_approval"), dict) else {}
    )
    latest_review = (
        latest.get("post_run_review")
        if isinstance(latest.get("post_run_review"), dict)
        else {}
    )
    latest_continuation = (
        latest.get("continuation") if isinstance(latest.get("continuation"), dict) else {}
    )
    terminal_status = str(chain.get("terminal_status") or "unknown/incomplete")
    approval_statuses = [
        str(approval.get("approval_status") or "unknown")
        for approval in approval_payloads
    ]
    retry_executions = [
        approval
        for approval in approval_payloads
        if _string_or_none(approval.get("retry_execution_run_id")) is not None
    ]
    final_execution_status = _string_or_none(latest_approval.get("retry_execution_status"))
    final_execution_reason = _string_or_none(latest_approval.get("retry_execution_reason"))
    final_review_status = _string_or_none(latest_review.get("status"))
    continuation_status = _string_or_none(latest_continuation.get("status"))
    failure_summary = _chain_failure_summary(approval_payloads, latest_review)
    success_summary = _chain_success_summary(
        terminal_status,
        final_execution_status,
        final_execution_reason,
    )
    stop_reason = _chain_stop_reason(terminal_status, latest_review, chain)
    lesson = _chain_lesson(
        terminal_status,
        failure_summary,
        success_summary,
        continuation_status,
    )
    improvement_flags = _chain_improvement_flags(
        terminal_status,
        failure_summary,
        final_review_status,
        continuation_status,
    )
    return {
        "type": "coding_loop_chain_lifecycle",
        "root_coding_loop_result_id": chain.get("root_coding_loop_result_id"),
        "original_goal": chain.get("original_goal"),
        "terminal_status": terminal_status,
        "chain_depth": int(chain.get("chain_depth") or len(approval_items)),
        "approval_count": len(approval_payloads),
        "approved_count": approval_statuses.count("approved"),
        "rejected_count": approval_statuses.count("rejected"),
        "pending_count": approval_statuses.count("pending"),
        "retry_execution_count": len(retry_executions),
        "final_execution_run_id": _string_or_none(
            latest_approval.get("retry_execution_run_id")
        ),
        "final_execution_status": final_execution_status,
        "final_execution_reason": final_execution_reason,
        "final_post_run_review_status": final_review_status,
        "continuation_decision": continuation_status,
        "key_failure_summary": failure_summary,
        "key_successful_change_summary": success_summary,
        "stop_reason": stop_reason,
        "lesson": lesson,
        "improvement_flags": improvement_flags,
        "created_at": chain.get("updated_at") or chain.get("created_at"),
        "approval_ids": [
            str(approval.get("approval_id"))
            for approval in approval_payloads
            if approval.get("approval_id")
        ],
        "execution_run_ids": [
            str(approval.get("retry_execution_run_id"))
            for approval in retry_executions
            if approval.get("retry_execution_run_id")
        ],
        "truncated": bool(chain.get("truncated")),
        "cycle_detected": bool(chain.get("cycle_detected")),
    }


def _chain_failure_summary(
    approvals: list[object],
    latest_review: dict[str, Any],
) -> str | None:
    for approval in reversed(approvals):
        if isinstance(approval, dict):
            summary = _string_or_none(approval.get("failed_verification_summary"))
            if summary:
                return summary
    return _string_or_none(latest_review.get("reason"))


def _chain_success_summary(
    terminal_status: str,
    execution_status: str | None,
    execution_reason: str | None,
) -> str | None:
    if terminal_status != "stopped" and execution_status != "completed":
        return None
    reason = execution_reason or "Retry execution completed."
    return f"Final retry execution completed: {reason}"


def _chain_stop_reason(
    terminal_status: str,
    latest_review: dict[str, Any],
    chain: dict[str, Any],
) -> str | None:
    if terminal_status == "stopped":
        return _string_or_none(latest_review.get("reason")) or _string_or_none(
            chain.get("initial_reason")
        )
    if terminal_status in {
        "pending_approval",
        "rejected",
        "blocked",
        "unsafe",
        "ask_user",
        "executable_approved_retry_available",
    }:
        return f"Chain paused at terminal status: {terminal_status}."
    return None


def _chain_lesson(
    terminal_status: str,
    failure_summary: str | None,
    success_summary: str | None,
    continuation_status: str | None,
) -> str:
    if success_summary:
        return (
            "A bounded approval-gated retry resolved the chain after verification "
            "feedback."
        )
    if terminal_status == "pending_approval":
        return "The chain is paused at an authority boundary before the next retry."
    if terminal_status == "rejected":
        return "The operator rejected the proposed retry; future planning should avoid it."
    if terminal_status == "ask_user":
        return "ARI needs user clarification before it can continue safely."
    if terminal_status == "unsafe":
        return "ARI stopped because the proposed continuation crossed a safety boundary."
    if terminal_status == "blocked":
        return "ARI could not derive a safe bounded continuation from this chain."
    if continuation_status == "create_pending_approval":
        return "A review found a bounded next retry, but authority is still required."
    if failure_summary:
        return "Verification feedback should be folded into future planning context."
    return "The chain should remain inspectable until a clearer terminal outcome exists."


def _chain_improvement_flags(
    terminal_status: str,
    failure_summary: str | None,
    review_status: str | None,
    continuation_status: str | None,
) -> dict[str, bool]:
    return {
        "planner_improvement": bool(
            failure_summary
            and terminal_status
            in {
                "pending_approval",
                "blocked",
                "unknown/incomplete",
                "executable_approved_retry_available",
            }
        ),
        "verification_improvement": bool(
            failure_summary and review_status in {"propose_retry", "ask_user", None}
        ),
        "authority_improvement": terminal_status
        in {"pending_approval", "executable_approved_retry_available"},
        "user_clarification": terminal_status == "ask_user"
        or continuation_status == "ask_user",
    }


def _chain_title(summary: dict[str, object]) -> str:
    status = str(summary.get("terminal_status") or "unknown")
    depth = summary.get("chain_depth")
    goal = str(summary.get("original_goal") or "untitled goal")
    trimmed = goal if len(goal) <= 56 else f"{goal[:53]}..."
    return f"Coding-loop chain {status}/{depth}: {trimmed}"


def _chain_body(summary: dict[str, object]) -> str:
    flags = summary.get("improvement_flags")
    flag_payload = flags if isinstance(flags, dict) else {}
    return "\n".join(
        [
            f"Original goal: {summary.get('original_goal')}",
            f"Terminal status: {summary.get('terminal_status')}",
            f"Chain depth: {summary.get('chain_depth')}",
            (
                "Approvals: "
                f"{summary.get('approval_count')} total, "
                f"{summary.get('approved_count')} approved, "
                f"{summary.get('rejected_count')} rejected, "
                f"{summary.get('pending_count')} pending"
            ),
            f"Retry executions: {summary.get('retry_execution_count')}",
            f"Final execution status: {summary.get('final_execution_status')}",
            f"Final execution reason: {summary.get('final_execution_reason')}",
            f"Final review status: {summary.get('final_post_run_review_status')}",
            f"Continuation decision: {summary.get('continuation_decision')}",
            f"Key failure: {summary.get('key_failure_summary')}",
            f"Successful change: {summary.get('key_successful_change_summary')}",
            f"Stop reason: {summary.get('stop_reason')}",
            f"Lesson: {summary.get('lesson')}",
            (
                "Improvement signals: "
                f"planner={bool(flag_payload.get('planner_improvement'))}, "
                f"verification={bool(flag_payload.get('verification_improvement'))}, "
                f"authority={bool(flag_payload.get('authority_improvement'))}, "
                f"user_clarification={bool(flag_payload.get('user_clarification'))}"
            ),
        ]
    )


def _chain_importance(summary: dict[str, object]) -> int:
    status = summary.get("terminal_status")
    if status in {"unsafe", "blocked", "ask_user", "unknown/incomplete"}:
        return 4
    if status in {"pending_approval", "executable_approved_retry_available"}:
        return 3
    return 3


def _chain_tags(summary: dict[str, object]) -> list[str]:
    status = str(summary.get("terminal_status") or "unknown")
    tags = ["execution", "coding-loop", "chain-lifecycle", f"status:{status}"]
    flags = summary.get("improvement_flags")
    if isinstance(flags, dict):
        for name, enabled in flags.items():
            if enabled:
                tags.append(f"improvement:{name}")
    return tags


def _chain_subject_ids(summary: dict[str, object]) -> list[str]:
    raw_ids: list[object] = [
        summary.get("root_coding_loop_result_id"),
        *(summary.get("approval_ids") if isinstance(summary.get("approval_ids"), list) else []),
        *(
            summary.get("execution_run_ids")
            if isinstance(summary.get("execution_run_ids"), list)
            else []
        ),
    ]
    return [str(value) for value in raw_ids if value]


def _chain_evidence(summary: dict[str, object]) -> dict[str, object]:
    return {
        "type": "coding_loop_chain_lifecycle",
        "root_coding_loop_result_id": summary.get("root_coding_loop_result_id"),
        "terminal_status": summary.get("terminal_status"),
        "chain_depth": summary.get("chain_depth"),
        "approval_count": summary.get("approval_count"),
        "approved_count": summary.get("approved_count"),
        "rejected_count": summary.get("rejected_count"),
        "pending_count": summary.get("pending_count"),
        "retry_execution_count": summary.get("retry_execution_count"),
        "final_execution_run_id": summary.get("final_execution_run_id"),
        "final_execution_status": summary.get("final_execution_status"),
        "final_post_run_review_status": summary.get("final_post_run_review_status"),
        "continuation_decision": summary.get("continuation_decision"),
        "key_failure_summary": summary.get("key_failure_summary"),
        "key_successful_change_summary": summary.get("key_successful_change_summary"),
        "stop_reason": summary.get("stop_reason"),
        "lesson": summary.get("lesson"),
        "improvement_flags": summary.get("improvement_flags"),
        "approval_ids": summary.get("approval_ids"),
        "execution_run_ids": summary.get("execution_run_ids"),
        "created_at": summary.get("created_at"),
        "truncated": summary.get("truncated"),
        "cycle_detected": summary.get("cycle_detected"),
    }


def _title(status: str, objective: str) -> str:
    trimmed = objective if len(objective) <= 72 else f"{objective[:69]}..."
    return f"Execution {status}: {trimmed or 'untitled goal'}"


def _body(run: dict[str, Any], selected_planner: str, fallback_reason: object) -> str:
    lines = [
        f"Objective: {run.get('objective')}",
        f"Status: {run.get('status')}",
        f"Reason: {run.get('reason')}",
        f"Cycles run: {run.get('cycles_run')} of {run.get('max_cycles')}",
        f"Planner: {selected_planner}",
    ]
    if fallback_reason:
        lines.append(f"Planner fallback: {fallback_reason}")
    results = run.get("results") if isinstance(run.get("results"), list) else []
    if results:
        final_result = results[-1]
        if isinstance(final_result, dict):
            lines.append(f"Verified: {final_result.get('verified')}")
            error = final_result.get("error")
            if error:
                lines.append(f"Error: {error}")
    return "\n".join(lines)


def _importance(status: str) -> int:
    if status == "completed":
        return 3
    if status in {"failed", "rejected", "exhausted"}:
        return 4
    return 2


def _tags(status: str, selected_planner: str) -> list[str]:
    return ["execution", f"status:{status}", f"planner:{selected_planner}"]


def _evidence(
    run: dict[str, Any],
    selected_planner: str,
    fallback_reason: object,
) -> dict[str, object]:
    return {
        "type": "execution_run",
        "run_id": run.get("id"),
        "goal_id": run.get("goal_id"),
        "status": run.get("status"),
        "reason": run.get("reason"),
        "cycles_run": run.get("cycles_run"),
        "max_cycles": run.get("max_cycles"),
        "planner": selected_planner,
        "fallback_reason": fallback_reason,
    }


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None
