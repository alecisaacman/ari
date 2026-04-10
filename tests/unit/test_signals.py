from datetime import UTC, date, datetime, timedelta

from ari_signals import generate_alerts, generate_signals
from ari_state import (
    AlertChannel,
    AlertEscalationLevel,
    DailyState,
    OpenLoop,
    OpenLoopPriority,
    SignalSeverity,
    WeeklyState,
)


def test_generate_signals_produces_explainable_initial_signal_set() -> None:
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    daily_state = DailyState(
        date=date(2026, 4, 10),
        priorities=["Inbox cleanup", "Admin sweep"],
        win_condition="Clear reactive work.",
        movement=False,
        stress=8,
        next_action="Triage the backlog.",
        last_check_at=detected_at,
    )
    weekly_state = WeeklyState(
        week_start=date(2026, 4, 7),
        outcomes=["Launch the routine spine", "Lock explainable alerts"],
        cannot_drift=["Canonical state consistency"],
        blockers=["Unclear naming"],
        last_review_at=detected_at,
    )
    open_loops = [
        OpenLoop(
            title=f"Loop {index}",
            priority=OpenLoopPriority.HIGH if index < 2 else OpenLoopPriority.MEDIUM,
            source="test",
            opened_at=detected_at - timedelta(days=10 + index),
        )
        for index in range(7)
    ]

    signals = generate_signals(
        detected_at=detected_at,
        daily_state=daily_state,
        weekly_state=weekly_state,
        open_loops=open_loops,
    )

    signal_map = {signal.kind: signal for signal in signals}

    assert set(signal_map) == {
        "open_loop_accumulation",
        "weekly_trajectory_drift",
        "elevated_stress",
    }
    assert signal_map["open_loop_accumulation"].severity == SignalSeverity.WARNING
    assert signal_map["open_loop_accumulation"].evidence[0].payload["total_open_loops"] == 7
    assert signal_map["weekly_trajectory_drift"].evidence[0].payload["outcomes"] == [
        "Launch the routine spine",
        "Lock explainable alerts",
    ]
    assert signal_map["elevated_stress"].evidence[0].payload["stress"] == 8


def test_generate_alerts_preserves_signal_explainability() -> None:
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    daily_state = DailyState(
        date=date(2026, 4, 10),
        stress=9,
        next_action="Pause and re-plan.",
    )
    signal = generate_signals(detected_at=detected_at, daily_state=daily_state)[0]

    alerts = generate_alerts(
        [signal],
        created_at=detected_at,
        channel=AlertChannel.TERMINAL,
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.channel == AlertChannel.TERMINAL
    assert alert.escalation_level == AlertEscalationLevel.INTERRUPTIVE
    assert alert.reason == signal.reason
    assert alert.source_signal_ids == [signal.id]
