from datetime import UTC, date, datetime, timedelta

from ari_core import RunSignalOrchestrationInput, run_signal_orchestration
from ari_memory import (
    AlertRepository,
    Base,
    DailyStateRepository,
    OpenLoopRepository,
    OrchestrationRunRepository,
    SignalRepository,
    WeeklyStateRepository,
)
from ari_state import AlertChannel, DailyState, OpenLoop, OpenLoopPriority, WeeklyState
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_signal_orchestration_persists_signals_alerts_and_run_history_end_to_end() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=detected_at)

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
    assert result.run.state_date == date(2026, 4, 10)
    assert len(result.run.signal_ids) == 3
    assert len(result.run.alert_ids) == 3

    with Session(engine) as session:
        stored_signals = SignalRepository(session).list_recent(limit=10)
        stored_alerts = AlertRepository(session).list_recent(limit=10)
        stored_runs = OrchestrationRunRepository(session).list_for_state_date(date(2026, 4, 10))

    assert len(stored_signals) == 3
    assert len(stored_alerts) == 3
    assert len(stored_runs) == 1

    signal_reasons = {signal.id: signal.reason for signal in stored_signals}
    for alert in stored_alerts:
        assert len(alert.source_signal_ids) == 1
        source_signal_id = alert.source_signal_ids[0]
        assert source_signal_id in signal_reasons
        assert alert.reason == signal_reasons[source_signal_id]


def test_repeated_orchestration_run_reuses_identical_signals_and_alerts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    first_detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    second_detected_at = datetime(2026, 4, 10, 12, 30, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=first_detected_at)

    with Session(engine) as session:
        first_result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=first_detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )

    with Session(engine) as session:
        second_result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=second_detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )

    assert [signal.id for signal in second_result.signals] == [
        signal.id for signal in first_result.signals
    ]
    assert [alert.id for alert in second_result.alerts] == [
        alert.id for alert in first_result.alerts
    ]
    assert second_result.run.id != first_result.run.id
    assert second_result.run.signal_ids == first_result.run.signal_ids
    assert second_result.run.alert_ids == first_result.run.alert_ids

    with Session(engine) as session:
        stored_signals = SignalRepository(session).list_recent(limit=10)
        stored_alerts = AlertRepository(session).list_recent(limit=10)
        stored_runs = OrchestrationRunRepository(session).list_for_state_date(date(2026, 4, 10))

    assert len(stored_signals) == 3
    assert len(stored_alerts) == 3
    assert len(stored_runs) == 2
    assert stored_runs[0].state_fingerprint == stored_runs[1].state_fingerprint


def test_changed_state_creates_new_signal_and_alert_when_fingerprint_changes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    first_detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    second_detected_at = datetime(2026, 4, 10, 13, 0, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=first_detected_at)

    with Session(engine) as session:
        first_result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=first_detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )

    with Session(engine) as session:
        daily_states = DailyStateRepository(session)
        current = daily_states.get(date(2026, 4, 10))
        assert current is not None
        daily_states.upsert(
            current.model_copy(
                update={
                    "stress": 10,
                    "last_check_at": second_detected_at,
                }
            )
        )
        session.commit()

    with Session(engine) as session:
        second_result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=second_detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )

    first_signals = {signal.kind: signal for signal in first_result.signals}
    second_signals = {signal.kind: signal for signal in second_result.signals}
    assert second_result.run.state_fingerprint != first_result.run.state_fingerprint
    assert second_signals["elevated_stress"].id != first_signals["elevated_stress"].id
    assert second_signals["open_loop_accumulation"].id == first_signals[
        "open_loop_accumulation"
    ].id
    assert second_signals["weekly_trajectory_drift"].id == first_signals[
        "weekly_trajectory_drift"
    ].id

    first_alerts = {alert.title: alert for alert in first_result.alerts}
    second_alerts = {alert.title: alert for alert in second_result.alerts}
    assert second_alerts["Stress is elevated"].id != first_alerts["Stress is elevated"].id
    assert second_alerts["Open loops are accumulating"].id == first_alerts[
        "Open loops are accumulating"
    ].id
    assert second_alerts["Weekly trajectory is drifting"].id == first_alerts[
        "Weekly trajectory is drifting"
    ].id

    with Session(engine) as session:
        stored_signals = SignalRepository(session).list_recent(limit=10)
        stored_alerts = AlertRepository(session).list_recent(limit=10)

    assert len(stored_signals) == 4
    assert len(stored_alerts) == 4


def _seed_orchestration_state(engine: object, *, detected_at: datetime) -> None:
    Base.metadata.create_all(engine)

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
