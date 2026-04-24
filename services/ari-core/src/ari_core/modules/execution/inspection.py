from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...core.paths import DB_PATH
from ..coordination.db import get_coordination_entity, list_coordination_entities


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
