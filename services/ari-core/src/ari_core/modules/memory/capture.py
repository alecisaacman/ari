from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.paths import DB_PATH
from ..execution.inspection import get_execution_run, list_execution_runs
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
