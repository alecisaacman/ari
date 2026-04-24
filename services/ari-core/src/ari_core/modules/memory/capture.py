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
