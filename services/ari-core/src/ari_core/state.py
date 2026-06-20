from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar
from uuid import UUID

from ari_memory import (
    DailyStateRepository,
    EventRepository,
    OpenLoopEnrichmentRepository,
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
    OpenLoopEnrichment,
    OpenLoopKind,
    OpenLoopPriority,
    OpenLoopStatus,
    SkillKind,
    WeeklyState,
)
from sqlalchemy.orm import Session

from ari_core.company_research import research_company
from ari_core.skills import PAUSED_FILE, record_skill_invocation

StateT = TypeVar("StateT")

JOB_APPLICATION_ENRICHMENT_SKILL_NAME = "company_research"
JOB_APPLICATION_ENRICHMENT_SOURCE = "ari.signals.job_application_enrichment"


def _job_application_enrichment_enabled() -> bool:
    """Reversible via a flag, not a code revert: flip
    ARI_JOB_APPLICATION_ENRICHMENT_ENABLED=false to disable. Also honors
    the same state/PAUSED kill switch build_mcp_request_args checks, since
    this is an autonomous skill call ARI makes on its own, not one a human
    approved turn-by-turn."""
    if PAUSED_FILE.exists():
        return False
    return os.environ.get("ARI_JOB_APPLICATION_ENRICHMENT_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
    }


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
    company: str | None = None
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
            company=loop.company,
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

    if (
        created.kind == OpenLoopKind.JOB_APPLICATION
        and created.company
        and _job_application_enrichment_enabled()
    ):
        _trigger_job_application_enrichment(
            session,
            loop_id=created.id,
            company=created.company,
        )

    return StateMutationResult(state=created, events=[event])


def _trigger_job_application_enrichment(
    session: Session,
    *,
    loop_id: UUID,
    company: str,
) -> None:
    """Fires once, synchronously, right after a job_application loop is
    created. Reversible via ARI_JOB_APPLICATION_ENRICHMENT_ENABLED=false or
    the state/PAUSED kill switch — no code change needed to turn it off.
    Network/API failures are caught and recorded as a failed skill
    invocation rather than raised, so a flaky search never blocks filing
    the open loop itself. Logs through ari_core.skills.record_skill_invocation,
    the same audit path every other skill call goes through."""
    try:
        result = research_company(company)
    except Exception as exc:  # noqa: BLE001 - any failure here is logged, not raised
        record_skill_invocation(
            session,
            channel="automation",
            skill_kind=SkillKind.WEB_SEARCH,
            skill_name=JOB_APPLICATION_ENRICHMENT_SKILL_NAME,
            tool_name="web_search",
            summary=f"Company research failed for {company}: {exc}",
            payload={
                "loop_id": str(loop_id),
                "company": company,
                "reason": "open_loop created with kind=job_application",
                "error": str(exc),
            },
            is_error=True,
        )
        return

    enrichment = OpenLoopEnrichmentRepository(session).create(
        OpenLoopEnrichment(
            loop_id=loop_id,
            kind="company_intel",
            company=company,
            summary=result.summary,
            findings=[
                {
                    "category": finding.category,
                    "summary": finding.summary,
                    "source_url": finding.source_url,
                    "published_at": finding.published_at,
                }
                for finding in result.findings
            ],
            source=JOB_APPLICATION_ENRICHMENT_SOURCE,
            created_at=datetime.now(tz=UTC),
        )
    )
    session.commit()
    record_skill_invocation(
        session,
        channel="automation",
        skill_kind=SkillKind.WEB_SEARCH,
        skill_name=JOB_APPLICATION_ENRICHMENT_SKILL_NAME,
        tool_name="web_search",
        summary=f"Company research completed for {company}: {result.summary}"[:500],
        payload={
            "loop_id": str(loop_id),
            "company": company,
            "reason": "open_loop created with kind=job_application",
            "enrichment_id": str(enrichment.id),
            "findings_count": len(enrichment.findings),
        },
        is_error=False,
    )


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
