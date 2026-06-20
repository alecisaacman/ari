from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ari_state import ActionType


@dataclass(frozen=True, slots=True)
class ActionIntent:
    action_type: ActionType
    target: str
    instructions: str


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    success: bool
    kind: str
    target: str
    summary: str
    details: str


@dataclass(frozen=True, slots=True)
class WorkerDecision:
    decision_summary: str
    confidence: float
    action_intents: tuple[ActionIntent, ...]


def parse_worker_decision(payload: Mapping[str, Any]) -> WorkerDecision:
    decision_summary = _require_str(payload, "decision_summary")
    confidence = _require_float(payload, "confidence")
    action_intents_payload = _require_list(payload, "action_intents")

    action_intents = tuple(
        ActionIntent(
            action_type=ActionType(_require_str(item, "action_type")),
            target=_require_str(item, "target"),
            instructions=_require_str(item, "instructions"),
        )
        for item in (
            _require_mapping(action_intent, "action_intents[]")
            for action_intent in action_intents_payload
        )
    )

    return WorkerDecision(
        decision_summary=decision_summary,
        confidence=confidence,
        action_intents=action_intents,
    )


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Worker field '{field_name}' must be an object.")
    return value


def _require_list(payload: Mapping[str, Any], field_name: str) -> list[object]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"Worker field '{field_name}' must be a list.")
    return value


def _require_str(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Worker field '{field_name}' must be a non-empty string.")
    return value


def _require_float(payload: Mapping[str, Any], field_name: str) -> float:
    value = payload.get(field_name)
    if not isinstance(value, int | float):
        raise ValueError(f"Worker field '{field_name}' must be numeric.")
    return float(value)
