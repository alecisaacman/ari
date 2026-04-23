from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ...core.paths import DB_PATH
from ..coordination.db import put_coordination_entity
from .dispatch import DispatchResult
from .engine import Decision
from .evaluate import EvaluationResult, LoopControlResult


@dataclass(frozen=True, slots=True)
class PersistedDecisionTrail:
    decisions: list[dict[str, object]]
    dispatches: list[dict[str, object]]
    evaluations: list[dict[str, object]]
    cycle: dict[str, object] | None = None


def persist_decision_trail(
    *,
    orchestration_run_id: str,
    decisions: list[Decision],
    dispatch_results: list[DispatchResult],
    evaluation_results: list[EvaluationResult],
    loop_control: LoopControlResult | None = None,
    db_path: Path = DB_PATH,
) -> PersistedDecisionTrail:
    created_at = _now_iso()
    decision_rows: list[dict[str, object]] = []
    dispatch_rows: list[dict[str, object]] = []
    evaluation_rows: list[dict[str, object]] = []

    dispatch_by_reference = {
        result.decision_reference: result for result in dispatch_results
    }
    evaluation_by_reference = {
        result.decision_reference: result for result in evaluation_results
    }

    for decision in decisions:
        signal_id = next(iter(decision.related_signal_ids), None)
        decision_row = _row_to_plain_dict(
            put_coordination_entity(
                "decision_record",
                {
                    "id": decision.id,
                    "orchestration_run_id": orchestration_run_id,
                    "signal_id": signal_id,
                    "intent": decision.intent,
                    "decision_type": decision.decision_type,
                    "priority": decision.priority,
                    "reasoning": decision.reasoning,
                    "related_signal_ids_json": json.dumps(list(decision.related_signal_ids), sort_keys=True),
                    "related_entity_type": decision.related_entity_type,
                    "related_entity_id": decision.related_entity_id,
                    "proposed_action_json": json.dumps(
                        None if decision.proposed_action is None else decision.proposed_action.to_dict(),
                        sort_keys=True,
                    ),
                    "requires_approval": 1 if decision.requires_approval else 0,
                    "action_json": json.dumps(decision.action, sort_keys=True),
                    "confidence": decision.confidence,
                    "created_at": decision.created_at or created_at,
                },
                db_path=db_path,
            )
        )
        decision_rows.append(decision_row)

        decision_reference = _decision_reference(decision)
        dispatch_result = dispatch_by_reference.get(decision_reference)
        if dispatch_result is None:
            continue

        dispatch_row = _row_to_plain_dict(
            put_coordination_entity(
                "decision_dispatch_record",
                {
                    "id": _new_id("decision-dispatch"),
                    "decision_id": decision_row["id"],
                    "decision_reference": dispatch_result.decision_reference,
                    "status": dispatch_result.status,
                    "reason": dispatch_result.reason,
                    "action_json": json.dumps(dispatch_result.action, sort_keys=True),
                    "execution_result_json": json.dumps(
                        dispatch_result.execution_result or {},
                        sort_keys=True,
                    ),
                    "created_at": created_at,
                },
                db_path=db_path,
            )
        )
        dispatch_rows.append(dispatch_row)

        evaluation_result = evaluation_by_reference.get(decision_reference)
        if evaluation_result is None:
            continue

        evaluation_row = _row_to_plain_dict(
            put_coordination_entity(
                "decision_evaluation_record",
                {
                    "id": _new_id("decision-evaluation"),
                    "decision_id": decision_row["id"],
                    "dispatch_record_id": dispatch_row["id"],
                    "decision_reference": evaluation_result.decision_reference,
                    "status": evaluation_result.status,
                    "reason": evaluation_result.reason,
                    "next_step": evaluation_result.next_step,
                    "created_at": created_at,
                },
                db_path=db_path,
            )
        )
        evaluation_rows.append(evaluation_row)

    cycle_row = None
    if loop_control is not None:
        cycle_row = _row_to_plain_dict(
            put_coordination_entity(
                "decision_cycle_record",
                {
                    "id": _new_id("decision-cycle"),
                    "orchestration_run_id": orchestration_run_id,
                    "status": loop_control.status,
                    "reason": loop_control.reason,
                    "decision_count": len(decisions),
                    "dispatch_count": len(dispatch_results),
                    "evaluation_count": len(evaluation_results),
                    "created_at": created_at,
                },
                db_path=db_path,
            )
        )

    return PersistedDecisionTrail(
        decisions=decision_rows,
        dispatches=dispatch_rows,
        evaluations=evaluation_rows,
        cycle=cycle_row,
    )


def _decision_reference(decision: Decision) -> str:
    action_type = str(decision.action.get("type", "unknown"))
    target = str(
        decision.action.get("path")
        or decision.action.get("target")
        or decision.action.get("signal_id")
        or "none"
    )
    return f"{decision.intent}:{action_type}:{target}"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_to_plain_dict(row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}
