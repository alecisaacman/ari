from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_memory.tables import DailyStateRow, EventRow, OpenLoopRow, WeeklyStateRow
from ari_state import DailyState, Event, OpenLoop, WeeklyState


class DailyStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, day: date) -> Optional[DailyState]:
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
            last_check_at=row.last_check_at,
        )


class OpenLoopRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, loop_id: UUID) -> Optional[OpenLoop]:
        row = self._session.get(OpenLoopRow, loop_id)
        if row is None:
            return None
        return self._to_model(row)

    def list_open(self) -> list[OpenLoop]:
        rows = self._session.scalars(
            select(OpenLoopRow).where(OpenLoopRow.status != "closed").order_by(OpenLoopRow.opened_at.desc())
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
            opened_at=row.opened_at,
            due_at=row.due_at,
            last_touched_at=row.last_touched_at,
        )


class WeeklyStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, week_start: date) -> Optional[WeeklyState]:
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
            last_review_at=row.last_review_at,
        )


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: UUID) -> Optional[Event]:
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
            occurred_at=row.occurred_at,
            title=row.title,
            body=row.body,
            payload=row.payload,
            normalized_text=row.normalized_text,
        )
