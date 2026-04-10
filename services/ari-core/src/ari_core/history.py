from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from ari_memory import AlertRepository, OrchestrationRunRepository, SignalRepository
from ari_state import Alert, OrchestrationRun, Signal
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class OrchestrationRunDetails:
    run: OrchestrationRun
    signals: list[Signal]
    alerts: list[Alert]


@dataclass(frozen=True, slots=True)
class OrchestrationRunComparison:
    state_date: date
    latest_run_id: UUID
    latest_executed_at: datetime
    previous_run_id: UUID
    previous_executed_at: datetime
    latest_state_fingerprint: str
    previous_state_fingerprint: str
    state_fingerprint_changed: bool
    reused_signal_ids: list[UUID]
    new_signal_ids: list[UUID]
    reused_alert_ids: list[UUID]
    new_alert_ids: list[UUID]


def get_latest_run_details(
    session: Session,
    *,
    state_date: date,
) -> OrchestrationRunDetails | None:
    runs = OrchestrationRunRepository(session)
    run = runs.get_latest_for_state_date(state_date)
    if run is None:
        return None
    return _load_run_details(session, run=run)


def get_previous_run_details(
    session: Session,
    *,
    state_date: date,
) -> OrchestrationRunDetails | None:
    runs = OrchestrationRunRepository(session)
    run = runs.get_previous_for_state_date(state_date)
    if run is None:
        return None
    return _load_run_details(session, run=run)


def compare_latest_two_runs(
    session: Session,
    *,
    state_date: date,
) -> OrchestrationRunComparison | None:
    latest = get_latest_run_details(session, state_date=state_date)
    previous = get_previous_run_details(session, state_date=state_date)
    if latest is None or previous is None:
        return None
    return _compare_runs(latest=latest, previous=previous)


def _load_run_details(session: Session, *, run: OrchestrationRun) -> OrchestrationRunDetails:
    signals = SignalRepository(session).list_by_ids(run.signal_ids)
    alerts = AlertRepository(session).list_by_ids(run.alert_ids)
    return OrchestrationRunDetails(run=run, signals=signals, alerts=alerts)


def _compare_runs(
    *,
    latest: OrchestrationRunDetails,
    previous: OrchestrationRunDetails,
) -> OrchestrationRunComparison:
    reused_signal_ids, new_signal_ids = _partition_ids(
        latest_ids=latest.run.signal_ids,
        previous_ids=previous.run.signal_ids,
    )
    reused_alert_ids, new_alert_ids = _partition_ids(
        latest_ids=latest.run.alert_ids,
        previous_ids=previous.run.alert_ids,
    )
    return OrchestrationRunComparison(
        state_date=latest.run.state_date,
        latest_run_id=latest.run.id,
        latest_executed_at=latest.run.executed_at,
        previous_run_id=previous.run.id,
        previous_executed_at=previous.run.executed_at,
        latest_state_fingerprint=latest.run.state_fingerprint,
        previous_state_fingerprint=previous.run.state_fingerprint,
        state_fingerprint_changed=(
            latest.run.state_fingerprint != previous.run.state_fingerprint
        ),
        reused_signal_ids=reused_signal_ids,
        new_signal_ids=new_signal_ids,
        reused_alert_ids=reused_alert_ids,
        new_alert_ids=new_alert_ids,
    )


def _partition_ids(
    *,
    latest_ids: list[UUID],
    previous_ids: list[UUID],
) -> tuple[list[UUID], list[UUID]]:
    previous_id_set = set(previous_ids)
    reused_ids = [entity_id for entity_id in latest_ids if entity_id in previous_id_set]
    new_ids = [entity_id for entity_id in latest_ids if entity_id not in previous_id_set]
    return reused_ids, new_ids
