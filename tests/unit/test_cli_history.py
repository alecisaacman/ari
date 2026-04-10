from datetime import UTC, date, datetime, timedelta
from io import StringIO

from ari_cli.history_cli import (
    handle_compare_latest_two_runs,
    handle_latest_run,
    handle_previous_run,
)
from ari_core import RunSignalOrchestrationInput, run_signal_orchestration
from ari_memory import Base, DailyStateRepository, OpenLoopRepository, WeeklyStateRepository
from ari_memory.session import create_session_factory
from ari_state import AlertChannel, DailyState, OpenLoop, OpenLoopPriority, WeeklyState
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def test_cli_latest_run_outputs_run_signals_and_alerts() -> None:
    session_factory = _build_history_session_factory()
    output = StringIO()

    exit_code = handle_latest_run(
        session_factory,
        state_date=date(2026, 4, 10),
        stdout=output,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "latest orchestration run for 2026-04-10" in rendered
    assert "signals: 3" in rendered
    assert "alerts: 3" in rendered
    assert "open_loop_accumulation" in rendered
    assert "Weekly trajectory is drifting" in rendered


def test_cli_previous_run_outputs_previous_run_for_state_date() -> None:
    session_factory = _build_changed_history_session_factory()
    output = StringIO()

    exit_code = handle_previous_run(
        session_factory,
        state_date=date(2026, 4, 10),
        stdout=output,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "previous orchestration run for 2026-04-10" in rendered
    assert "signals: 3" in rendered
    assert "alerts: 3" in rendered
    assert "Stress is elevated at 9/10." in rendered


def test_cli_compare_latest_two_runs_marks_reused_and_new_outputs() -> None:
    session_factory = _build_changed_history_session_factory()
    output = StringIO()

    exit_code = handle_compare_latest_two_runs(
        session_factory,
        state_date=date(2026, 4, 10),
        stdout=output,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "compare latest two orchestration runs for 2026-04-10" in rendered
    assert "state_fingerprint_changed: yes" in rendered
    assert "- reused warning open_loop_accumulation" in rendered
    assert "- new critical elevated_stress" in rendered
    assert "- reused visible hub Open loops are accumulating" in rendered
    assert "- new interruptive hub Stress is elevated" in rendered


def test_cli_explainability_output_reads_from_canonical_query_results() -> None:
    session_factory = _build_history_session_factory()
    output = StringIO()

    exit_code = handle_latest_run(
        session_factory,
        state_date=date(2026, 4, 10),
        stdout=output,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "Open loops have accumulated past the operating threshold of 7" in rendered
    assert "evidence: Open loop volume exceeds the baseline threshold." in rendered
    assert "Sample of active open loops contributing to the accumulation signal." in rendered
    assert "reason: No meaningful overlap was found between the weekly outcomes" in rendered
    assert "source_signals:" in rendered


def _build_history_session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=detected_at)

    with Session(engine) as session:
        run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )
        run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at + timedelta(minutes=30),
                alert_channel=AlertChannel.HUB,
            ),
        )

    return create_session_factory(engine)


def _build_changed_history_session_factory() -> sessionmaker[Session]:
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
        repository = DailyStateRepository(session)
        current = repository.get(date(2026, 4, 10))
        assert current is not None
        repository.upsert(
            current.model_copy(
                update={
                    "stress": 10,
                    "last_check_at": second_detected_at,
                }
            )
        )
        session.commit()

    with Session(engine) as session:
        run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=second_detected_at,
                alert_channel=AlertChannel.HUB,
            ),
        )

    return create_session_factory(engine)


def _seed_orchestration_state(engine: Engine, *, detected_at: datetime) -> None:
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
