from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ari_state import DailyState, Event, EventCategory, WeeklyState

StateT = TypeVar("StateT", DailyState, WeeklyState)


class RoutineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DailyCheckInput(RoutineInput):
    priorities: list[str] = Field(default_factory=list, max_length=3)
    win_condition: str = ""
    movement: Optional[bool] = None
    stress: Optional[int] = Field(default=None, ge=1, le=10)
    next_action: str = ""


class WeeklyPlanningInput(RoutineInput):
    outcomes: list[str] = Field(default_factory=list, max_length=3)
    cannot_drift: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class WeeklyReflectionInput(RoutineInput):
    lesson: str = ""
    blockers: Optional[list[str]] = None


@dataclass(frozen=True)
class RoutineResult(Generic[StateT]):
    state: StateT
    event: Event


def record_daily_check(
    *,
    day: date,
    check: DailyCheckInput,
    checked_at: datetime,
    source: str = "ari.routine.daily_check",
) -> RoutineResult[DailyState]:
    state = DailyState(
        date=day,
        priorities=list(check.priorities),
        win_condition=check.win_condition,
        movement=check.movement,
        stress=check.stress,
        next_action=check.next_action,
        last_check_at=checked_at,
    )
    event = Event(
        source=source,
        category=EventCategory.DAILY_UPDATE,
        occurred_at=checked_at,
        title="Daily check recorded",
        payload=state.model_dump(mode="json"),
    )
    return RoutineResult(state=state, event=event)


def record_weekly_planning(
    *,
    week_start: date,
    planning: WeeklyPlanningInput,
    reviewed_at: datetime,
    current_state: Optional[WeeklyState] = None,
    source: str = "ari.routine.weekly_planning",
) -> RoutineResult[WeeklyState]:
    state = WeeklyState(
        week_start=week_start,
        outcomes=list(planning.outcomes),
        cannot_drift=list(planning.cannot_drift),
        blockers=list(planning.blockers),
        lesson="" if current_state is None else current_state.lesson,
        last_review_at=reviewed_at,
    )
    event = Event(
        source=source,
        category=EventCategory.WEEKLY_PLANNING,
        occurred_at=reviewed_at,
        title="Weekly planning recorded",
        payload=state.model_dump(mode="json"),
    )
    return RoutineResult(state=state, event=event)


def record_weekly_reflection(
    *,
    week_start: date,
    reflection: WeeklyReflectionInput,
    reviewed_at: datetime,
    current_state: Optional[WeeklyState] = None,
    source: str = "ari.routine.weekly_reflection",
) -> RoutineResult[WeeklyState]:
    preserved_state = current_state or WeeklyState(week_start=week_start)
    state = WeeklyState(
        week_start=week_start,
        outcomes=list(preserved_state.outcomes),
        cannot_drift=list(preserved_state.cannot_drift),
        blockers=list(preserved_state.blockers if reflection.blockers is None else reflection.blockers),
        lesson=reflection.lesson,
        last_review_at=reviewed_at,
    )
    event = Event(
        source=source,
        category=EventCategory.WEEKLY_REFLECTION,
        occurred_at=reviewed_at,
        title="Weekly reflection recorded",
        payload=state.model_dump(mode="json"),
    )
    return RoutineResult(state=state, event=event)
