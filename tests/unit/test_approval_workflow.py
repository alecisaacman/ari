from datetime import UTC, date, datetime, timedelta

from ari_core import (
    RunSignalOrchestrationInput,
    approve_pending_approval,
    deny_pending_approval,
    get_latest_run_details,
    list_pending_approvals,
    run_signal_orchestration,
)
from ari_memory import Base, DailyStateRepository, OpenLoopRepository, WeeklyStateRepository
from ari_state import (
    ActionType,
    AlertChannel,
    ControllerDecision,
    ControllerEventType,
    DailyState,
    OpenLoop,
    OpenLoopPriority,
    ProposedAction,
    WeeklyState,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_require_approval_cycle_persists_pending_approval_and_waiting_state() -> None:
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
                controller_decision=_approval_controller_decision(),
            ),
        )

    assert result.pending_approval is not None
    assert result.run.controller_cycle_state == "waiting_for_approval"
    assert [event.event_type for event in result.controller_events or []] == [
        ControllerEventType.OBSERVATION_INTAKE,
        ControllerEventType.DECISION_SELECTED,
        ControllerEventType.AUTHORITY_RESULT,
        ControllerEventType.APPROVAL_REQUESTED,
    ]

    with Session(engine) as session:
        approvals = list_pending_approvals(session)

    assert [approval.id for approval in approvals] == [result.pending_approval.id]


def test_approved_pending_cycle_resumes_and_completes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    approved_at = datetime(2026, 4, 10, 12, 5, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=detected_at)

    with Session(engine) as session:
        result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at,
                alert_channel=AlertChannel.HUB,
                controller_decision=_approval_controller_decision(),
            ),
        )
    assert result.pending_approval is not None

    with Session(engine) as session:
        resumed = approve_pending_approval(
            session,
            approval_id=result.pending_approval.id,
            approved_at=approved_at,
        )

    assert resumed is not None
    assert resumed.approval.status == "approved"
    assert resumed.run.controller_cycle_state == "completed"
    assert resumed.run.controller_trajectory is not None
    assert resumed.run.controller_trajectory.controller_outcome == "success"

    with Session(engine) as session:
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        approvals = list_pending_approvals(session)

    assert latest is not None
    assert approvals == []
    assert [event.event_type for event in latest.controller_events] == [
        ControllerEventType.OBSERVATION_INTAKE,
        ControllerEventType.DECISION_SELECTED,
        ControllerEventType.AUTHORITY_RESULT,
        ControllerEventType.APPROVAL_REQUESTED,
        ControllerEventType.APPROVAL_GRANTED,
        ControllerEventType.CONTROLLER_RESUMED,
        ControllerEventType.DISPATCH_STARTED,
        ControllerEventType.DISPATCH_RESULT,
        ControllerEventType.VERIFICATION_RESULT,
        ControllerEventType.CONTROLLER_OUTCOME,
    ]


def test_denied_pending_cycle_records_denial_and_stops() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    denied_at = datetime(2026, 4, 10, 12, 5, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=detected_at)

    with Session(engine) as session:
        result = run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at,
                alert_channel=AlertChannel.HUB,
                controller_decision=_approval_controller_decision(),
            ),
        )
    assert result.pending_approval is not None

    with Session(engine) as session:
        denied = deny_pending_approval(
            session,
            approval_id=result.pending_approval.id,
            denied_at=denied_at,
        )

    assert denied is not None
    assert denied.approval.status == "denied"
    assert denied.run.controller_cycle_state == "denied"
    assert denied.run.controller_trajectory is not None
    assert denied.run.controller_trajectory.controller_outcome == "denied"

    with Session(engine) as session:
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        approvals = list_pending_approvals(session)

    assert latest is not None
    assert approvals == []
    assert [event.event_type for event in latest.controller_events] == [
        ControllerEventType.OBSERVATION_INTAKE,
        ControllerEventType.DECISION_SELECTED,
        ControllerEventType.AUTHORITY_RESULT,
        ControllerEventType.APPROVAL_REQUESTED,
        ControllerEventType.APPROVAL_DENIED,
        ControllerEventType.CONTROLLER_OUTCOME,
    ]


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
