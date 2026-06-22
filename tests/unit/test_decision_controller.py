from __future__ import annotations

from dataclasses import dataclass

from ari_core.decision.controller import DecisionController


@dataclass
class MockSignal:
    id: str
    kind: str
    severity: str
    summary: str
    reason: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None


def test_decision_controller_orders_decisions_by_priority() -> None:
    controller = DecisionController()
    signals = [
        MockSignal(
            id="signal-warning",
            kind="weekly_trajectory_drift",
            severity="warning",
            summary="Weekly drift is building.",
            reason="Today is pulling away from the weekly plan.",
        ),
        MockSignal(
            id="signal-critical",
            kind="open_loop_accumulation",
            severity="critical",
            summary="Open loops are critically high.",
            reason="The active workspace surface is overloaded.",
        ),
    ]

    result = controller.decide(
        signals=signals,
        state={"state_date": "2026-04-22", "open_loop_count": 12},
    )

    assert len(result.decisions) == 2
    assert result.decisions[0].intent == "inspect_workspace_surface"
    assert result.decisions[0].decision_type == "act"
    assert result.decisions[1].intent == "realign_daily_execution"
