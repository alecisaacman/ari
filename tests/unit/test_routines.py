from datetime import UTC, date, datetime

from ari_routines import (
    DailyCheckInput,
    WeeklyPlanningInput,
    WeeklyReflectionInput,
    record_daily_check,
    record_weekly_planning,
    record_weekly_reflection,
)
from ari_state import EventCategory, WeeklyState


def test_daily_check_routine_maps_locked_structure() -> None:
    checked_at = datetime(2026, 4, 10, 8, 30, tzinfo=UTC)

    result = record_daily_check(
        day=date(2026, 4, 10),
        check=DailyCheckInput(
            priorities=["Ship the weekly repository", "Wire the first signals"],
            win_condition="The spine writes and reasons from one shared state.",
            movement=True,
            stress=7,
            next_action="Add alert generation tests.",
        ),
        checked_at=checked_at,
    )

    assert result.state.priorities == ["Ship the weekly repository", "Wire the first signals"]
    assert result.state.win_condition == "The spine writes and reasons from one shared state."
    assert result.state.movement is True
    assert result.state.stress == 7
    assert result.state.next_action == "Add alert generation tests."
    assert result.state.last_check_at == checked_at
    assert result.event.category == EventCategory.DAILY_UPDATE
    assert result.event.payload["last_check_at"] == "2026-04-10T08:30:00Z"


def test_weekly_planning_routine_updates_weekly_contract_and_preserves_lesson() -> None:
    existing = WeeklyState(
        week_start=date(2026, 4, 7),
        outcomes=["Old outcome"],
        cannot_drift=["Old guardrail"],
        blockers=["Old blocker"],
        lesson="Keep routines state-first.",
    )
    reviewed_at = datetime(2026, 4, 7, 16, 0, tzinfo=UTC)

    result = record_weekly_planning(
        week_start=date(2026, 4, 7),
        planning=WeeklyPlanningInput(
            outcomes=["Ship the spine", "Add explainable alerts"],
            cannot_drift=["Canonical state"],
            blockers=["Naming still needs review"],
        ),
        reviewed_at=reviewed_at,
        current_state=existing,
    )

    assert result.state.outcomes == ["Ship the spine", "Add explainable alerts"]
    assert result.state.cannot_drift == ["Canonical state"]
    assert result.state.blockers == ["Naming still needs review"]
    assert result.state.lesson == "Keep routines state-first."
    assert result.state.last_review_at == reviewed_at
    assert result.event.category == EventCategory.WEEKLY_PLANNING


def test_weekly_reflection_routine_updates_lesson_and_optionally_blockers() -> None:
    existing = WeeklyState(
        week_start=date(2026, 4, 7),
        outcomes=["Ship the spine"],
        cannot_drift=["Canonical state"],
        blockers=["Migration review"],
    )
    reviewed_at = datetime(2026, 4, 11, 11, 0, tzinfo=UTC)

    result = record_weekly_reflection(
        week_start=date(2026, 4, 7),
        reflection=WeeklyReflectionInput(
            lesson="Small explainable signals are enough for the first layer.",
            blockers=["No material blockers"],
        ),
        reviewed_at=reviewed_at,
        current_state=existing,
    )

    assert result.state.outcomes == ["Ship the spine"]
    assert result.state.cannot_drift == ["Canonical state"]
    assert result.state.blockers == ["No material blockers"]
    assert result.state.lesson == "Small explainable signals are enough for the first layer."
    assert result.state.last_review_at == reviewed_at
    assert result.event.category == EventCategory.WEEKLY_REFLECTION
