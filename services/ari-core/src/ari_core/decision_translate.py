from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ari_state import ActionType, ControllerDecision, DecisionType, ProposedAction

from ari_core.execution_types import ActionIntent, WorkerDecision, parse_worker_decision


def translate_worker_decision(decision: WorkerDecision | Mapping[str, Any]) -> list[ActionIntent]:
    if isinstance(decision, WorkerDecision):
        return list(decision.action_intents)
    return list(parse_worker_decision(decision).action_intents)


def build_controller_decision(
    decision: WorkerDecision | Mapping[str, Any],
) -> ControllerDecision:
    worker_decision = (
        decision
        if isinstance(decision, WorkerDecision)
        else parse_worker_decision(decision)
    )
    action_intents = [
        ProposedAction(
            action_type=intent.action_type,
            target=intent.target,
            instructions=intent.instructions,
        )
        for intent in worker_decision.action_intents
    ]
    requires_approval = any(
        intent.action_type in {ActionType.ASK_USER, ActionType.EDIT_FILE}
        for intent in action_intents
    )
    decision_type = DecisionType.ACT if action_intents else DecisionType.RESPOND
    return ControllerDecision(
        decision_summary=worker_decision.decision_summary,
        proposed_action=worker_decision.decision_summary,
        decision_type=decision_type,
        requires_approval=requires_approval,
        confidence=worker_decision.confidence,
        action_intents=action_intents,
    )
