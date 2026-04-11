from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from ari_core import OrchestrationRunComparison, OrchestrationRunDetails
from ari_state import Alert, DailyState, EvidenceItem, OpenLoop, Signal, WeeklyState
from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItemResponse(APIModel):
    kind: str
    summary: str
    entity_type: str | None
    entity_id: UUID | None
    payload: dict[str, object]


class SignalResponse(APIModel):
    id: UUID
    state_date: date | None
    kind: str
    fingerprint: str
    severity: str
    summary: str
    reason: str
    evidence: list[EvidenceItemResponse]
    related_entity_type: str | None
    related_entity_id: UUID | None
    detected_at: datetime


class AlertResponse(APIModel):
    id: UUID
    state_date: date | None
    fingerprint: str
    status: str
    channel: str
    escalation_level: str
    title: str
    message: str
    reason: str
    source_signal_ids: list[UUID]
    created_at: datetime
    sent_at: datetime | None


class RunSummaryResponse(APIModel):
    run_id: UUID
    state_date: date
    executed_at: datetime
    state_fingerprint: str
    signal_ids: list[UUID]
    alert_ids: list[UUID]


class OrchestrationRunResponse(APIModel):
    run: RunSummaryResponse
    signals: list[SignalResponse]
    alerts: list[AlertResponse]


class OrchestrationRunComparisonResponse(APIModel):
    latest_run: RunSummaryResponse
    previous_run: RunSummaryResponse
    state_fingerprint_changed: bool
    reused_signal_ids: list[UUID]
    new_signal_ids: list[UUID]
    reused_alert_ids: list[UUID]
    new_alert_ids: list[UUID]
    signals: list[SignalResponse]
    alerts: list[AlertResponse]


class DailyStateResponse(APIModel):
    date: date
    priorities: list[str]
    win_condition: str
    movement: bool | None
    stress: int | None
    next_action: str
    last_check_at: datetime | None


class WeeklyStateResponse(APIModel):
    week_start: date
    outcomes: list[str]
    cannot_drift: list[str]
    blockers: list[str]
    lesson: str
    last_review_at: datetime | None


class OpenLoopResponse(APIModel):
    id: UUID
    title: str
    status: str
    kind: str
    priority: str
    source: str
    notes: str
    project_id: UUID | None
    opened_at: datetime
    due_at: datetime | None
    last_touched_at: datetime | None


class ActiveOpenLoopsResponse(APIModel):
    loops: list[OpenLoopResponse]


def build_run_response(details: OrchestrationRunDetails) -> OrchestrationRunResponse:
    return OrchestrationRunResponse(
        run=_build_run_summary(details),
        signals=[_build_signal_response(signal) for signal in details.signals],
        alerts=[_build_alert_response(alert) for alert in details.alerts],
    )


def build_run_comparison_response(
    comparison: OrchestrationRunComparison,
    latest: OrchestrationRunDetails,
    previous: OrchestrationRunDetails,
) -> OrchestrationRunComparisonResponse:
    return OrchestrationRunComparisonResponse(
        latest_run=_build_run_summary(latest),
        previous_run=_build_run_summary(previous),
        state_fingerprint_changed=comparison.state_fingerprint_changed,
        reused_signal_ids=[*comparison.reused_signal_ids],
        new_signal_ids=[*comparison.new_signal_ids],
        reused_alert_ids=[*comparison.reused_alert_ids],
        new_alert_ids=[*comparison.new_alert_ids],
        signals=[_build_signal_response(signal) for signal in latest.signals],
        alerts=[_build_alert_response(alert) for alert in latest.alerts],
    )


def build_daily_state_response(state: DailyState) -> DailyStateResponse:
    return DailyStateResponse(
        date=state.date,
        priorities=[*state.priorities],
        win_condition=state.win_condition,
        movement=state.movement,
        stress=state.stress,
        next_action=state.next_action,
        last_check_at=state.last_check_at,
    )


def build_weekly_state_response(state: WeeklyState) -> WeeklyStateResponse:
    return WeeklyStateResponse(
        week_start=state.week_start,
        outcomes=[*state.outcomes],
        cannot_drift=[*state.cannot_drift],
        blockers=[*state.blockers],
        lesson=state.lesson,
        last_review_at=state.last_review_at,
    )


def build_active_open_loops_response(loops: list[OpenLoop]) -> ActiveOpenLoopsResponse:
    return ActiveOpenLoopsResponse(
        loops=[_build_open_loop_response(loop) for loop in loops],
    )


def build_signal_response(signal: Signal) -> SignalResponse:
    return _build_signal_response(signal)


def build_alert_response(alert: Alert) -> AlertResponse:
    return _build_alert_response(alert)


def _build_run_summary(details: OrchestrationRunDetails) -> RunSummaryResponse:
    run = details.run
    return RunSummaryResponse(
        run_id=run.id,
        state_date=run.state_date,
        executed_at=run.executed_at,
        state_fingerprint=run.state_fingerprint,
        signal_ids=[*run.signal_ids],
        alert_ids=[*run.alert_ids],
    )


def _build_signal_response(signal: Signal) -> SignalResponse:
    return SignalResponse(
        id=signal.id,
        state_date=signal.state_date,
        kind=signal.kind,
        fingerprint=signal.fingerprint,
        severity=signal.severity,
        summary=signal.summary,
        reason=signal.reason,
        evidence=[_build_evidence_item_response(item) for item in signal.evidence],
        related_entity_type=signal.related_entity_type,
        related_entity_id=signal.related_entity_id,
        detected_at=signal.detected_at,
    )


def _build_alert_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        state_date=alert.state_date,
        fingerprint=alert.fingerprint,
        status=alert.status,
        channel=alert.channel,
        escalation_level=alert.escalation_level,
        title=alert.title,
        message=alert.message,
        reason=alert.reason,
        source_signal_ids=[*alert.source_signal_ids],
        created_at=alert.created_at,
        sent_at=alert.sent_at,
    )


def _build_evidence_item_response(item: EvidenceItem) -> EvidenceItemResponse:
    return EvidenceItemResponse(
        kind=item.kind,
        summary=item.summary,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        payload=dict(item.payload),
    )


def _build_open_loop_response(loop: OpenLoop) -> OpenLoopResponse:
    return OpenLoopResponse(
        id=loop.id,
        title=loop.title,
        status=loop.status,
        kind=loop.kind,
        priority=loop.priority,
        source=loop.source,
        notes=loop.notes,
        project_id=loop.project_id,
        opened_at=loop.opened_at,
        due_at=loop.due_at,
        last_touched_at=loop.last_touched_at,
    )
