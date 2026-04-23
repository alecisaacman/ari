from __future__ import annotations

import json
from pathlib import Path

from ari_core.modules.coordination.db import list_coordination_entities
from ari_core.modules.decision.dispatch import DispatchResult
from ari_core.modules.decision.engine import Decision, ProposedAction
from ari_core.modules.decision.evaluate import EvaluationResult, LoopControlResult
from ari_core.modules.decision.persistence import persist_decision_trail


def test_persist_decision_trail_round_trips_canonically(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"

    decision = Decision(
        intent="inspect_workspace_file",
        decision_type="act",
        priority=80,
        reasoning="The file can be read safely.",
        confidence=0.9,
        related_signal_ids=("signal-1",),
        proposed_action=ProposedAction("read_file", {"path": "sample.txt", "signal_id": "signal-1"}),
    )
    dispatch = DispatchResult(
        decision_reference="inspect_workspace_file:read_file:sample.txt",
        status="executed",
        reason="read_file is safe for automatic execution.",
        action=decision.action,
        execution_result={"success": True, "content": "hello\n"},
    )
    evaluation = EvaluationResult(
        decision_reference=dispatch.decision_reference,
        status="completed",
        reason="The authorized action executed successfully.",
        next_step="stop",
    )

    trail = persist_decision_trail(
        orchestration_run_id="run-1",
        decisions=[decision],
        dispatch_results=[dispatch],
        evaluation_results=[evaluation],
        loop_control=LoopControlResult(
            status="stop",
            reason="Authorized decisions completed without requiring escalation.",
        ),
        db_path=db_path,
    )

    assert len(trail.decisions) == 1
    assert len(trail.dispatches) == 1
    assert len(trail.evaluations) == 1

    stored_decisions = list_coordination_entities("decision_record", limit=10, db_path=db_path)
    stored_dispatches = list_coordination_entities("decision_dispatch_record", limit=10, db_path=db_path)
    stored_evaluations = list_coordination_entities("decision_evaluation_record", limit=10, db_path=db_path)
    stored_cycles = list_coordination_entities("decision_cycle_record", limit=10, db_path=db_path)

    assert len(stored_decisions) == 1
    assert stored_decisions[0]["orchestration_run_id"] == "run-1"
    assert stored_decisions[0]["decision_type"] == "act"
    assert stored_decisions[0]["requires_approval"] == 0
    assert json.loads(stored_decisions[0]["related_signal_ids_json"]) == ["signal-1"]
    assert json.loads(stored_decisions[0]["action_json"])["path"] == "sample.txt"
    assert json.loads(stored_decisions[0]["proposed_action_json"])["type"] == "read_file"

    assert len(stored_dispatches) == 1
    assert stored_dispatches[0]["decision_id"] == stored_decisions[0]["id"]
    assert json.loads(stored_dispatches[0]["execution_result_json"])["success"] is True

    assert len(stored_evaluations) == 1
    assert stored_evaluations[0]["decision_id"] == stored_decisions[0]["id"]
    assert stored_evaluations[0]["dispatch_record_id"] == stored_dispatches[0]["id"]
    assert stored_evaluations[0]["next_step"] == "stop"

    assert trail.cycle is not None
    assert len(stored_cycles) == 1
    assert stored_cycles[0]["orchestration_run_id"] == "run-1"
    assert stored_cycles[0]["status"] == "stop"
