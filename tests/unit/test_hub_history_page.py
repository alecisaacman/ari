from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from ari_api import create_app as create_api_app
from ari_core import (
    RunSignalOrchestrationInput,
    get_latest_run_details,
    run_signal_orchestration,
)
from ari_hub import create_app as create_hub_app
from ari_hub.app import HubAPIError
from ari_memory import Base, DailyStateRepository, OpenLoopRepository, WeeklyStateRepository
from ari_memory.session import create_session_factory
from ari_state import AlertChannel, DailyState, OpenLoop, OpenLoopPriority, WeeklyState
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


class StubHistoryClient:
    def __init__(self, *, latest_run: dict[str, Any], comparison: dict[str, Any]) -> None:
        self.latest_run = latest_run
        self.comparison = comparison
        self.requested_dates: list[date] = []

    def get_latest_run(self, *, state_date: date) -> dict[str, Any]:
        self.requested_dates.append(state_date)
        return self.latest_run

    def compare_latest_two_runs(self, *, state_date: date) -> dict[str, Any]:
        self.requested_dates.append(state_date)
        return self.comparison


def test_hub_page_renders_expected_sections_and_change_markers() -> None:
    latest_run, comparison = _build_read_models()
    client = StubHistoryClient(latest_run=latest_run, comparison=comparison)
    app = create_hub_app(api_client=client)

    with TestClient(app) as test_client:
        response = test_client.get("/", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert client.requested_dates == [date(2026, 4, 10), date(2026, 4, 10)]
    body = response.text
    assert "Latest Run" in body
    assert "Latest vs Previous" in body
    assert "Linked Signals" in body
    assert "Linked Alerts" in body
    assert "State fingerprint changed:</strong> yes" in body
    assert "Reused signal ids" in body
    assert "New signal ids" in body
    assert "Reused alert ids" in body
    assert "New alert ids" in body
    assert '<span class="pill">reused</span>' in body
    assert '<span class="pill">new</span>' in body


def test_hub_page_consumes_canonical_api_payloads() -> None:
    session_factory = _build_changed_history_session_factory()
    api_app = create_api_app(session_factory)
    latest_run, comparison = _build_read_models(api_app)
    hub_app = create_hub_app(
        api_client=APIBackedHistoryClient(api_app),
    )

    with TestClient(hub_app) as client:
        response = client.get("/", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    body = response.text
    assert "ARI Hub" in body
    assert latest_run["run"]["run_id"] in body
    assert comparison["previous_run"]["run_id"] in body
    assert comparison["signals"][0]["summary"] in body
    assert comparison["alerts"][0]["title"] in body
    assert "Latest Summary" in body
    assert "Previous Summary" in body


def test_hub_page_returns_not_found_when_latest_run_is_missing() -> None:
    app = create_hub_app(
        api_client=MissingLatestHistoryClient(detail="No orchestration run found for 2026-04-11."),
    )

    with TestClient(app) as client:
        response = client.get("/", params={"state_date": "2026-04-11"})

    assert response.status_code == 404
    assert "No orchestration run found for 2026-04-11." in response.text


class APIBackedHistoryClient:
    def __init__(self, api_app: Any) -> None:
        self._client = TestClient(api_app)

    def get_latest_run(self, *, state_date: date) -> dict[str, Any]:
        return self._get("/orchestration-runs/latest", state_date)

    def compare_latest_two_runs(self, *, state_date: date) -> dict[str, Any]:
        return self._get("/orchestration-runs/compare-latest-two", state_date)

    def _get(self, path: str, state_date: date) -> dict[str, Any]:
        response = self._client.get(path, params={"state_date": state_date.isoformat()})
        response.raise_for_status()
        return response.json()


class MissingLatestHistoryClient:
    def __init__(self, *, detail: str) -> None:
        self._detail = detail

    def get_latest_run(self, *, state_date: date) -> dict[str, Any]:
        raise HubAPIError(status_code=404, detail=self._detail)

    def compare_latest_two_runs(self, *, state_date: date) -> dict[str, Any]:
        raise AssertionError(
            "compare_latest_two_runs should not be called when latest run is missing"
        )


def _build_read_models(
    api_app: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved_api_app = api_app or create_api_app(_build_changed_history_session_factory())
    client = TestClient(resolved_api_app)
    latest_response = client.get(
        "/orchestration-runs/latest",
        params={"state_date": "2026-04-10"},
    )
    comparison_response = client.get(
        "/orchestration-runs/compare-latest-two",
        params={"state_date": "2026-04-10"},
    )
    latest_response.raise_for_status()
    comparison_response.raise_for_status()
    return latest_response.json(), comparison_response.json()


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
        latest = get_latest_run_details(session, state_date=date(2026, 4, 10))
        assert latest is not None

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
