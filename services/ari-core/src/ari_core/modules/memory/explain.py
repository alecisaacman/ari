from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.paths import DB_PATH
from ..execution.inspection import get_execution_run
from .db import list_memory_blocks, memory_block_to_payload


def explain_execution_run(
    run_id: str,
    *,
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    run = get_execution_run(run_id, db_path=db_path)
    if run is None:
        raise ValueError(f"Execution run {run_id} was not found.")
    related_memory = _related_memory_blocks(run_id, db_path=db_path)
    decisions = _decision_summaries(run)
    results = _result_summaries(run)
    planner_config = (
        run.get("planner_config") if isinstance(run.get("planner_config"), dict) else {}
    )
    return {
        "subject": {
            "type": "execution_run",
            "id": run_id,
        },
        "summary": _summary(run, planner_config, related_memory),
        "why": _why(run, decisions, planner_config),
        "status": run.get("status"),
        "objective": run.get("objective"),
        "reason": run.get("reason"),
        "planner_config": planner_config,
        "decisions": decisions,
        "results": results,
        "memory_blocks": related_memory,
        "evidence": {
            "execution_run": run,
            "memory_block_ids": [block["id"] for block in related_memory],
        },
    }


def _related_memory_blocks(run_id: str, *, db_path: Path) -> list[dict[str, object]]:
    blocks = [
        memory_block_to_payload(row)
        for row in list_memory_blocks(layer="session", limit=200, db_path=db_path)
    ]
    return [
        block
        for block in blocks
        if block.get("source") == run_id or run_id in set(block.get("subject_ids", []))
    ]


def _decision_summaries(run: dict[str, Any]) -> list[dict[str, object]]:
    raw_decisions = run.get("decisions") if isinstance(run.get("decisions"), list) else []
    summaries: list[dict[str, object]] = []
    for decision in raw_decisions:
        if not isinstance(decision, dict):
            continue
        action = decision.get("action") if isinstance(decision.get("action"), dict) else {}
        plan = decision.get("plan") if isinstance(decision.get("plan"), dict) else {}
        actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
        summaries.append(
            {
                "id": decision.get("id"),
                "cycle_index": decision.get("cycle_index"),
                "status": decision.get("status"),
                "reason": decision.get("reason"),
                "confidence": decision.get("confidence"),
                "planner_name": decision.get("planner_name"),
                "action_type": action.get("action_type"),
                "planned_action_count": len(actions),
                "failure_context": decision.get("failure_context"),
            }
        )
    return summaries


def _result_summaries(run: dict[str, Any]) -> list[dict[str, object]]:
    raw_results = run.get("results") if isinstance(run.get("results"), list) else []
    summaries: list[dict[str, object]] = []
    for index, result in enumerate(raw_results, start=1):
        if not isinstance(result, dict):
            continue
        summaries.append(
            {
                "index": index,
                "success": result.get("success"),
                "verified": result.get("verified"),
                "retryable": result.get("retryable"),
                "error": result.get("error"),
                "planner": result.get("planner"),
                "confidence": result.get("confidence"),
            }
        )
    return summaries


def _summary(
    run: dict[str, Any],
    planner_config: dict[str, Any],
    related_memory: list[dict[str, object]],
) -> str:
    memory_count = len(related_memory)
    return (
        f"Execution run {run.get('id')} is {run.get('status')} after "
        f"{run.get('cycles_run')} cycle(s). Planner selected "
        f"{planner_config.get('selected', 'unknown')}. "
        f"{memory_count} linked memory block(s) are available."
    )


def _why(
    run: dict[str, Any],
    decisions: list[dict[str, object]],
    planner_config: dict[str, Any],
) -> list[str]:
    reasons = [
        f"Goal objective: {run.get('objective')}",
        f"Final status reason: {run.get('reason')}",
    ]
    if planner_config.get("fallback_reason"):
        reasons.append(f"Planner fallback: {planner_config['fallback_reason']}")
    for decision in decisions:
        reasons.append(
            "Cycle "
            f"{decision.get('cycle_index')} used {decision.get('planner_name')} "
            f"with confidence {decision.get('confidence')}: {decision.get('reason')}"
        )
    return reasons
