from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from typing import TextIO

from ari_memory import DatabaseSettings, create_engine, create_session_factory
from sqlalchemy.orm import Session, sessionmaker

from ari_cli.history_cli import (
    handle_compare_latest_two_runs,
    handle_latest_run,
    handle_previous_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ari")
    parser.set_defaults(handler=None)

    orchestration_parser = parser.add_subparsers(dest="surface").add_parser("orchestration")
    orchestration_subparsers = orchestration_parser.add_subparsers(dest="command")

    for command in ("latest", "previous", "compare-latest-two"):
        command_parser = orchestration_subparsers.add_parser(command)
        command_parser.add_argument(
            "--state-date",
            required=True,
            type=_parse_state_date,
            help="State date to inspect (YYYY-MM-DD).",
        )
        command_parser.add_argument(
            "--database-url",
            default=None,
            help="Override DATABASE_URL for this command.",
        )

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.surface != "orchestration" or args.command is None:
        parser.print_help(file=stdout)
        return 1

    output = stdout if stdout is not None else sys.stdout
    session_factory = _resolve_session_factory(args.database_url)

    if args.command == "latest":
        return handle_latest_run(session_factory, state_date=args.state_date, stdout=output)
    if args.command == "previous":
        return handle_previous_run(session_factory, state_date=args.state_date, stdout=output)
    return handle_compare_latest_two_runs(
        session_factory,
        state_date=args.state_date,
        stdout=output,
    )


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
