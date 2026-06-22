from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.paths import DB_PATH
from ..coordination.db import get_coordination_entity, list_coordination_entities

if TYPE_CHECKING:
    from .coding_loop import (
        CodingLoopChainAdvancement,
        CodingLoopChainApprovalMutation,
        CodingLoopChainNextApprovalProposal,
        CodingLoopContinuationDecision,
        CodingLoopResult,
        CodingLoopRetryApproval,
        CodingLoopRetryExecutionReview,
    )


def list_execution_runs(
    *,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    rows = list_coordination_entities(
        "runtime_execution_run",
        limit=limit,
        db_path=db_path,
    )
    return [_decode_execution_run_row(row) for row in rows]


def get_execution_run(
    run_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    row = get_coordination_entity(
        "runtime_execution_run",
        run_id,
        db_path=db_path,
    )
    if row is None:
        return None
    return _decode_execution_run_row(row)


def list_execution_plan_previews(
    *,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    rows = list_coordination_entities(
        "runtime_execution_plan_preview",
        limit=limit,
        db_path=db_path,
    )
    return [_decode_execution_plan_preview_row(row) for row in rows]


def get_execution_plan_preview(
    preview_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    row = get_coordination_entity(
        "runtime_execution_plan_preview",
        preview_id,
        db_path=db_path,
    )
    if row is None:
        return None
    return _decode_execution_plan_preview_row(row)


def list_coding_loop_results(
    *,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    rows = list_coordination_entities(
        "runtime_coding_loop_result",
        limit=limit,
        db_path=db_path,
    )
    return [_decode_coding_loop_result_row(row) for row in rows]


def get_coding_loop_result(
    result_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    row = get_coordination_entity(
        "runtime_coding_loop_result",
        result_id,
        db_path=db_path,
    )
    if row is None:
        return None
    return _decode_coding_loop_result_row(row)


def inspect_coding_loop_chain(
    result_id: str,
    *,
    max_depth: int = 10,
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    root = get_coding_loop_result(result_id, db_path=db_path)
    if root is None:
        return None

    from .coding_loop import (
        decide_coding_loop_retry_continuation,
        get_coding_loop_retry_approval,
        review_coding_loop_retry_execution,
    )

    safe_max_depth = max(1, max_depth)
    approvals: list[dict[str, Any]] = []
    visited: set[str] = set()
    truncated = False
    cycle_detected = False
    current_approval_id = _string_or_none(root.get("retry_approval_id"))

    while current_approval_id is not None:
        if current_approval_id in visited:
            cycle_detected = True
            break
        if len(approvals) >= safe_max_depth:
            truncated = True
            break
        visited.add(current_approval_id)

        approval = get_coding_loop_retry_approval(current_approval_id, db_path=db_path)
        if approval is None:
            approvals.append(
                {
                    "approval_id": current_approval_id,
                    "missing": True,
                    "retry_approval": None,
                    "post_run_review": None,
                    "continuation": None,
                    "next_retry_approval_id": None,
                }
            )
            break

        approval_payload = inspect_coding_loop_retry_approval(approval)
        review_payload = None
        continuation_payload = None
        try:
            review_payload = inspect_coding_loop_retry_execution_review(
                review_coding_loop_retry_execution(current_approval_id, db_path=db_path)
            )
            continuation_payload = inspect_coding_loop_continuation_decision(
                decide_coding_loop_retry_continuation(
                    current_approval_id,
                    db_path=db_path,
                )
            )
        except ValueError:
            review_payload = None
            continuation_payload = None

        approvals.append(
            {
                "approval_id": current_approval_id,
                "missing": False,
                "retry_approval": approval_payload,
                "approval_status": approval_payload.get("approval_status"),
                "retry_execution_run_id": approval_payload.get("retry_execution_run_id"),
                "retry_execution_status": approval_payload.get("retry_execution_status"),
                "retry_execution_reason": approval_payload.get("retry_execution_reason"),
                "post_run_review": review_payload,
                "continuation": continuation_payload,
                "next_retry_approval_id": approval_payload.get("next_retry_approval_id"),
                "created_at": approval_payload.get("created_at"),
                "updated_at": approval_payload.get("updated_at"),
            }
        )
        current_approval_id = _string_or_none(approval_payload.get("next_retry_approval_id"))

    terminal_status = _chain_terminal_status(
        root,
        approvals,
        truncated=truncated,
        cycle_detected=cycle_detected,
    )
    latest = approvals[-1] if approvals else None
    return {
        "root_coding_loop_result_id": root["id"],
        "original_goal": root["original_goal"],
        "initial_status": root["status"],
        "initial_reason": root["reason"],
        "initial_execution_run_id": root["execution_run_id"],
        "retry_approvals": approvals,
        "terminal_status": terminal_status,
        "chain_depth": len(approvals),
        "max_depth": safe_max_depth,
        "truncated": truncated,
        "cycle_detected": cycle_detected,
        "created_at": root["created_at"],
        "updated_at": _latest_chain_timestamp(root, approvals),
        "latest_retry_approval_id": None if latest is None else latest.get("approval_id"),
        "next_retry_approval_id": None
        if latest is None
        else latest.get("next_retry_approval_id"),
    }


def inspect_coding_loop_chain_advancement(
    advancement: CodingLoopChainAdvancement | dict[str, Any],
) -> dict[str, Any]:
    payload = advancement if isinstance(advancement, dict) else advancement.to_dict()
    return {
        "root_coding_loop_result_id": payload.get("root_coding_loop_result_id"),
        "prior_terminal_status": payload.get("prior_terminal_status"),
        "action_taken": payload.get("action_taken"),
        "reason": payload.get("reason"),
        "executed_retry_approval_id": payload.get("executed_retry_approval_id"),
        "retry_execution_run_id": payload.get("retry_execution_run_id"),
        "refreshed_terminal_status": payload.get("refreshed_terminal_status"),
        "refreshed_chain": payload.get("refreshed_chain"),
        "stop_reason": payload.get("stop_reason"),
        "created_at": payload.get("created_at"),
    }


def inspect_coding_loop_chain_approval_mutation(
    mutation: CodingLoopChainApprovalMutation | dict[str, Any],
) -> dict[str, Any]:
    payload = mutation if isinstance(mutation, dict) else mutation.to_dict()
    return {
        "root_coding_loop_result_id": payload.get("root_coding_loop_result_id"),
        "action_taken": payload.get("action_taken"),
        "reason": payload.get("reason"),
        "updated_retry_approval": payload.get("updated_retry_approval"),
        "refreshed_chain": payload.get("refreshed_chain"),
        "created_at": payload.get("created_at"),
    }


def inspect_coding_loop_chain_next_approval_proposal(
    proposal: CodingLoopChainNextApprovalProposal | dict[str, Any],
) -> dict[str, Any]:
    payload = proposal if isinstance(proposal, dict) else proposal.to_dict()
    return {
        "root_coding_loop_result_id": payload.get("root_coding_loop_result_id"),
        "reason": payload.get("reason"),
        "new_retry_approval": payload.get("new_retry_approval"),
        "refreshed_chain": payload.get("refreshed_chain"),
        "created_at": payload.get("created_at"),
    }


def inspect_coding_loop_result(
    result: CodingLoopResult | dict[str, Any],
) -> dict[str, Any]:
    payload = result if isinstance(result, dict) else result.to_dict()
    retry_proposal = payload.get("retry_proposal")
    retry_payload = retry_proposal if isinstance(retry_proposal, dict) else None
    retry_approval = payload.get("retry_approval")
    retry_approval_payload = retry_approval if isinstance(retry_approval, dict) else None
    execution_run_id = _string_or_none(payload.get("execution_run_id"))
    return {
        "id": payload.get("id"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "preview_id": payload.get("preview_id"),
        "execution_run_id": execution_run_id,
        "execution_occurred": execution_run_id is not None,
        "approval_required_reason": payload.get("approval_required_reason"),
        "retry_proposal": retry_payload,
        "retry_approval": retry_approval_payload,
        "retry_approval_id": (
            None if retry_approval_payload is None else retry_approval_payload.get("approval_id")
        ),
        "retry_approval_status": (
            None
            if retry_approval_payload is None
            else retry_approval_payload.get("approval_status")
        ),
        "suggested_next_goal": (
            None if retry_payload is None else retry_payload.get("suggested_next_goal")
        ),
        "suggested_next_action": (
            None if retry_payload is None else retry_payload.get("suggested_next_action")
        ),
        "retry_requires_approval": (
            None if retry_payload is None else retry_payload.get("approval_required")
        ),
        "preview": payload.get("preview"),
        "execution_run": payload.get("execution_run"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


def inspect_coding_loop_retry_approval(
    approval: CodingLoopRetryApproval | dict[str, Any],
) -> dict[str, Any]:
    payload = approval if isinstance(approval, dict) else approval.to_dict()
    return {
        "approval_id": payload.get("approval_id"),
        "source_coding_loop_result_id": payload.get("source_coding_loop_result_id"),
        "source_preview_id": payload.get("source_preview_id"),
        "source_execution_run_id": payload.get("source_execution_run_id"),
        "original_goal": payload.get("original_goal"),
        "proposed_retry_goal": payload.get("proposed_retry_goal"),
        "proposed_retry_action": payload.get("proposed_retry_action"),
        "proposed_retry_action_description": payload.get(
            "proposed_retry_action_description"
        ),
        "reason": payload.get("reason"),
        "failed_verification_summary": payload.get("failed_verification_summary"),
        "approval_status": payload.get("approval_status"),
        "approval": payload.get("approval"),
        "retry_execution_run_id": payload.get("retry_execution_run_id"),
        "retry_execution_status": payload.get("retry_execution_status"),
        "retry_execution_reason": payload.get("retry_execution_reason"),
        "prior_retry_approval_id": payload.get("prior_retry_approval_id"),
        "prior_retry_execution_run_id": payload.get("prior_retry_execution_run_id"),
        "next_retry_approval_id": payload.get("next_retry_approval_id"),
        "retry_execution_requires_approval": payload.get(
            "retry_execution_requires_approval"
        ),
        "proposed_action_requires_approval": payload.get("proposed_action_requires_approval"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "executed_at": payload.get("executed_at"),
        "rejected_by": payload.get("rejected_by"),
        "rejected_at": payload.get("rejected_at"),
    }


def inspect_coding_loop_retry_execution_review(
    review: CodingLoopRetryExecutionReview | dict[str, Any],
) -> dict[str, Any]:
    payload = review if isinstance(review, dict) else review.to_dict()
    return {
        "approval_id": payload.get("approval_id"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "retry_execution_run_id": payload.get("retry_execution_run_id"),
        "retry_execution_status": payload.get("retry_execution_status"),
        "suggested_next_goal": payload.get("suggested_next_goal"),
        "suggested_next_action": payload.get("suggested_next_action"),
        "approval_required": payload.get("approval_required"),
        "created_at": payload.get("created_at"),
    }


def inspect_coding_loop_continuation_decision(
    decision: CodingLoopContinuationDecision | dict[str, Any],
) -> dict[str, Any]:
    payload = decision if isinstance(decision, dict) else decision.to_dict()
    return {
        "approval_id": payload.get("approval_id"),
        "eligible": payload.get("eligible"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "review_status": payload.get("review_status"),
        "retry_execution_run_id": payload.get("retry_execution_run_id"),
        "next_retry_approval_id": payload.get("next_retry_approval_id"),
        "suggested_next_goal": payload.get("suggested_next_goal"),
        "suggested_next_action": payload.get("suggested_next_action"),
        "approval_required": payload.get("approval_required"),
        "created_at": payload.get("created_at"),
    }


def _decode_execution_run_row(row: Any) -> dict[str, Any]:
    contexts = _json_list(row["contexts_json"])
    decisions = _json_list(row["decisions_json"])
    results = _json_list(row["results_json"])
    return {
        "id": row["id"],
        "goal_id": row["goal_id"],
        "objective": row["objective"],
        "status": row["status"],
        "reason": row["reason"],
        "cycles_run": row["cycles_run"],
        "max_cycles": row["max_cycles"],
        "repo_root": row["repo_root"],
        "planner_config": _planner_config(decisions, results),
        "contexts": contexts,
        "decisions": decisions,
        "results": results,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _decode_execution_plan_preview_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "goal_id": row["goal_id"],
        "objective": row["objective"],
        "status": row["status"],
        "reason": row["reason"],
        "repo_root": row["repo_root"],
        "repo_context": _json_object(row["context_json"]),
        "memory_context": _json_object(row["memory_context_json"]),
        "planner_config": _json_object(row["planner_config_json"]),
        "planner_result": _json_object(row["planner_result_json"]),
        "decision": _json_object(row["decision_json"]),
        "validation_error": row["validation_error"],
        "created_at": row["created_at"],
    }


def _decode_coding_loop_result_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "original_goal": row["original_goal"],
        "status": row["status"],
        "reason": row["reason"],
        "preview_id": row["preview_id"],
        "execution_run_id": row["execution_run_id"],
        "execution_occurred": bool(row["execution_occurred"]),
        "approval_required_reason": row["approval_required_reason"],
        "retry_proposal": _json_object_or_none(row["retry_proposal_json"]),
        "retry_approval_id": row["retry_approval_id"],
        "retry_approval_status": row["retry_approval_status"],
        "retry_execution_run_id": row["retry_execution_run_id"],
        "retry_execution_status": row["retry_execution_status"],
        "retry_execution_reason": row["retry_execution_reason"],
        "post_run_review": _json_object_or_none(row["post_run_review_json"]),
        "next_retry_approval_id": row["next_retry_approval_id"],
        "suggested_next_goal": row["suggested_next_goal"],
        "suggested_next_action": _json_object_or_none(row["suggested_next_action_json"]),
        "stop_reason": row["stop_reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _chain_terminal_status(
    root: dict[str, Any],
    approvals: list[dict[str, Any]],
    *,
    truncated: bool,
    cycle_detected: bool,
) -> str:
    if truncated or cycle_detected:
        return "unknown/incomplete"
    if not approvals:
        root_status = str(root.get("status") or "")
        if root_status == "success":
            return "stopped"
        if root_status in {"blocked", "unsafe", "ask_user"}:
            return root_status
        if root_status == "requires_approval":
            return "pending_approval"
        return "unknown/incomplete"

    latest = approvals[-1]
    if latest.get("missing") is True:
        return "unknown/incomplete"

    approval_status = str(latest.get("approval_status") or "")
    retry_execution_run_id = _string_or_none(latest.get("retry_execution_run_id"))
    if approval_status == "pending":
        return "pending_approval"
    if approval_status == "rejected":
        return "rejected"
    if approval_status == "approved" and retry_execution_run_id is None:
        return "executable_approved_retry_available"

    review = latest.get("post_run_review")
    review_status = str(review.get("status") or "") if isinstance(review, dict) else ""
    if review_status == "stop":
        return "stopped"
    if review_status in {"blocked", "unsafe", "ask_user"}:
        return review_status
    if review_status == "propose_retry":
        return "unknown/incomplete"
    return "unknown/incomplete"


def _latest_chain_timestamp(
    root: dict[str, Any],
    approvals: list[dict[str, Any]],
) -> str | None:
    timestamps = [
        value
        for value in (
            root.get("updated_at"),
            *[approval.get("updated_at") for approval in approvals],
            *[approval.get("created_at") for approval in approvals],
        )
        if isinstance(value, str)
    ]
    return max(timestamps) if timestamps else None


def _json_list(raw_value: str) -> list[dict[str, Any]]:
    decoded = json.loads(raw_value or "[]")
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


def _json_object(raw_value: str) -> dict[str, Any]:
    decoded = json.loads(raw_value or "{}")
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _json_object_or_none(raw_value: str) -> dict[str, Any] | None:
    decoded = _json_object(raw_value)
    return decoded or None


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def _planner_config(
    decisions: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    for result in results:
        config = result.get("planner_config")
        if isinstance(config, dict):
            return config
    if decisions:
        planner_name = decisions[0].get("planner_name")
        if isinstance(planner_name, str):
            return {
                "requested": planner_name,
                "selected": planner_name,
                "fallback_reason": None,
            }
    return {
        "requested": "unknown",
        "selected": "unknown",
        "fallback_reason": None,
    }
