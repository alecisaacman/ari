from datetime import UTC, date, datetime, timedelta

from ari_core import RunSignalOrchestrationInput, run_signal_orchestration
from ari_memory import (
    AlertRepository,
    Base,
    DailyStateRepository,
    OpenLoopRepository,
    SignalRepository,
    WeeklyStateRepository,
)
from ari_state import AlertChannel, DailyState, OpenLoop, OpenLoopPriority, WeeklyState
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_signal_orchestration_persists_signals_and_alerts_end_to_end() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)

    with Session(engine) as session:
        DailyStateRepository(session).upsert(
            DailyState(
                date=date(2026, 4, 10),
                priorities=["Inbox cleanup", "Admin sweep"],
                win_condition="Clear reactive work.",
                movement=False,
                stress=9,
                next_action="Triage the backlog.",
                last_check_at=detected_at,
            )
        )
        WeeklyStateRepository(session).upsert(
            WeeklyState(
                week_start=date(2026, 4, 6),
                outcomes=["Launch the routine spine", "Lock explainable alerts"],
                cannot_drift=["Canonical state consistency"],
                blockers=["Unclear naming"],
                last_review_at=detected_at,
            )
        )
        open_loop_repository = OpenLoopRepository(session)
        for index in range(7):
            open_loop_repository.upsert(
                OpenLoop(
                    title=f"Loop {index}",
                    priority=(
                        OpenLoopPriority.HIGH if index < 2 else OpenLoopPriority.MEDIUM
                    ),
                    source="test",
                    opened_at=detected_at - timedelta(days=10 + index),
                )
            )
        session.commit()

    with Session(engine) as session:
        result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )

    assert {signal.kind for signal in result.signals} == {
        "open_loop_accumulation",
        "weekly_trajectory_drift",
        "elevated_stress",
    }
    assert len(result.alerts) == 3

    with Session(engine) as session:
        stored_signals = SignalRepository(session).list_recent(limit=10)
        stored_alerts = AlertRepository(session).list_recent(limit=10)

    assert len(stored_signals) == 3
    assert len(stored_alerts) == 3

    signal_reasons = {signal.id: signal.reason for signal in stored_signals}
    for alert in stored_alerts:
        assert len(alert.source_signal_ids) == 1
        source_signal_id = alert.source_signal_ids[0]
        assert source_signal_id in signal_reasons
        assert alert.reason == signal_reasons[source_signal_id]
