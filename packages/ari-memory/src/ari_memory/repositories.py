from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from ari_state import (
    Alert,
    DailyState,
    Event,
    EvidenceItem,
    OpenLoop,
    OrchestrationRun,
    Signal,
    WeeklyState,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_memory.tables import (
    AlertRow,
    DailyStateRow,
    EventRow,
    OpenLoopRow,
    OrchestrationRunRow,
    SignalRow,
    WeeklyStateRow,
)


class DailyStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, day: date) -> DailyState | None:
        row = self._session.get(DailyStateRow, day)
        if row is None:
            return None
        return self._to_model(row)

    def upsert(self, state: DailyState) -> DailyState:
        row = self._session.get(DailyStateRow, state.date)
        if row is None:
            row = DailyStateRow(date=state.date)
            self._session.add(row)

        row.priorities = list(state.priorities)
        row.win_condition = state.win_condition
        row.movement = state.movement
        row.stress = state.stress
        row.next_action = state.next_action
        row.last_check_at = state.last_check_at
        self._session.flush()
        return self._to_model(row)

    def _to_model(self, row: DailyStateRow) -> DailyState:
        return DailyState(
            date=row.date,
            priorities=row.priorities,
            win_condition=row.win_condition,
            movement=row.movement,
            stress=row.stress,
            next_action=row.next_action,
            last_check_at=_normalize_datetime(row.last_check_at),
        )


class OpenLoopRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, loop_id: UUID) -> OpenLoop | None:
        row = self._session.get(OpenLoopRow, loop_id)
        if row is None:
            return None
        return self._to_model(row)

    def list_open(self) -> list[OpenLoop]:
        rows = self._session.scalars(
            select(OpenLoopRow)
            .where(OpenLoopRow.status != "closed")
            .order_by(OpenLoopRow.opened_at.desc())
        ).all()
        return [self._to_model(row) for row in rows]

    def upsert(self, loop: OpenLoop) -> OpenLoop:
        row = self._session.get(OpenLoopRow, loop.id)
        if row is None:
            row = OpenLoopRow(id=loop.id)
            self._session.add(row)

        row.title = loop.title
        row.status = loop.status
        row.kind = loop.kind
        row.priority = loop.priority
        row.source = loop.source
        row.notes = loop.notes
        row.project_id = loop.project_id
        row.opened_at = loop.opened_at
        row.due_at = loop.due_at
        row.last_touched_at = loop.last_touched_at
        self._session.flush()
        return self._to_model(row)

    def _to_model(self, row: OpenLoopRow) -> OpenLoop:
        return OpenLoop(
            id=row.id,
            title=row.title,
            status=row.status,
            kind=row.kind,
            priority=row.priority,
            source=row.source,
            notes=row.notes,
            project_id=row.project_id,
            opened_at=_normalize_datetime(row.opened_at),
            due_at=_normalize_datetime(row.due_at),
            last_touched_at=_normalize_datetime(row.last_touched_at),
        )


class WeeklyStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, week_start: date) -> WeeklyState | None:
        row = self._session.get(WeeklyStateRow, week_start)
        if row is None:
            return None
        return self._to_model(row)

    def upsert(self, state: WeeklyState) -> WeeklyState:
        row = self._session.get(WeeklyStateRow, state.week_start)
        if row is None:
            row = WeeklyStateRow(week_start=state.week_start)
            self._session.add(row)

        row.outcomes = list(state.outcomes)
        row.cannot_drift = list(state.cannot_drift)
        row.blockers = list(state.blockers)
        row.lesson = state.lesson
        row.last_review_at = state.last_review_at
        self._session.flush()
        return self._to_model(row)

    def _to_model(self, row: WeeklyStateRow) -> WeeklyState:
        return WeeklyState(
            week_start=row.week_start,
            outcomes=row.outcomes,
            cannot_drift=row.cannot_drift,
            blockers=row.blockers,
            lesson=row.lesson,
            last_review_at=_normalize_datetime(row.last_review_at),
        )


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: UUID) -> Event | None:
        row = self._session.get(EventRow, event_id)
        if row is None:
            return None
        return self._to_model(row)

    def create(self, event: Event) -> Event:
        row = EventRow(
            id=event.id,
            source=event.source,
            category=event.category,
            occurred_at=event.occurred_at,
            title=event.title,
            body=event.body,
            payload=event.payload,
            normalized_text=event.normalized_text,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def list_recent(self, limit: int = 20) -> list[Event]:
        rows = self._session.scalars(
            select(EventRow).order_by(EventRow.occurred_at.desc()).limit(limit)
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: EventRow) -> Event:
        return Event(
            id=row.id,
            source=row.source,
            category=row.category,
            occurred_at=_normalize_datetime(row.occurred_at),
            title=row.title,
            body=row.body,
            payload=row.payload,
            normalized_text=row.normalized_text,
        )


class SignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, signal_id: UUID) -> Signal | None:
        row = self._session.get(SignalRow, signal_id)
        if row is None:
            return None
        return self._to_model(row)

    def create(self, signal: Signal) -> Signal:
        row = SignalRow(
            id=signal.id,
            state_date=signal.state_date,
            kind=signal.kind,
            fingerprint=signal.fingerprint,
            severity=signal.severity,
            summary=signal.summary,
            reason=signal.reason,
            evidence=[item.model_dump(mode="json") for item in signal.evidence],
            related_entity_type=signal.related_entity_type,
            related_entity_id=signal.related_entity_id,
            detected_at=signal.detected_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def create_many(self, signals: list[Signal]) -> list[Signal]:
        return [self.create(signal) for signal in signals]

    def get_by_fingerprint(self, *, state_date: date, fingerprint: str) -> Signal | None:
        row = self._session.scalar(
            select(SignalRow).where(
                SignalRow.state_date == state_date,
                SignalRow.fingerprint == fingerprint,
            )
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_recent(self, limit: int = 20) -> list[Signal]:
        rows = self._session.scalars(
            select(SignalRow).order_by(SignalRow.detected_at.desc()).limit(limit)
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: SignalRow) -> Signal:
        return Signal(
            id=row.id,
            state_date=row.state_date,
            kind=row.kind,
            fingerprint=row.fingerprint,
            severity=row.severity,
            summary=row.summary,
            reason=row.reason,
            evidence=[EvidenceItem.model_validate(item) for item in row.evidence],
            related_entity_type=row.related_entity_type,
            related_entity_id=row.related_entity_id,
            detected_at=_normalize_datetime(row.detected_at),
        )


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, alert_id: UUID) -> Alert | None:
        row = self._session.get(AlertRow, alert_id)
        if row is None:
            return None
        return self._to_model(row)

    def create(self, alert: Alert) -> Alert:
        row = AlertRow(
            id=alert.id,
            state_date=alert.state_date,
            fingerprint=alert.fingerprint,
            status=alert.status,
            channel=alert.channel,
            escalation_level=alert.escalation_level,
            title=alert.title,
            message=alert.message,
            reason=alert.reason,
            source_signal_ids=[str(signal_id) for signal_id in alert.source_signal_ids],
            created_at=alert.created_at,
            sent_at=alert.sent_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def create_many(self, alerts: list[Alert]) -> list[Alert]:
        return [self.create(alert) for alert in alerts]

    def get_by_fingerprint(self, *, state_date: date, fingerprint: str) -> Alert | None:
        row = self._session.scalar(
            select(AlertRow).where(
                AlertRow.state_date == state_date,
                AlertRow.fingerprint == fingerprint,
            )
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_recent(self, limit: int = 20) -> list[Alert]:
        rows = self._session.scalars(
            select(AlertRow).order_by(AlertRow.created_at.desc()).limit(limit)
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: AlertRow) -> Alert:
        return Alert(
            id=row.id,
            state_date=row.state_date,
            fingerprint=row.fingerprint,
            status=row.status,
            channel=row.channel,
            escalation_level=row.escalation_level,
            title=row.title,
            message=row.message,
            reason=row.reason,
            source_signal_ids=[UUID(signal_id) for signal_id in row.source_signal_ids],
            created_at=_normalize_datetime(row.created_at),
            sent_at=_normalize_datetime(row.sent_at),
        )


class OrchestrationRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, run: OrchestrationRun) -> OrchestrationRun:
        row = OrchestrationRunRow(
            id=run.id,
            state_date=run.state_date,
            state_fingerprint=run.state_fingerprint,
            executed_at=run.executed_at,
            signal_ids=[str(signal_id) for signal_id in run.signal_ids],
            alert_ids=[str(alert_id) for alert_id in run.alert_ids],
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def get_latest_for_state_date(self, state_date: date) -> OrchestrationRun | None:
        row = self._session.scalar(
            select(OrchestrationRunRow)
            .where(OrchestrationRunRow.state_date == state_date)
            .order_by(OrchestrationRunRow.executed_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_for_state_date(self, state_date: date) -> list[OrchestrationRun]:
        rows = self._session.scalars(
            select(OrchestrationRunRow)
            .where(OrchestrationRunRow.state_date == state_date)
            .order_by(OrchestrationRunRow.executed_at.desc())
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: OrchestrationRunRow) -> OrchestrationRun:
        return OrchestrationRun(
            id=row.id,
            state_date=row.state_date,
            state_fingerprint=row.state_fingerprint,
            executed_at=_normalize_datetime(row.executed_at),
            signal_ids=[UUID(signal_id) for signal_id in row.signal_ids],
            alert_ids=[UUID(alert_id) for alert_id in row.alert_ids],
        )


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
