from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime
from typing import TextIO
from uuid import UUID

from ari_core import (
    CreateOpenLoopInput,
    DailyStateUpdate,
    WeeklyPlanningUpdate,
    WeeklyReflectionUpdate,
)
from ari_memory import DatabaseSettings, create_engine, create_session_factory
from ari_state import OpenLoopKind, OpenLoopPriority
from sqlalchemy.orm import Session, sessionmaker

from ari_cli.history_cli import (
    handle_compare_latest_two_runs,
    handle_latest_run,
    handle_previous_run,
)
from ari_cli.state_cli import (
    handle_loops_add,
    handle_loops_read,
    handle_loops_resolve,
    handle_today_read,
    handle_today_set,
    handle_week_read,
    handle_week_set_plan,
    handle_week_set_reflection,
    parse_kind,
    parse_priority,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ari")
    parser.set_defaults(handler=None)

    surfaces = parser.add_subparsers(dest="surface")

    orchestration_parser = surfaces.add_parser("orchestration")
    orchestration_subparsers = orchestration_parser.add_subparsers(dest="command")

    for command in ("latest", "previous", "compare-latest-two"):
        command_parser = orchestration_subparsers.add_parser(command)
        _add_state_date_argument(command_parser, required=True)
        _add_database_url_argument(command_parser)

    today_parser = surfaces.add_parser("today")
    today_subparsers = today_parser.add_subparsers(dest="command")

    today_read = today_subparsers.add_parser("read")
    _add_state_date_argument(today_read)
    _add_database_url_argument(today_read)

    today_set = today_subparsers.add_parser("set")
    _add_state_date_argument(today_set)
    _add_database_url_argument(today_set)
    today_set.add_argument("--priority", action="append", dest="priorities", default=None)
    today_set.add_argument("--win-condition")
    today_set.add_argument("--movement", type=_parse_movement)
    today_set.add_argument("--stress", type=int)
    today_set.add_argument("--next-action")

    week_parser = surfaces.add_parser("week")
    week_subparsers = week_parser.add_subparsers(dest="command")

    week_read = week_subparsers.add_parser("read")
    _add_state_date_argument(week_read)
    _add_database_url_argument(week_read)

    week_set = week_subparsers.add_parser("set")
    _add_state_date_argument(week_set)
    _add_database_url_argument(week_set)
    week_set.add_argument("--outcome", action="append", dest="outcomes", default=None)
    week_set.add_argument("--cannot-drift", action="append", dest="cannot_drift", default=None)
    week_set.add_argument("--blocker", action="append", dest="blockers", default=None)
    week_set.add_argument("--lesson")

    loops_parser = surfaces.add_parser("loops")
    loops_subparsers = loops_parser.add_subparsers(dest="command")

    loops_read = loops_subparsers.add_parser("read")
    _add_database_url_argument(loops_read)

    loops_add = loops_subparsers.add_parser("add")
    _add_database_url_argument(loops_add)
    loops_add.add_argument("--title", required=True)
    loops_add.add_argument("--source", required=True)
    loops_add.add_argument("--kind", type=_parse_kind, default=parse_kind("task"))
    loops_add.add_argument("--priority", type=_parse_priority, default=parse_priority("medium"))
    loops_add.add_argument("--notes", default="")
    loops_add.add_argument("--project-id", type=UUID)
    loops_add.add_argument("--due-at", type=_parse_datetime)

    loops_resolve = loops_subparsers.add_parser("resolve")
    _add_database_url_argument(loops_resolve)
    loops_resolve.add_argument("--id", required=True, type=UUID)

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.surface is None or args.command is None:
        parser.print_help(file=stdout)
        return 1

    output = stdout if stdout is not None else sys.stdout
    session_factory = _resolve_session_factory(args.database_url)

    if args.surface == "orchestration":
        if args.command == "latest":
            return handle_latest_run(session_factory, state_date=args.state_date, stdout=output)
        if args.command == "previous":
            return handle_previous_run(session_factory, state_date=args.state_date, stdout=output)
        return handle_compare_latest_two_runs(
            session_factory,
            state_date=args.state_date,
            stdout=output,
        )
    if args.surface == "today":
        if args.command == "read":
            return handle_today_read(session_factory, state_date=args.state_date, stdout=output)
        return handle_today_set(
            session_factory,
            state_date=args.state_date,
            update=DailyStateUpdate(
                priorities=args.priorities,
                win_condition=args.win_condition,
                movement=args.movement,
                stress=args.stress,
                next_action=args.next_action,
            ),
            stdout=output,
        )
    if args.surface == "week":
        if args.command == "read":
            return handle_week_read(session_factory, state_date=args.state_date, stdout=output)
        if args.lesson is not None and (args.outcomes is not None or args.cannot_drift is not None):
            parser.error("week set accepts planning fields or --lesson, but not both")
        if args.lesson is not None:
            return handle_week_set_reflection(
                session_factory,
                state_date=args.state_date,
                update=WeeklyReflectionUpdate(
                    lesson=args.lesson,
                    blockers=args.blockers,
                ),
                stdout=output,
            )
        return handle_week_set_plan(
            session_factory,
            state_date=args.state_date,
            update=WeeklyPlanningUpdate(
                outcomes=args.outcomes,
                cannot_drift=args.cannot_drift,
                blockers=args.blockers,
            ),
            stdout=output,
        )
    if args.surface == "loops":
        if args.command == "read":
            return handle_loops_read(session_factory, stdout=output)
        if args.command == "add":
            return handle_loops_add(
                session_factory,
                loop=CreateOpenLoopInput(
                    title=args.title,
                    source=args.source,
                    kind=args.kind,
                    priority=args.priority,
                    notes=args.notes,
                    project_id=args.project_id,
                    due_at=args.due_at,
                ),
                stdout=output,
            )
        return handle_loops_resolve(session_factory, loop_id=args.id, stdout=output)
    parser.print_help(file=stdout)
    return 1


def main() -> None:
    raise SystemExit(run_cli())


def _resolve_session_factory(database_url: str | None) -> sessionmaker[Session]:
    resolved_database_url = database_url or DatabaseSettings().database_url
    engine = create_engine(resolved_database_url)
    return create_session_factory(engine)


def _parse_state_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid state date {raw_value!r}; expected YYYY-MM-DD"
        ) from exc


def _parse_datetime(raw_value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid datetime {raw_value!r}; expected ISO-8601"
        ) from exc
    return parsed


def _parse_movement(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise argparse.ArgumentTypeError(
        f"invalid movement {raw_value!r}; expected true/false"
    )


def _parse_priority(raw_value: str) -> OpenLoopPriority:
    try:
        return parse_priority(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_kind(raw_value: str) -> OpenLoopKind:
    try:
        return parse_kind(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_database_url_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL for this command.",
    )


def _add_state_date_argument(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
) -> None:
    parser.add_argument(
        "--state-date",
        required=required,
        default=date.today(),
        type=_parse_state_date,
        help="State date to inspect (YYYY-MM-DD).",
    )
