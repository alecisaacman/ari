from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.paths import DB_PATH
from ..coordination.db import get_coordination_entity, list_coordination_entities

if TYPE_CHECKING:
    from .coding_loop import CodingLoopResult, CodingLoopRetryApproval


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
