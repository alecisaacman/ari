from __future__ import annotations

from datetime import date
from io import StringIO
from pathlib import Path

from ari_cli.main import run_cli
from ari_memory import (
    Base,
    DailyStateRepository,
    EventRepository,
    OpenLoopRepository,
    WeeklyStateRepository,
)
from ari_state import EventCategory, OpenLoopStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_today_set_and_read_persist_canonical_daily_state_and_event(tmp_path: Path) -> None:
    database_url = _prepare_database(tmp_path / "today.db")
    output = StringIO()

    exit_code = run_cli(
        [
            "today",
            "set",
            "--state-date",
            "2026-04-10",
            "--priority",
            "Ship CLI write surface",
            "--priority",
            "Preserve canon",
            "--win-condition",
            "Leave the operator loop writable.",
            "--movement",
            "true",
            "--stress",
            "6",
            "--next-action",
            "Wire the API on the same seam.",
            "--database-url",
            database_url,
        ],
        stdout=output,
    )

    assert exit_code == 0
    assert "daily state 2026-04-10" in output.getvalue()
    assert "Ship CLI write surface" in output.getvalue()

    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        state = DailyStateRepository(session).get(date(2026, 4, 10))
        events = EventRepository(session).list_recent(limit=1)

    assert state is not None
    assert state.priorities == ["Ship CLI write surface", "Preserve canon"]
    assert state.movement is True
    assert state.stress == 6
    assert state.next_action == "Wire the API on the same seam."
    assert events[0].category == EventCategory.DAILY_UPDATE

    read_output = StringIO()
    read_exit_code = run_cli(
        [
            "today",
            "read",
            "--state-date",
            "2026-04-10",
            "--database-url",
            database_url,
        ],
        stdout=read_output,
    )

    assert read_exit_code == 0
    assert "Leave the operator loop writable." in read_output.getvalue()


def test_week_set_supports_planning_then_reflection_without_losing_week_context(
    tmp_path: Path,
) -> None:
    database_url = _prepare_database(tmp_path / "week.db")

    plan_exit_code = run_cli(
        [
            "week",
            "set",
            "--state-date",
            "2026-04-10",
            "--outcome",
            "Finish the writable operator loop",
            "--cannot-drift",
            "Canonical package ownership",
            "--blocker",
            "API writes still missing",
            "--database-url",
            database_url,
        ],
        stdout=StringIO(),
    )
    reflection_output = StringIO()
    reflection_exit_code = run_cli(
        [
            "week",
            "set",
            "--state-date",
            "2026-04-10",
            "--lesson",
            "Thin surfaces only hold if the write seam is shared.",
            "--database-url",
            database_url,
        ],
        stdout=reflection_output,
    )

    assert plan_exit_code == 0
    assert reflection_exit_code == 0
    assert "Thin surfaces only hold if the write seam is shared." in reflection_output.getvalue()

    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        state = WeeklyStateRepository(session).get(date(2026, 4, 6))
        events = EventRepository(session).list_recent(limit=2)

    assert state is not None
    assert state.outcomes == ["Finish the writable operator loop"]
    assert state.cannot_drift == ["Canonical package ownership"]
    assert state.blockers == ["API writes still missing"]
    assert state.lesson == "Thin surfaces only hold if the write seam is shared."
    assert [event.category for event in events] == [
        EventCategory.WEEKLY_REFLECTION,
        EventCategory.WEEKLY_PLANNING,
    ]


def test_loops_add_read_and_resolve_manage_open_loop_lifecycle(tmp_path: Path) -> None:
    database_url = _prepare_database(tmp_path / "loops.db")
    add_output = StringIO()

    add_exit_code = run_cli(
        [
            "loops",
            "add",
            "--title",
            "Close the CLI/API write gap",
            "--source",
            "operator",
            "--kind",
            "task",
            "--priority",
            "high",
            "--notes",
            "Needs canonical mutation helpers first.",
            "--database-url",
            database_url,
        ],
        stdout=add_output,
    )

    assert add_exit_code == 0
    assert "Close the CLI/API write gap" in add_output.getvalue()

    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        loops = OpenLoopRepository(session).list_open()
        loop_id = loops[0].id

    read_output = StringIO()
    read_exit_code = run_cli(
        ["loops", "read", "--database-url", database_url],
        stdout=read_output,
    )
    resolve_output = StringIO()
    resolve_exit_code = run_cli(
        [
            "loops",
            "resolve",
            "--id",
            str(loop_id),
            "--database-url",
            database_url,
        ],
        stdout=resolve_output,
    )

    assert read_exit_code == 0
    assert "Close the CLI/API write gap" in read_output.getvalue()
    assert resolve_exit_code == 0
    assert "status: closed" in resolve_output.getvalue()

    with Session(engine) as session:
        loop = OpenLoopRepository(session).get(loop_id)
        events = EventRepository(session).list_recent(limit=2)

    assert loop is not None
    assert loop.status == OpenLoopStatus.CLOSED
    assert [event.category for event in events] == [
        EventCategory.OPEN_LOOP_RESOLVE,
        EventCategory.OPEN_LOOP_ADD,
    ]


def _prepare_database(path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return database_url
