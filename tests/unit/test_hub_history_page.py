from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ari_api import create_app as create_api_app
from ari_core import (
    RunSignalOrchestrationInput,
    get_latest_run_details,
    run_signal_orchestration,
)
from ari_hub import app as hub_app_module
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
    def __init__(
        self,
        *,
        latest_run: dict[str, Any],
        comparison: dict[str, Any],
        daily_state: dict[str, Any],
        weekly_state: dict[str, Any],
        active_open_loops: dict[str, Any],
    ) -> None:
        self.latest_run = latest_run
        self.comparison = comparison
        self.daily_state = daily_state
        self.weekly_state = weekly_state
        self.active_open_loops = active_open_loops
        signals = comparison.get("signals", latest_run.get("signals", []))
        alerts = comparison.get("alerts", latest_run.get("alerts", []))
        self.signal_details = {
            signal["id"]: signal for signal in signals
        }
        self.alert_details = {
            alert["id"]: alert for alert in alerts
        }
        self.requested_dates: list[date] = []

    def get_latest_run(self, *, state_date: date) -> dict[str, Any]:
        self.requested_dates.append(state_date)
        return self.latest_run

    def compare_latest_two_runs(self, *, state_date: date) -> dict[str, Any]:
        self.requested_dates.append(state_date)
        return self.comparison

    def get_current_daily_state(self, *, state_date: date) -> dict[str, Any]:
        self.requested_dates.append(state_date)
        return self.daily_state

    def get_current_weekly_state(self, *, state_date: date) -> dict[str, Any]:
        self.requested_dates.append(state_date)
        return self.weekly_state

    def get_active_open_loops(self) -> dict[str, Any]:
        return self.active_open_loops

    def get_signal_detail(self, *, signal_id: Any) -> dict[str, Any]:
        return self.signal_details[str(signal_id)]

    def get_alert_detail(self, *, alert_id: Any) -> dict[str, Any]:
        return self.alert_details[str(alert_id)]


def test_hub_page_renders_expected_sections_and_change_markers() -> None:
    latest_run, comparison, daily_state, weekly_state, active_open_loops = _build_read_models()
    client = StubHistoryClient(
        latest_run=latest_run,
        comparison=comparison,
        daily_state=daily_state,
        weekly_state=weekly_state,
        active_open_loops=active_open_loops,
    )
    app = create_hub_app(api_client=client)

    with TestClient(app) as test_client:
        response = test_client.get("/", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert client.requested_dates == [
        date(2026, 4, 10),
        date(2026, 4, 10),
        date(2026, 4, 10),
        date(2026, 4, 10),
    ]
    body = response.text
    assert "Latest Run" in body
    assert "Latest vs Previous" in body
    assert "Current Operational State" in body
    assert "Weekly Trajectory" in body
    assert "Active Open Loops" in body
    assert "Linked Signals" in body
    assert "Linked Alerts" in body
    assert "Inbox cleanup" in body
    assert "Launch the routine spine" in body
    assert "Loop 0" in body
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
    latest_run, comparison, daily_state, weekly_state, active_open_loops = _build_read_models(
        api_app
    )
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
    assert daily_state["next_action"] in body
    assert weekly_state["week_start"] in body
    assert active_open_loops["loops"][0]["title"] in body
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


def test_hub_page_renders_empty_weekly_state_and_open_loops() -> None:
    latest_run, comparison, daily_state, _, _ = _build_read_models()
    app = create_hub_app(
        api_client=StateGapHistoryClient(
            latest_run=latest_run,
            comparison=comparison,
            daily_state=daily_state,
            weekly_detail="No weekly state found for the week of 2026-04-06.",
        ),
    )

    with TestClient(app) as client:
        response = client.get("/", params={"state_date": "2026-04-10"})

    assert response.status_code == 200
    assert "No weekly state found for the week of 2026-04-06." in response.text
    assert "No active open loops." in response.text


def test_hub_page_renders_signal_detail_evidence_chain() -> None:
    latest_run, comparison, daily_state, weekly_state, active_open_loops = _build_read_models()
    signal_id = comparison["signals"][0]["id"]
    app = create_hub_app(
        api_client=StubHistoryClient(
            latest_run=latest_run,
            comparison=comparison,
            daily_state=daily_state,
            weekly_state=weekly_state,
            active_open_loops=active_open_loops,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/",
            params={"state_date": "2026-04-10", "signal_id": signal_id},
        )

    assert response.status_code == 200
    body = response.text
    assert "Signal Detail" in body
    assert "Inspect signal detail" in body
    assert "Evidence chain" in body
    assert "Related entity type" in body
    assert comparison["signals"][0]["reason"] in body
    assert comparison["signals"][0]["evidence"][0]["summary"] in body


def test_hub_page_renders_alert_detail_with_source_signal_chain() -> None:
    latest_run, comparison, daily_state, weekly_state, active_open_loops = _build_read_models()
    alert_id = comparison["alerts"][0]["id"]
    source_signal_id = comparison["alerts"][0]["source_signal_ids"][0]
    app = create_hub_app(
        api_client=StubHistoryClient(
            latest_run=latest_run,
            comparison=comparison,
            daily_state=daily_state,
            weekly_state=weekly_state,
            active_open_loops=active_open_loops,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/",
            params={"state_date": "2026-04-10", "alert_id": alert_id},
        )

    assert response.status_code == 200
    body = response.text
    assert "Alert Detail" in body
    assert "Source Signal Chain" in body
    assert "Source signal ids" in body
    assert source_signal_id in body
    assert "Inspect alert detail" in body


def test_hub_module_has_no_direct_persistence_dependency() -> None:
    source = inspect.getsource(hub_app_module)

    assert "ari_memory" not in source
    assert "sqlalchemy" not in source


class APIBackedHistoryClient:
    def __init__(self, api_app: Any) -> None:
        self._client = TestClient(api_app)

    def get_latest_run(self, *, state_date: date) -> dict[str, Any]:
        return self._get("/orchestration-runs/latest", state_date)

    def compare_latest_two_runs(self, *, state_date: date) -> dict[str, Any]:
        return self._get("/orchestration-runs/compare-latest-two", state_date)

    def get_current_daily_state(self, *, state_date: date) -> dict[str, Any]:
        return self._get("/daily-states/current", state_date)

    def get_current_weekly_state(self, *, state_date: date) -> dict[str, Any]:
        return self._get("/weekly-states/current", state_date)

    def get_active_open_loops(self) -> dict[str, Any]:
        response = self._client.get("/open-loops/active")
        response.raise_for_status()
        return response.json()

    def get_signal_detail(self, *, signal_id: Any) -> dict[str, Any]:
        response = self._client.get(f"/signals/{signal_id}")
        response.raise_for_status()
        return response.json()

    def get_alert_detail(self, *, alert_id: Any) -> dict[str, Any]:
        response = self._client.get(f"/alerts/{alert_id}")
        response.raise_for_status()
        return response.json()

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


class StateGapHistoryClient:
    def __init__(
        self,
        *,
        latest_run: dict[str, Any],
        comparison: dict[str, Any],
        daily_state: dict[str, Any],
        weekly_detail: str,
    ) -> None:
        self._latest_run = latest_run
        self._comparison = comparison
        self._daily_state = daily_state
        self._weekly_detail = weekly_detail

    def get_latest_run(self, *, state_date: date) -> dict[str, Any]:
        return self._latest_run

    def compare_latest_two_runs(self, *, state_date: date) -> dict[str, Any]:
        return self._comparison

    def get_current_daily_state(self, *, state_date: date) -> dict[str, Any]:
        return self._daily_state

    def get_current_weekly_state(self, *, state_date: date) -> dict[str, Any]:
        raise HubAPIError(status_code=404, detail=self._weekly_detail)

    def get_active_open_loops(self) -> dict[str, Any]:
        return {"loops": []}

    def get_signal_detail(self, *, signal_id: Any) -> dict[str, Any]:
        raise HubAPIError(status_code=404, detail=f"No signal found for {signal_id}.")

    def get_alert_detail(self, *, alert_id: Any) -> dict[str, Any]:
        raise HubAPIError(status_code=404, detail=f"No alert found for {alert_id}.")


def _build_read_models(
    api_app: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    daily_state_response = client.get(
        "/daily-states/current",
        params={"state_date": "2026-04-10"},
    )
    weekly_state_response = client.get(
        "/weekly-states/current",
        params={"state_date": "2026-04-10"},
    )
    open_loops_response = client.get("/open-loops/active")
    latest_response.raise_for_status()
    comparison_response.raise_for_status()
    daily_state_response.raise_for_status()
    weekly_state_response.raise_for_status()
    open_loops_response.raise_for_status()
    return (
        latest_response.json(),
        comparison_response.json(),
        daily_state_response.json(),
        weekly_state_response.json(),
        open_loops_response.json(),
    )


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
