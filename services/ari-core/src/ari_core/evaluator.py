from __future__ import annotations

from ari_core.execution_types import ActionIntent, ActionType, ExecutionObservation


def evaluate_observations(
    intents: list[ActionIntent],
    observations: list[ExecutionObservation],
) -> str:
    if not intents:
        return "RETRY"

    if len(intents) != len(observations):
        return "RETRY"

    if any(intent.action_type == ActionType.ASK_USER for intent in intents):
        return "ASK_USER"

    if any(obs.kind == "ask_user" for obs in observations):
        return "ASK_USER"

    if all(obs.success for obs in observations):
        return "SUCCESS"

    return "RETRY"
