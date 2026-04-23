from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ari_core.decision.engine import decide
from ari_core.decision.models import Decision


@dataclass
class MockSignal:
    id: str
    kind: str
    severity: str
    summary: str
    reason: str


@dataclass
class MockAlert:
    escalation_level: str
    source_signal_ids: list[str]


def test_decide_creates_a_decision_for_a_high_severity_signal() -> None:
    detected_at = datetime.now(timezone.utc)
    signal = MockSignal(
        id=f"signal-{int(detected_at.timestamp())}",
        kind="open_loop_accumulation",
        severity="critical",
        summary="12 open loops are active.",
        reason="Open loops have accumulated beyond the critical threshold.",
    )
    alert = MockAlert(
        escalation_level="interruptive",
        source_signal_ids=[signal.id],
    )

    decisions = decide([signal], [alert], {"state_date": "2026-04-21"})

    assert len(decisions) == 1
    decision = decisions[0]
    assert isinstance(decision, Decision)
    assert decision.intent == "inspect_workspace_surface"
    assert decision.decision_type == "act"
    assert decision.priority >= 90
    assert decision.action["type"] == "run_command"
    assert decision.proposed_action is not None
    assert decision.proposed_action.to_dict()["command"] == ["ls"]
    assert decision.related_signal_ids == (str(signal.id),)
    assert decision.confidence >= 0.8


def test_decide_keeps_weekly_drift_as_non_executable_investigation() -> None:
    signal = MockSignal(
        id="signal-weekly",
        kind="weekly_trajectory_drift",
        severity="warning",
        summary="Today's priorities are not reinforcing this week's outcomes.",
        reason="Day-level work is drifting from the current weekly commitments.",
    )
    alert = MockAlert(
        escalation_level="visible",
        source_signal_ids=[signal.id],
    )

    decisions = decide([signal], [alert], {"state_date": "2026-04-21"})

    assert len(decisions) == 1
    assert decisions[0].intent == "realign_daily_execution"
    assert decisions[0].decision_type == "defer"
    assert decisions[0].action["type"] == "investigate"
