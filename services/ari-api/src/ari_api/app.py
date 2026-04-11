from __future__ import annotations

from collections.abc import Generator
from datetime import date

from ari_core import (
    compare_latest_two_runs,
    get_latest_run_details,
    get_previous_run_details,
)
from ari_memory import DatabaseSettings, create_engine, create_session_factory
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session, sessionmaker

from ari_api.schemas import (
    OrchestrationRunComparisonResponse,
    OrchestrationRunResponse,
    build_run_comparison_response,
    build_run_response,
)


def create_app(session_factory: sessionmaker[Session] | None = None) -> FastAPI:
    resolved_session_factory = session_factory or _build_session_factory()
    app = FastAPI(title="ARI API", version="0.1.0")

    def get_session() -> Generator[Session, None, None]:
        with resolved_session_factory() as session:
            yield session

    @app.get(
        "/orchestration-runs/latest",
        response_model=OrchestrationRunResponse,
    )
    def latest_orchestration_run(
        state_date: date = Query(...),  # noqa: B008
        session: Session = Depends(get_session),  # noqa: B008
    ) -> OrchestrationRunResponse:
        details = get_latest_run_details(session, state_date=state_date)
        if details is None:
            raise HTTPException(
                status_code=404,
                detail=f"No orchestration run found for {state_date.isoformat()}.",
            )
        return build_run_response(details)

    @app.get(
        "/orchestration-runs/previous",
        response_model=OrchestrationRunResponse,
    )
    def previous_orchestration_run(
        state_date: date = Query(...),  # noqa: B008
        session: Session = Depends(get_session),  # noqa: B008
    ) -> OrchestrationRunResponse:
        details = get_previous_run_details(session, state_date=state_date)
        if details is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No previous orchestration run found for {state_date.isoformat()}."
                ),
            )
        return build_run_response(details)

    @app.get(
        "/orchestration-runs/compare-latest-two",
        response_model=OrchestrationRunComparisonResponse,
    )
    def compare_latest_two_orchestration_runs(
        state_date: date = Query(...),  # noqa: B008
        session: Session = Depends(get_session),  # noqa: B008
    ) -> OrchestrationRunComparisonResponse:
        comparison = compare_latest_two_runs(session, state_date=state_date)
        latest = get_latest_run_details(session, state_date=state_date)
        previous = get_previous_run_details(session, state_date=state_date)
        if comparison is None or latest is None or previous is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Need at least two orchestration runs to compare "
                    f"for {state_date.isoformat()}."
                ),
            )
        return build_run_comparison_response(comparison, latest, previous)

    return app


def _build_session_factory() -> sessionmaker[Session]:
    settings = DatabaseSettings()
    engine = create_engine(settings.database_url)
    return create_session_factory(engine)
