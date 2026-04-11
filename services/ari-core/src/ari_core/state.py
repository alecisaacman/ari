from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar
from uuid import UUID

from ari_memory import (
    DailyStateRepository,
    EventRepository,
    OpenLoopRepository,
    WeeklyStateRepository,
)
from ari_routines import (
    DailyCheckInput,
    WeeklyPlanningInput,
    WeeklyReflectionInput,
    record_daily_check,
    record_weekly_planning,
    record_weekly_reflection,
)
from ari_state import (
    DailyState,
    Event,
    EventCategory,
    OpenLoop,
    OpenLoopKind,
    OpenLoopPriority,
    OpenLoopStatus,
    WeeklyState,
)
from sqlalchemy.orm import Session

StateT = TypeVar("StateT")


@dataclass(frozen=True, slots=True)
class DailyStateUpdate:
    priorities: list[str] | None = None
    win_condition: str | None = None
    movement: bool | None = None
    stress: int | None = None
    next_action: str | None = None


@dataclass(frozen=True, slots=True)
class WeeklyPlanningUpdate:
    outcomes: list[str] | None = None
    cannot_drift: list[str] | None = None
    blockers: list[str] | None = None


@dataclass(frozen=True, slots=True)
class WeeklyReflectionUpdate:
    lesson: str
    blockers: list[str] | None = None


@dataclass(frozen=True, slots=True)
class CreateOpenLoopInput:
    title: str
    source: str
    kind: OpenLoopKind = OpenLoopKind.TASK
    priority: OpenLoopPriority = OpenLoopPriority.MEDIUM
    notes: str = ""
    project_id: UUID | None = None
    due_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StateMutationResult[StateT]:
    state: StateT
    events: list[Event]


def get_daily_state(session: Session, *, day: date) -> DailyState | None:
    return DailyStateRepository(session).get(day)


def update_daily_state(
    session: Session,
    *,
    day: date,
    update: DailyStateUpdate,
    checked_at: datetime,
    source: str = "ari.cli.today",
) -> StateMutationResult[DailyState]:
    repository = DailyStateRepository(session)
    current_state = repository.get(day)
    merged = DailyCheckInput(
        priorities=(
            list(current_state.priorities)
            if current_state is not None and update.priorities is None
            else list(update.priorities or [])
        ),
        win_condition=(
            current_state.win_condition
            if current_state is not None and update.win_condition is None
            else update.win_condition or ""
        ),
        movement=(
            current_state.movement
            if current_state is not None and update.movement is None
            else update.movement
        ),
        stress=(
            current_state.stress
            if current_state is not None and update.stress is None
            else update.stress
        ),
        next_action=(
            current_state.next_action
            if current_state is not None and update.next_action is None
            else update.next_action or ""
        ),
    )
    result = record_daily_check(
        day=day,
        check=merged,
        checked_at=_normalize_timestamp(checked_at),
        source=source,
    )
    persisted_state = repository.upsert(result.state)
    event = EventRepository(session).create(result.event)
    session.commit()
    return StateMutationResult(state=persisted_state, events=[event])


def get_weekly_state(session: Session, *, state_date: date) -> WeeklyState | None:
    return WeeklyStateRepository(session).get(_week_start_for(state_date))


def update_weekly_plan(
    session: Session,
    *,
    state_date: date,
    update: WeeklyPlanningUpdate,
    reviewed_at: datetime,
    source: str = "ari.cli.week",
) -> StateMutationResult[WeeklyState]:
    week_start = _week_start_for(state_date)
    repository = WeeklyStateRepository(session)
    current_state = repository.get(week_start)
    planning = WeeklyPlanningInput(
        outcomes=(
            list(current_state.outcomes)
            if current_state is not None and update.outcomes is None
            else list(update.outcomes or [])
        ),
        cannot_drift=(
            list(current_state.cannot_drift)
            if current_state is not None and update.cannot_drift is None
            else list(update.cannot_drift or [])
        ),
        blockers=(
            list(current_state.blockers)
            if current_state is not None and update.blockers is None
            else list(update.blockers or [])
        ),
    )
    result = record_weekly_planning(
        week_start=week_start,
        planning=planning,
        reviewed_at=_normalize_timestamp(reviewed_at),
        current_state=current_state,
        source=source,
    )
    persisted_state = repository.upsert(result.state)
    event = EventRepository(session).create(result.event)
    session.commit()
    return StateMutationResult(state=persisted_state, events=[event])


def update_weekly_reflection(
    session: Session,
    *,
    state_date: date,
    update: WeeklyReflectionUpdate,
    reviewed_at: datetime,
    source: str = "ari.cli.week",
) -> StateMutationResult[WeeklyState]:
    week_start = _week_start_for(state_date)
    repository = WeeklyStateRepository(session)
    current_state = repository.get(week_start)
    reflection = WeeklyReflectionInput(
        lesson=update.lesson,
        blockers=None if update.blockers is None else list(update.blockers),
    )
    result = record_weekly_reflection(
        week_start=week_start,
        reflection=reflection,
        reviewed_at=_normalize_timestamp(reviewed_at),
        current_state=current_state,
        source=source,
    )
    persisted_state = repository.upsert(result.state)
    event = EventRepository(session).create(result.event)
    session.commit()
    return StateMutationResult(state=persisted_state, events=[event])


def list_open_loops(session: Session) -> list[OpenLoop]:
    return OpenLoopRepository(session).list_open()


def create_open_loop(
    session: Session,
    *,
    loop: CreateOpenLoopInput,
    opened_at: datetime,
    source: str = "ari.cli.loops",
) -> StateMutationResult[OpenLoop]:
    timestamp = _normalize_timestamp(opened_at)
    repository = OpenLoopRepository(session)
    created = repository.upsert(
        OpenLoop(
            title=loop.title,
            status=OpenLoopStatus.OPEN,
            kind=loop.kind,
            priority=loop.priority,
            source=loop.source,
            notes=loop.notes,
            project_id=loop.project_id,
            opened_at=timestamp,
            due_at=loop.due_at,
            last_touched_at=timestamp,
        )
    )
    event = EventRepository(session).create(
        Event(
            source=source,
            category=EventCategory.OPEN_LOOP_ADD,
            occurred_at=timestamp,
            title="Open loop added",
            payload=created.model_dump(mode="json"),
        )
    )
    session.commit()
    return StateMutationResult(state=created, events=[event])


def resolve_open_loop(
    session: Session,
    *,
    loop_id: UUID,
    resolved_at: datetime,
    source: str = "ari.cli.loops",
) -> StateMutationResult[OpenLoop] | None:
    repository = OpenLoopRepository(session)
    existing = repository.get(loop_id)
    if existing is None:
        return None
    timestamp = _normalize_timestamp(resolved_at)
    resolved = repository.upsert(
        existing.model_copy(
            update={
                "status": OpenLoopStatus.CLOSED,
                "last_touched_at": timestamp,
            }
        )
    )
    event = EventRepository(session).create(
        Event(
            source=source,
            category=EventCategory.OPEN_LOOP_RESOLVE,
            occurred_at=timestamp,
            title="Open loop resolved",
            payload=resolved.model_dump(mode="json"),
        )
    )
    session.commit()
    return StateMutationResult(state=resolved, events=[event])


def _week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
