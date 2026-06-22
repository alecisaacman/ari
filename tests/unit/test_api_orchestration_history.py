from datetime import UTC, date, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import UUID

from ari_api import create_app
from ari_api.schemas import (
    build_active_open_loops_response,
    build_alert_response,
    build_daily_state_response,
    build_run_comparison_response,
    build_run_response,
    build_signal_response,
    build_weekly_state_response,
)
from ari_cli.main import run_cli
from ari_core import (
    RunSignalOrchestrationInput,
    compare_latest_two_runs,
    get_alert_details,
    get_latest_run_details,
    get_previous_run_details,
    get_signal_details,
    run_signal_orchestration,
)
from ari_memory import (
    Base,
    DailyStateRepository,
    EventRepository,
    OpenLoopRepository,
    WeeklyStateRepository,
)
from ari_memory.session import create_session_factory
from ari_state import (
    ActionType,
    AlertChannel,
    ControllerDecision,
    DailyState,
    EventCategory,
    OpenLoop,
    OpenLoopPriority,
    OpenLoopStatus,
    ProposedAction,
    WeeklyState,
)
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
        "latest_controller_events",
        "latest_run",
        "new_alert_ids",
        "new_signal_ids",
        "previous_controller_events",
        "previous_run",
        "reused_alert_ids",
        "reused_signal_ids",
        "signals",
        "state_fingerprint_changed",
    ]
    assert sorted(body["latest_run"]) == [
        "alert_ids",
        "controller_cycle_state",
        "controller_trajectory",
        "executed_at",
        "pending_approval",
        "run_id",
        "signal_ids",
        "state_date",
        "state_fingerprint",
    ]
    assert sorted(body["previous_run"]) == [
        "alert_ids",
        "controller_cycle_state",
        "controller_trajectory",
        "executed_at",
        "pending_approval",
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


def test_latest_run_endpoint_exposes_controller_trajectory_when_present() -> None:
    session_factory = _build_controlled_history_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get("/orchestration-runs/latest", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    trajectory = response.json()["run"]["controller_trajectory"]
    assert trajectory is not None
    assert trajectory["controller_outcome"] == "success"
    assert trajectory["authority_result"]["outcome"] == "allow"
    assert trajectory["action_plan"]["is_bounded"] is True
    assert trajectory["worker_run"]["observations"][0]["kind"] == "read_file"


def test_latest_run_endpoint_exposes_ordered_controller_events_when_present() -> None:
    session_factory = _build_controlled_history_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get("/orchestration-runs/latest", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    events = response.json()["controller_events"]
    assert [event["sequence_number"] for event in events] == list(range(7))
    assert [event["event_type"] for event in events] == [
        "observation_intake",
        "decision_selected",
        "authority_result",
        "dispatch_started",
        "dispatch_result",
        "verification_result",
        "controller_outcome",
    ]
    assert events[0]["payload"]["signal_ids"]
    assert events[-1]["payload"]["controller_outcome"] == "success"


def test_pending_approvals_endpoint_lists_waiting_approvals() -> None:
    session_factory = _build_pending_approval_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get("/pending-approvals")

    assert response.status_code == 200
    approvals = response.json()["approvals"]
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending"
    assert "requiring approval" in approvals[0]["reason"].lower()


def test_pending_approval_approve_endpoint_resumes_controller_cycle() -> None:
    session_factory = _build_pending_approval_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        pending = get_latest_run_details(session, state_date=date(2026, 4, 10))
    assert pending is not None
    assert pending.pending_approval is not None

    with TestClient(app) as client:
        response = client.post(
            f"/pending-approvals/{pending.pending_approval.id}/approve",
            json={"resolved_at": "2026-04-10T12:05:00Z"},
        )
        latest = client.get("/orchestration-runs/latest", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    latest_run = latest.json()["run"]
    assert latest_run["controller_cycle_state"] == "completed"
    assert latest_run["pending_approval"]["status"] == "approved"
    assert latest.json()["controller_events"][4]["event_type"] == "approval_granted"
    assert latest.json()["controller_events"][5]["event_type"] == "controller_resumed"


def test_pending_approval_deny_endpoint_denies_controller_cycle() -> None:
    session_factory = _build_pending_approval_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        pending = get_latest_run_details(session, state_date=date(2026, 4, 10))
    assert pending is not None
    assert pending.pending_approval is not None

    with TestClient(app) as client:
        response = client.post(
            f"/pending-approvals/{pending.pending_approval.id}/deny",
            json={"resolved_at": "2026-04-10T12:05:00Z"},
        )
        latest = client.get("/orchestration-runs/latest", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    latest_run = latest.json()["run"]
    assert latest_run["controller_cycle_state"] == "denied"
    assert latest_run["pending_approval"]["status"] == "denied"
    assert latest.json()["controller_events"][-2]["event_type"] == "approval_denied"
    assert latest.json()["controller_events"][-1]["event_type"] == "controller_outcome"


def test_current_daily_state_endpoint_returns_canonical_daily_state() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        state = DailyStateRepository(session).get(date(2026, 4, 10))
    assert state is not None
    expected = build_daily_state_response(state).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get("/daily-states/current", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert response.json() == expected


def test_current_weekly_state_endpoint_uses_corresponding_week_start() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        state = WeeklyStateRepository(session).get(date(2026, 4, 6))
    assert state is not None
    expected = build_weekly_state_response(state).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get("/weekly-states/current", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert response.json() == expected


def test_active_open_loops_endpoint_returns_open_loops_only() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        loops = OpenLoopRepository(session).list_open()
    expected = build_active_open_loops_response(loops).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get("/open-loops/active")

    assert response.status_code == 200
    assert response.json() == expected
    assert response.json()["loops"]
    assert all(loop["status"] != "closed" for loop in response.json()["loops"])


def test_write_daily_state_endpoint_persists_canonical_state_and_event() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.put(
            "/daily-states/current",
            params={"state_date": "2026-04-10"},
            json={
                "priorities": ["Ship API write surface", "Preserve core seam"],
                "win_condition": "Keep API transport thin.",
                "movement": True,
                "stress": 5,
                "next_action": "Add endpoint coverage.",
                "checked_at": "2026-04-10T14:30:00Z",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-04-10",
        "priorities": ["Ship API write surface", "Preserve core seam"],
        "win_condition": "Keep API transport thin.",
        "movement": True,
        "stress": 5,
        "next_action": "Add endpoint coverage.",
        "last_check_at": "2026-04-10T14:30:00Z",
    }

    with session_factory() as session:
        state = DailyStateRepository(session).get(date(2026, 4, 10))
        events = EventRepository(session).list_recent(limit=1)

    assert state is not None
    assert state.priorities == ["Ship API write surface", "Preserve core seam"]
    assert state.next_action == "Add endpoint coverage."
    assert events[0].category == EventCategory.DAILY_UPDATE
    assert events[0].source == "ari.api.daily_state"
    assert events[0].payload["date"] == "2026-04-10"


def test_weekly_write_endpoints_preserve_routine_semantics_and_emit_events() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        plan_response = client.put(
            "/weekly-states/plan",
            params={"state_date": "2026-04-10"},
            json={
                "outcomes": ["Finish shared write path"],
                "cannot_drift": ["No API business logic fork"],
                "blockers": ["Write endpoints still missing"],
                "reviewed_at": "2026-04-10T09:00:00Z",
            },
        )
        reflection_response = client.put(
            "/weekly-states/reflection",
            params={"state_date": "2026-04-10"},
            json={
                "lesson": "The transport stays honest when core owns mutation.",
                "reviewed_at": "2026-04-10T18:00:00Z",
            },
        )

    assert plan_response.status_code == 200
    assert reflection_response.status_code == 200
    assert reflection_response.json()["outcomes"] == ["Finish shared write path"]
    assert reflection_response.json()["cannot_drift"] == ["No API business logic fork"]
    assert reflection_response.json()["blockers"] == ["Write endpoints still missing"]
    assert (
        reflection_response.json()["lesson"]
        == "The transport stays honest when core owns mutation."
    )

    with session_factory() as session:
        state = WeeklyStateRepository(session).get(date(2026, 4, 6))
        events = EventRepository(session).list_recent(limit=2)

    assert state is not None
    assert state.outcomes == ["Finish shared write path"]
    assert state.cannot_drift == ["No API business logic fork"]
    assert state.blockers == ["Write endpoints still missing"]
    assert state.lesson == "The transport stays honest when core owns mutation."
    assert [event.category for event in events] == [
        EventCategory.WEEKLY_REFLECTION,
        EventCategory.WEEKLY_PLANNING,
    ]
    assert [event.source for event in events] == [
        "ari.api.weekly_reflection",
        "ari.api.weekly_plan",
    ]


def test_open_loop_write_endpoints_manage_canonical_lifecycle_and_events() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        add_response = client.post(
            "/open-loops",
            json={
                "title": "Close API write gap",
                "source": "operator",
                "priority": "high",
                "notes": "Must stay on ari_core.state.",
                "opened_at": "2026-04-10T12:00:00Z",
            },
        )

    assert add_response.status_code == 201
    loop_id = add_response.json()["id"]

    with TestClient(app) as client:
        resolve_response = client.post(
            f"/open-loops/{loop_id}/resolve",
            json={"resolved_at": "2026-04-10T13:00:00Z"},
        )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "closed"

    with session_factory() as session:
        loop = OpenLoopRepository(session).get(UUID(loop_id))
        events = EventRepository(session).list_recent(limit=2)

    assert loop is not None
    assert loop.status == OpenLoopStatus.CLOSED
    assert [event.category for event in events] == [
        EventCategory.OPEN_LOOP_RESOLVE,
        EventCategory.OPEN_LOOP_ADD,
    ]
    assert [event.source for event in events] == [
        "ari.api.open_loops",
        "ari.api.open_loops",
    ]


def test_api_write_and_cli_read_share_canonical_mutation_seam(tmp_path: Path) -> None:
    database_url = _prepare_file_database(tmp_path / "shared-seam.db")
    engine = create_engine(database_url, future=True)
    session_factory = create_session_factory(engine)
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.put(
            "/daily-states/current",
            params={"state_date": "2026-04-10"},
            json={
                "priorities": ["One canon"],
                "next_action": "Read it through CLI.",
                "checked_at": "2026-04-10T08:00:00Z",
            },
        )

    assert response.status_code == 200

    stdout = StringIO()
    exit_code = run_cli(
        [
            "today",
            "read",
            "--state-date",
            "2026-04-10",
            "--database-url",
            database_url,
        ],
        stdout=stdout,
    )

    assert exit_code == 0
    assert "One canon" in stdout.getvalue()
    assert "Read it through CLI." in stdout.getvalue()


def test_signal_detail_endpoint_returns_canonical_signal_read_model() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        assert latest is not None
        signal = get_signal_details(session, signal_id=latest.signals[0].id)
    assert signal is not None
    expected = build_signal_response(signal).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get(f"/signals/{signal.id}")

    assert response.status_code == 200
    assert response.json() == expected


def test_alert_detail_endpoint_returns_canonical_alert_read_model() -> None:
    session_factory = _build_changed_history_session_factory()
    app = create_app(session_factory)

    with session_factory() as session:
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        assert latest is not None
        alert = get_alert_details(session, alert_id=latest.alerts[0].id)
    assert alert is not None
    expected = build_alert_response(alert).model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get(f"/alerts/{alert.id}")

    assert response.status_code == 200
    assert response.json() == expected


def test_current_daily_state_endpoint_returns_not_found_when_missing() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get("/daily-states/current", params={"state_date": "2026-04-11"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No daily state found for 2026-04-11."}


def test_signal_detail_endpoint_returns_not_found_when_missing() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)
    missing_id = "11111111-1111-1111-1111-111111111111"

    with TestClient(app) as client:
        response = client.get(f"/signals/{missing_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"No signal found for {missing_id}."}


def test_alert_detail_endpoint_returns_not_found_when_missing() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)
    missing_id = "22222222-2222-2222-2222-222222222222"

    with TestClient(app) as client:
        response = client.get(f"/alerts/{missing_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"No alert found for {missing_id}."}


def test_current_weekly_state_endpoint_returns_not_found_when_missing() -> None:
    session_factory = _build_daily_only_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get("/weekly-states/current", params={"state_date": "2026-04-11"})

    assert response.status_code == 404
    assert response.json() == {
        "detail": "No weekly state found for the week of 2026-04-06."
    }


def test_active_open_loops_endpoint_returns_empty_list_when_none_are_active() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.get("/open-loops/active")

    assert response.status_code == 200
    assert response.json() == {"loops": []}


def test_open_loop_resolve_endpoint_returns_not_found_when_missing() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)
    missing_id = "33333333-3333-3333-3333-333333333333"

    with TestClient(app) as client:
        response = client.post(
            f"/open-loops/{missing_id}/resolve",
            json={"resolved_at": "2026-04-10T13:00:00Z"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": f"No open loop found for {missing_id}."}


def test_daily_write_endpoint_rejects_invalid_payload() -> None:
    session_factory = _build_empty_session_factory()
    app = create_app(session_factory)

    with TestClient(app) as client:
        response = client.put(
            "/daily-states/current",
            params={"state_date": "2026-04-10"},
            json={"stress": 11},
        )

    assert response.status_code == 422


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


def _build_empty_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def _build_controlled_history_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    detected_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    _seed_orchestration_state(engine, detected_at=detected_at)

    with Session(engine) as session:
        run_signal_orchestration(
            session,
            RunSignalOrchestrationInput(
                state_date=date(2026, 4, 10),
                detected_at=detected_at,
                alert_channel=AlertChannel.HUB,
                controller_decision=_controller_decision(),
            ),
        )

    return create_session_factory(engine)


def _build_pending_approval_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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

    return create_session_factory(engine)


def _prepare_file_database(path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return database_url


def _build_daily_only_session_factory() -> sessionmaker[Session]:
    session_factory = _build_empty_session_factory()
    with session_factory() as session:
        DailyStateRepository(session).upsert(
            DailyState(
                date=date(2026, 4, 11),
                priorities=["Stabilize read surface"],
                win_condition="Keep the slice thin.",
                movement=None,
                stress=None,
                next_action="Check the API contract.",
            )
        )
        session.commit()
    return session_factory


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


def _controller_decision() -> ControllerDecision:
    return ControllerDecision(
        decision_summary="Inspect the test file.",
        proposed_action="Inspect the test file.",
        confidence=0.92,
        action_intents=[
            ProposedAction(
                action_type=ActionType.READ_FILE,
                target="tests/unit/test_models.py",
                instructions="Read the target test before changing anything.",
            )
        ],
    )


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
