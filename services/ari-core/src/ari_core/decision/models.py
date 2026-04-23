from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


DecisionType = Literal["act", "escalate", "defer", "ignore"]


@dataclass(frozen=True, slots=True)
class ProposedAction:
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            **self.payload,
        }


@dataclass(frozen=True, slots=True)
class Decision:
    intent: str
    decision_type: DecisionType
    priority: int
    reasoning: str
    confidence: float
    related_signal_ids: tuple[str, ...] = ()
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    proposed_action: ProposedAction | None = None
    requires_approval: bool = False
    id: str = field(default_factory=lambda: f"decision-{uuid4()}")
    created_at: str = field(default_factory=lambda: _now_iso())

    @property
    def action(self) -> dict[str, Any]:
        return {} if self.proposed_action is None else self.proposed_action.to_dict()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["proposed_action"] = None if self.proposed_action is None else self.proposed_action.to_dict()
        payload["action"] = self.action
        return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
