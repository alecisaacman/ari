from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TextIO
from uuid import UUID

from ari_core import (
    CreateOpenLoopInput,
    DailyStateUpdate,
    WeeklyPlanningUpdate,
    WeeklyReflectionUpdate,
    create_open_loop,
    get_daily_state,
    get_weekly_state,
    list_open_loops,
    resolve_open_loop,
    update_daily_state,
    update_weekly_plan,
    update_weekly_reflection,
)
from ari_state import DailyState, OpenLoop, OpenLoopKind, OpenLoopPriority, WeeklyState
from sqlalchemy.orm import Session, sessionmaker


def handle_today_read(
    session_factory: sessionmaker[Session],
    *,
    state_date: date,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        state = get_daily_state(session, day=state_date)
    if state is None:
        stdout.write(f"no daily state for {state_date.isoformat()}\n")
        return 1
    stdout.write(_render_daily_state(state))
    return 0


def handle_today_set(
    session_factory: sessionmaker[Session],
    *,
    state_date: date,
    update: DailyStateUpdate,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = update_daily_state(
            session,
            day=state_date,
            update=update,
            checked_at=datetime.now(tz=UTC),
        )
    stdout.write(_render_daily_state(result.state))
    return 0


def handle_week_read(
    session_factory: sessionmaker[Session],
    *,
    state_date: date,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        state = get_weekly_state(session, state_date=state_date)
    if state is None:
        stdout.write(f"no weekly state for the week of {state_date.isoformat()}\n")
        return 1
    stdout.write(_render_weekly_state(state))
    return 0


def handle_week_set_plan(
    session_factory: sessionmaker[Session],
    *,
    state_date: date,
    update: WeeklyPlanningUpdate,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = update_weekly_plan(
            session,
            state_date=state_date,
            update=update,
            reviewed_at=datetime.now(tz=UTC),
        )
    stdout.write(_render_weekly_state(result.state))
    return 0


def handle_week_set_reflection(
    session_factory: sessionmaker[Session],
    *,
    state_date: date,
    update: WeeklyReflectionUpdate,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = update_weekly_reflection(
            session,
            state_date=state_date,
            update=update,
            reviewed_at=datetime.now(tz=UTC),
        )
    stdout.write(_render_weekly_state(result.state))
    return 0


def handle_loops_read(
    session_factory: sessionmaker[Session],
    *,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        loops = list_open_loops(session)
    stdout.write(_render_open_loops(loops))
    return 0


def handle_loops_add(
    session_factory: sessionmaker[Session],
    *,
    loop: CreateOpenLoopInput,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = create_open_loop(session, loop=loop, opened_at=datetime.now(tz=UTC))
    stdout.write(_render_single_loop(result.state))
    return 0


def handle_loops_resolve(
    session_factory: sessionmaker[Session],
    *,
    loop_id: UUID,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = resolve_open_loop(session, loop_id=loop_id, resolved_at=datetime.now(tz=UTC))
    if result is None:
        stdout.write(f"no open loop found for {loop_id}\n")
        return 1
    stdout.write(_render_single_loop(result.state))
    return 0


def _render_daily_state(state: DailyState) -> str:
    movement = "unknown" if state.movement is None else ("yes" if state.movement else "no")
    priorities = ", ".join(state.priorities) or "none"
    return "\n".join(
        [
            f"daily state {state.date.isoformat()}",
            f"priorities: {priorities}",
            f"win_condition: {state.win_condition or 'none'}",
            f"movement: {movement}",
            f"stress: {state.stress if state.stress is not None else 'unknown'}",
            f"next_action: {state.next_action or 'none'}",
            f"last_check_at: {state.last_check_at.isoformat() if state.last_check_at else 'none'}",
            "",
        ]
    )


def _render_weekly_state(state: WeeklyState) -> str:
    outcomes = ", ".join(state.outcomes) or "none"
    cannot_drift = ", ".join(state.cannot_drift) or "none"
    blockers = ", ".join(state.blockers) or "none"
    return "\n".join(
        [
            f"weekly state {state.week_start.isoformat()}",
            f"outcomes: {outcomes}",
            f"cannot_drift: {cannot_drift}",
            f"blockers: {blockers}",
            f"lesson: {state.lesson or 'none'}",
            (
                "last_review_at: "
                f"{state.last_review_at.isoformat() if state.last_review_at else 'none'}"
            ),
            "",
        ]
    )


def _render_open_loops(loops: list[OpenLoop]) -> str:
    if not loops:
        return "open loops\nnone\n"
    lines = ["open loops"]
    for loop in loops:
        lines.append(_render_single_loop(loop).rstrip())
    return "\n".join(lines) + "\n"


def _render_single_loop(loop: OpenLoop) -> str:
    return "\n".join(
        [
            f"loop {loop.id}",
            f"title: {loop.title}",
            f"status: {loop.status}",
            f"kind: {loop.kind}",
            f"priority: {loop.priority}",
            f"source: {loop.source}",
            f"notes: {loop.notes or 'none'}",
            f"project_id: {loop.project_id if loop.project_id is not None else 'none'}",
            f"opened_at: {loop.opened_at.isoformat()}",
            f"due_at: {loop.due_at.isoformat() if loop.due_at else 'none'}",
            (
                "last_touched_at: "
                f"{loop.last_touched_at.isoformat() if loop.last_touched_at else 'none'}"
            ),
            "",
        ]
    )


def parse_priority(raw_value: str) -> OpenLoopPriority:
    try:
        return OpenLoopPriority(raw_value)
    except ValueError as exc:
        valid = ", ".join(priority.value for priority in OpenLoopPriority)
        raise ValueError(f"invalid priority {raw_value!r}; expected one of {valid}") from exc


def parse_kind(raw_value: str) -> OpenLoopKind:
    try:
        return OpenLoopKind(raw_value)
    except ValueError as exc:
        valid = ", ".join(kind.value for kind in OpenLoopKind)
        raise ValueError(f"invalid kind {raw_value!r}; expected one of {valid}") from exc
