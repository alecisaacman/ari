from datetime import UTC, date, datetime, timedelta
from io import StringIO
from tempfile import NamedTemporaryFile

from ari_cli.main import run_cli
from ari_core import RunSignalOrchestrationInput, get_latest_run_details, run_signal_orchestration
from ari_memory import Base, DailyStateRepository, OpenLoopRepository, WeeklyStateRepository
from ari_memory.session import create_session_factory
from ari_state import (
    ActionType,
    AlertChannel,
    ControllerDecision,
    DailyState,
    OpenLoop,
    OpenLoopPriority,
    ProposedAction,
    WeeklyState,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def test_cli_lists_pending_approvals() -> None:
    session_factory, database_url = _build_pending_approval_session_factory()
    output = StringIO()

    exit_code = run_cli(
        ["approvals", "list", "--database-url", database_url],
        stdout=output,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "pending_approvals" in rendered
    assert "Inspect the test file with approval." in rendered


def test_cli_approve_resumes_pending_controller_cycle() -> None:
    session_factory, database_url = _build_pending_approval_session_factory()
    with session_factory() as session:
        details = get_latest_run_details(session, state_date=date(2026, 4, 10))
    assert details is not None
    assert details.pending_approval is not None

    output = StringIO()
    exit_code = run_cli(
        [
            "approvals",
            "approve",
            "--id",
            str(details.pending_approval.id),
            "--resolved-at",
            "2026-04-10T12:05:00+00:00",
            "--database-url",
            database_url,
        ],
        stdout=output,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "status: approved" in rendered
    assert "controller_cycle_state: completed" in rendered


def test_cli_deny_denies_pending_controller_cycle() -> None:
    session_factory, database_url = _build_pending_approval_session_factory()
    with session_factory() as session:
        details = get_latest_run_details(session, state_date=date(2026, 4, 10))
    assert details is not None
    assert details.pending_approval is not None

    output = StringIO()
    exit_code = run_cli(
        [
            "approvals",
            "deny",
            "--id",
            str(details.pending_approval.id),
            "--resolved-at",
            "2026-04-10T12:05:00+00:00",
            "--database-url",
            database_url,
        ],
        stdout=output,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "status: denied" in rendered
    assert "controller_cycle_state: denied" in rendered


def _build_pending_approval_session_factory() -> tuple[sessionmaker[Session], str]:
    handle = NamedTemporaryFile(suffix=".sqlite")
    database_url = f"sqlite+pysqlite:///{handle.name}"
    engine = create_engine(database_url, future=True)
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=detected_at)

    with Session(engine) as session:
        run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at,
                alert_channel=AlertChannel.HUB,
                controller_decision=_approval_controller_decision(),
            ),
        )

    factory = create_session_factory(engine)
    factory._tmp_handle = handle
    return factory, database_url


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


def _approval_controller_decision() -> ControllerDecision:
    return ControllerDecision(
        decision_summary="Inspect the test file with approval.",
        proposed_action="Inspect the test file with approval.",
        requires_approval=True,
        confidence=0.92,
        action_intents=[
            ProposedAction(
                action_type=ActionType.READ_FILE,
                target="tests/unit/test_models.py",
                instructions="Read the target test before changing anything.",
            )
        ],
    )
