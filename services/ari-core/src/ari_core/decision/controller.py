from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .engine import SignalLike, decide
from .models import Decision


@dataclass(frozen=True, slots=True)
class DecisionControllerResult:
    decisions: list[Decision]
    ignored_signal_ids: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DecisionController:
    def decide(
        self,
        *,
        signals: Sequence[SignalLike],
        alerts: Sequence[object] = (),
        state: Mapping[str, Any],
        run_context: Mapping[str, Any] | None = None,
    ) -> DecisionControllerResult:
        merged_state = dict(state)
        if run_context:
            merged_state["run_context"] = dict(run_context)

        decisions = decide(signals, alerts, merged_state)
        decided_signal_ids = {
            signal_id
            for decision in decisions
            for signal_id in decision.related_signal_ids
        }
        ignored_signal_ids = [
            str(signal.id)
            for signal in signals
            if str(signal.id) not in decided_signal_ids
        ]
        return DecisionControllerResult(
            decisions=decisions,
            ignored_signal_ids=ignored_signal_ids,
        )
