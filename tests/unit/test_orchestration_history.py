from datetime import UTC, date, datetime, timedelta

from ari_core import (
    RunSignalOrchestrationInput,
    compare_latest_two_runs,
    get_latest_run_details,
    get_previous_run_details,
    run_signal_orchestration,
)
from ari_memory import Base, DailyStateRepository, OpenLoopRepository, WeeklyStateRepository
from ari_state import AlertChannel, DailyState, OpenLoop, OpenLoopPriority, WeeklyState
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_history_loads_latest_and_previous_runs_for_state_date() -> None:
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

    with Session(engine) as session:
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        previous = get_previous_run_details(session, state_date=date(2026, 4, 10))

    assert latest is not None
    assert latest.run.id == second_result.run.id
    assert [signal.id for signal in latest.signals] == second_result.run.signal_ids
    assert [alert.id for alert in latest.alerts] == second_result.run.alert_ids

    assert previous is not None
    assert previous.run.id == first_result.run.id
    assert [signal.id for signal in previous.signals] == first_result.run.signal_ids
    assert [alert.id for alert in previous.alerts] == first_result.run.alert_ids


def test_history_comparison_of_unchanged_repeated_runs_marks_everything_reused() -> None:
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

    with Session(engine) as session:
        comparison = compare_latest_two_runs(session, state_date=date(2026, 4, 10))

    assert comparison is not None
    assert comparison.latest_run_id == second_result.run.id
    assert comparison.previous_run_id == first_result.run.id
    assert comparison.latest_executed_at == second_detected_at
    assert comparison.previous_executed_at == first_detected_at
    assert comparison.state_fingerprint_changed is False
    assert comparison.reused_signal_ids == second_result.run.signal_ids
    assert comparison.new_signal_ids == []
    assert comparison.reused_alert_ids == second_result.run.alert_ids
    assert comparison.new_alert_ids == []


def test_history_comparison_of_changed_run_distinguishes_reused_vs_new_outputs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    first_detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    second_detected_at = datetime(2026, 4, 10, 13, 0, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=first_detected_at)

    with Session(engine) as session:
        run_signal_orchestration(
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

    second_signals = {signal.kind: signal for signal in second_result.signals}
    second_alerts = {alert.title: alert for alert in second_result.alerts}

    with Session(engine) as session:
        comparison = compare_latest_two_runs(session, state_date=date(2026, 4, 10))

    assert comparison is not None
    assert comparison.state_fingerprint_changed is True
    assert comparison.reused_signal_ids == [
        second_signals["open_loop_accumulation"].id,
        second_signals["weekly_trajectory_drift"].id,
    ]
    assert comparison.new_signal_ids == [second_signals["elevated_stress"].id]
    assert comparison.reused_alert_ids == [
        second_alerts["Open loops are accumulating"].id,
        second_alerts["Weekly trajectory is drifting"].id,
    ]
    assert comparison.new_alert_ids == [second_alerts["Stress is elevated"].id]


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
