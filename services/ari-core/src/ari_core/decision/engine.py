from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .models import Decision, ProposedAction


class SignalLike(Protocol):
    id: object
    kind: str
    severity: object
    summary: str
    reason: str
    related_entity_type: str | None
    related_entity_id: object | None


def decide(
    signals: Sequence[SignalLike],
    alerts: Sequence[object],
    state: Mapping[str, Any],
) -> list[Decision]:
    del alerts
    decisions: list[Decision] = []
    repeated_signal_ids = {
        str(item)
        for item in state.get("repeated_signal_ids", [])
        if str(item)
    }

    for signal in signals:
        decision = _decision_for_signal(
            signal,
            state=state,
            repeated=str(signal.id) in repeated_signal_ids,
        )
        if decision is not None:
            decisions.append(decision)

    return sorted(decisions, key=lambda item: (-item.priority, -item.confidence, item.intent))


def _decision_for_signal(
    signal: SignalLike,
    *,
    state: Mapping[str, Any],
    repeated: bool,
) -> Decision | None:
    severity = str(signal.severity)
    if severity not in {"warning", "critical"}:
        return Decision(
            intent="ignore_low_value_signal",
            decision_type="ignore",
            priority=10,
            reasoning=f"{signal.summary} {signal.reason} ARI is ignoring this low-severity signal for now.",
            confidence=0.91,
            related_signal_ids=(str(signal.id),),
            related_entity_type=signal.related_entity_type,
            related_entity_id=None if signal.related_entity_id is None else str(signal.related_entity_id),
        )

    state_date = state.get("state_date")
    open_loop_count = int(state.get("open_loop_count", 0) or 0)
    priority = 92 if severity == "critical" else 68
    confidence = 0.87 if severity == "critical" else 0.74

    if signal.kind == "open_loop_accumulation":
        if severity == "critical" or repeated:
            return Decision(
                intent="inspect_workspace_surface",
                decision_type="act",
                priority=priority + (4 if repeated else 0),
                reasoning=(
                    f"{signal.summary} {signal.reason} "
                    "The active loop surface needs immediate inspection before more drift accumulates."
                ),
                confidence=confidence,
                related_signal_ids=(str(signal.id),),
                related_entity_type="workspace",
                related_entity_id=None if state_date is None else str(state_date),
                proposed_action=ProposedAction(
                    "run_command",
                    {
                        "command": ["ls"],
                        "signal_id": str(signal.id),
                        "state_date": None if state_date is None else str(state_date),
                        "open_loop_count": open_loop_count,
                    },
                ),
                requires_approval=False,
            )
        return Decision(
            intent="defer_open_loop_cleanup",
            decision_type="defer",
            priority=priority,
            reasoning=(
                f"{signal.summary} {signal.reason} "
                "The accumulation matters, but the next step can wait for a bounded review pass."
            ),
            confidence=confidence - 0.04,
            related_signal_ids=(str(signal.id),),
            related_entity_type="workspace",
            related_entity_id=None if state_date is None else str(state_date),
            proposed_action=ProposedAction(
                "investigate",
                {
                    "target": "open_loops",
                    "signal_id": str(signal.id),
                    "state_date": None if state_date is None else str(state_date),
                },
            ),
        )

    if signal.kind == "weekly_trajectory_drift":
        decision_type = "escalate" if repeated else "defer"
        return Decision(
            intent="realign_daily_execution",
            decision_type=decision_type,
            priority=priority + (6 if repeated else 0),
            reasoning=(
                f"{signal.summary} {signal.reason} "
                + (
                    "This has repeated, so ARI should escalate strategic attention instead of quietly deferring it."
                    if repeated
                    else "ARI should defer immediate action and queue a bounded alignment review."
                )
            ),
            confidence=confidence - 0.02,
            related_signal_ids=(str(signal.id),),
            related_entity_type="weekly_state",
            related_entity_id=None if state_date is None else str(state_date),
            proposed_action=ProposedAction(
                "investigate",
                {
                    "target": "weekly_alignment",
                    "signal_id": str(signal.id),
                    "state_date": None if state_date is None else str(state_date),
                },
            ),
            requires_approval=decision_type == "escalate",
        )

    if signal.kind == "elevated_stress":
        return Decision(
            intent="de_risk_operator_load",
            decision_type="escalate" if severity == "critical" else "defer",
            priority=priority + 3,
            reasoning=(
                f"{signal.summary} {signal.reason} "
                "ARI should reduce operational risk before adding more execution pressure."
            ),
            confidence=confidence,
            related_signal_ids=(str(signal.id),),
            related_entity_type=signal.related_entity_type,
            related_entity_id=None if signal.related_entity_id is None else str(signal.related_entity_id),
            proposed_action=ProposedAction(
                "investigate",
                {
                    "target": "operator_load",
                    "signal_id": str(signal.id),
                    "state_date": None if state_date is None else str(state_date),
                },
            ),
            requires_approval=severity == "critical",
        )

    return Decision(
        intent="inspect_signal",
        decision_type="defer",
        priority=priority - 8,
        reasoning=f"{signal.summary} {signal.reason} ARI should inspect this signal before taking stronger action.",
        confidence=confidence - 0.08,
        related_signal_ids=(str(signal.id),),
        related_entity_type=signal.related_entity_type,
        related_entity_id=None if signal.related_entity_id is None else str(signal.related_entity_id),
        proposed_action=ProposedAction(
            "investigate",
            {
                "target": signal.kind,
                "signal_id": str(signal.id),
                "state_date": None if state_date is None else str(state_date),
            },
        ),
    )
