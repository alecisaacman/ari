from datetime import UTC, date, datetime, timedelta

from ari_api import create_app
from ari_api.schemas import build_run_comparison_response, build_run_response
from ari_core import (
    RunSignalOrchestrationInput,
    compare_latest_two_runs,
    get_latest_run_details,
    get_previous_run_details,
    run_signal_orchestration,
)
from ari_memory import Base, DailyStateRepository, OpenLoopRepository, WeeklyStateRepository
from ari_memory.session import create_session_factory
from ari_state import AlertChannel, DailyState, OpenLoop, OpenLoopPriority, WeeklyState
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_latest_run_endpoint_returns_canonical_latest_history_read_model() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
    assert latest is not None
    expected = build_run_response(latest).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get("/orchestration-runs/latest", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert response.json() == expected


def test_previous_run_endpoint_returns_canonical_previous_history_read_model() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        previous = get_previous_run_details(session, state_date=date(2026, 4, 10))
    assert previous is not None
    expected = build_run_response(previous).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get(
            "/orchestration-runs/previous",
            params={"state_date": "2026-04-10"},
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_compare_latest_two_runs_endpoint_returns_canonical_comparison_read_model() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        comparison = compare_latest_two_runs(session, state_date=date(2026, 4, 10))
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        previous = get_previous_run_details(session, state_date=date(2026, 4, 10))
    assert comparison is not None
    assert latest is not None
    assert previous is not None
    expected = build_run_comparison_response(comparison, latest, previous).model_dump(
        mode="json"
    )

    with TestClient(app) as client:
        response = client.get(
            "/orchestration-runs/compare-latest-two",
            params={"state_date": "2026-04-10"},
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_compare_latest_two_runs_endpoint_exposes_expected_shape_fields() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get(
            "/orchestration-runs/compare-latest-two",
            params={"state_date": "2026-04-10"},
        )

    body = response.json()

    assert response.status_code == 200
    assert sorted(body) == [
        "alerts",
        "latest_run",
        "new_alert_ids",
        "new_signal_ids",
        "previous_run",
        "reused_alert_ids",
        "reused_signal_ids",
        "signals",
        "state_fingerprint_changed",
    ]
    assert sorted(body["latest_run"]) == [
        "alert_ids",
        "executed_at",
        "run_id",
        "signal_ids",
        "state_date",
        "state_fingerprint",
    ]
    assert sorted(body["previous_run"]) == [
        "alert_ids",
        "executed_at",
        "run_id",
        "signal_ids",
        "state_date",
        "state_fingerprint",
    ]
    assert sorted(body["signals"][0]) == [
        "detected_at",
        "evidence",
        "fingerprint",
        "id",
        "kind",
        "reason",
        "related_entity_id",
        "related_entity_type",
        "severity",
        "state_date",
        "summary",
    ]
    assert sorted(body["alerts"][0]) == [
        "channel",
        "created_at",
        "escalation_level",
        "fingerprint",
        "id",
        "message",
        "reason",
        "sent_at",
        "source_signal_ids",
        "state_date",
        "status",
        "title",
    ]


def _build_changed_history_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
