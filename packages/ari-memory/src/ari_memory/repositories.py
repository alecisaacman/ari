from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from ari_state import (
    Alert,
    AlertChannel,
    AlertEscalationLevel,
    AlertStatus,
    ControllerCycleState,
    ControllerEvent,
    ControllerEventType,
    ControllerTrajectory,
    ConversationState,
    DailyState,
    Event,
    EventCategory,
    EvidenceItem,
    OpenLoop,
    OpenLoopEnrichment,
    OpenLoopKind,
    OpenLoopPriority,
    OpenLoopStatus,
    OrchestrationRun,
    PendingApproval,
    PendingApprovalStatus,
    Signal,
    SignalSeverity,
    SkillInvocation,
    SkillKind,
    SkillRegistration,
    SkillRegistrationKind,
    WeeklyState,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ari_memory.tables import (
    AlertRow,
    ControllerEventRow,
    ConversationStateRow,
    DailyStateRow,
    EventRow,
    OpenLoopEnrichmentRow,
    OpenLoopRow,
    OrchestrationRunRow,
    PendingApprovalRow,
    SignalRow,
    SkillInvocationRow,
    SkillRegistrationRow,
    WeeklyStateRow,
)


class DailyStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, day: date) -> DailyState | None:
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
            last_check_at=_normalize_datetime(row.last_check_at),
        )


class OpenLoopRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, loop_id: UUID) -> OpenLoop | None:
        row = self._session.get(OpenLoopRow, loop_id)
        if row is None:
            return None
        return self._to_model(row)

    def list_open(self) -> list[OpenLoop]:
        rows = self._session.scalars(
            select(OpenLoopRow)
            .where(OpenLoopRow.status != "closed")
            .order_by(OpenLoopRow.opened_at.desc())
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
        row.company = loop.company
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
            status=OpenLoopStatus(row.status),
            kind=OpenLoopKind(row.kind),
            priority=OpenLoopPriority(row.priority),
            source=row.source,
            notes=row.notes,
            company=row.company,
            project_id=row.project_id,
            opened_at=_required_datetime(row.opened_at),
            due_at=_normalize_datetime(row.due_at),
            last_touched_at=_normalize_datetime(row.last_touched_at),
        )


class OpenLoopEnrichmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, enrichment: OpenLoopEnrichment) -> OpenLoopEnrichment:
        row = OpenLoopEnrichmentRow(
            id=enrichment.id,
            loop_id=enrichment.loop_id,
            kind=enrichment.kind,
            company=enrichment.company,
            summary=enrichment.summary,
            findings=enrichment.findings,
            source=enrichment.source,
            created_at=enrichment.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def list_for_loop(self, loop_id: UUID) -> list[OpenLoopEnrichment]:
        rows = self._session.scalars(
            select(OpenLoopEnrichmentRow)
            .where(OpenLoopEnrichmentRow.loop_id == loop_id)
            .order_by(OpenLoopEnrichmentRow.created_at.desc())
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: OpenLoopEnrichmentRow) -> OpenLoopEnrichment:
        return OpenLoopEnrichment(
            id=row.id,
            loop_id=row.loop_id,
            kind=row.kind,
            company=row.company,
            summary=row.summary,
            findings=row.findings,
            source=row.source,
            created_at=_required_datetime(row.created_at),
        )


class WeeklyStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, week_start: date) -> WeeklyState | None:
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
            last_review_at=_normalize_datetime(row.last_review_at),
        )


class ConversationStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, channel: str) -> ConversationState | None:
        row = self._session.scalar(
            select(ConversationStateRow).where(ConversationStateRow.channel == channel)
        )
        if row is None:
            return None
        return self._to_model(row)

    def upsert(self, state: ConversationState) -> ConversationState:
        row = self._session.scalar(
            select(ConversationStateRow).where(ConversationStateRow.channel == state.channel)
        )
        if row is None:
            row = ConversationStateRow(id=uuid4(), channel=state.channel)
            self._session.add(row)

        row.cursor = state.cursor
        row.messages = list(state.messages)
        row.updated_at = state.updated_at
        self._session.flush()
        return self._to_model(row)

    def _to_model(self, row: ConversationStateRow) -> ConversationState:
        return ConversationState(
            id=row.id,
            channel=row.channel,
            cursor=row.cursor,
            messages=row.messages,
            updated_at=_normalize_datetime(row.updated_at),
        )


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: UUID) -> Event | None:
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
            category=EventCategory(row.category),
            occurred_at=_required_datetime(row.occurred_at),
            title=row.title,
            body=row.body,
            payload=row.payload,
            normalized_text=row.normalized_text,
        )


class ControllerEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, event: ControllerEvent) -> ControllerEvent:
        row = ControllerEventRow(
            id=event.id,
            run_id=event.run_id,
            sequence_number=event.sequence_number,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            summary=event.summary,
            payload=event.payload,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def create_many(self, events: list[ControllerEvent]) -> list[ControllerEvent]:
        return [self.create(event) for event in events]

    def list_for_run(self, run_id: UUID) -> list[ControllerEvent]:
        rows = self._session.scalars(
            select(ControllerEventRow)
            .where(ControllerEventRow.run_id == run_id)
            .order_by(
                ControllerEventRow.sequence_number.asc(),
                ControllerEventRow.occurred_at.asc(),
                ControllerEventRow.id.asc(),
            )
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: ControllerEventRow) -> ControllerEvent:
        return ControllerEvent(
            id=row.id,
            run_id=row.run_id,
            sequence_number=row.sequence_number,
            occurred_at=_required_datetime(row.occurred_at),
            event_type=ControllerEventType(row.event_type),
            summary=row.summary,
            payload=row.payload,
        )


class SignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, signal_id: UUID) -> Signal | None:
        row = self._session.get(SignalRow, signal_id)
        if row is None:
            return None
        return self._to_model(row)

    def create(self, signal: Signal) -> Signal:
        row = SignalRow(
            id=signal.id,
            state_date=signal.state_date,
            kind=signal.kind,
            fingerprint=signal.fingerprint,
            severity=signal.severity,
            summary=signal.summary,
            reason=signal.reason,
            evidence=[item.model_dump(mode="json") for item in signal.evidence],
            related_entity_type=signal.related_entity_type,
            related_entity_id=signal.related_entity_id,
            detected_at=signal.detected_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def create_many(self, signals: list[Signal]) -> list[Signal]:
        return [self.create(signal) for signal in signals]

    def list_by_ids(self, signal_ids: list[UUID]) -> list[Signal]:
        signals_by_id = {
            signal_id: signal
            for signal_id in signal_ids
            if (signal := self.get(signal_id)) is not None
        }
        return [signals_by_id[signal_id] for signal_id in signal_ids if signal_id in signals_by_id]

    def get_by_fingerprint(self, *, state_date: date, fingerprint: str) -> Signal | None:
        row = self._session.scalar(
            select(SignalRow).where(
                SignalRow.state_date == state_date,
                SignalRow.fingerprint == fingerprint,
            )
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_recent(self, limit: int = 20) -> list[Signal]:
        rows = self._session.scalars(
            select(SignalRow).order_by(SignalRow.detected_at.desc()).limit(limit)
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: SignalRow) -> Signal:
        return Signal(
            id=row.id,
            state_date=row.state_date,
            kind=row.kind,
            fingerprint=row.fingerprint,
            severity=SignalSeverity(row.severity),
            summary=row.summary,
            reason=row.reason,
            evidence=[EvidenceItem.model_validate(item) for item in row.evidence],
            related_entity_type=row.related_entity_type,
            related_entity_id=row.related_entity_id,
            detected_at=_required_datetime(row.detected_at),
        )


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, alert_id: UUID) -> Alert | None:
        row = self._session.get(AlertRow, alert_id)
        if row is None:
            return None
        return self._to_model(row)

    def create(self, alert: Alert) -> Alert:
        row = AlertRow(
            id=alert.id,
            state_date=alert.state_date,
            fingerprint=alert.fingerprint,
            status=alert.status,
            channel=alert.channel,
            escalation_level=alert.escalation_level,
            title=alert.title,
            message=alert.message,
            reason=alert.reason,
            source_signal_ids=[str(signal_id) for signal_id in alert.source_signal_ids],
            created_at=alert.created_at,
            sent_at=alert.sent_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def create_many(self, alerts: list[Alert]) -> list[Alert]:
        return [self.create(alert) for alert in alerts]

    def list_by_ids(self, alert_ids: list[UUID]) -> list[Alert]:
        alerts_by_id = {
            alert_id: alert for alert_id in alert_ids if (alert := self.get(alert_id)) is not None
        }
        return [alerts_by_id[alert_id] for alert_id in alert_ids if alert_id in alerts_by_id]

    def get_by_fingerprint(self, *, state_date: date, fingerprint: str) -> Alert | None:
        row = self._session.scalar(
            select(AlertRow).where(
                AlertRow.state_date == state_date,
                AlertRow.fingerprint == fingerprint,
            )
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_recent(self, limit: int = 20) -> list[Alert]:
        rows = self._session.scalars(
            select(AlertRow).order_by(AlertRow.created_at.desc()).limit(limit)
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: AlertRow) -> Alert:
        return Alert(
            id=row.id,
            state_date=row.state_date,
            fingerprint=row.fingerprint,
            status=AlertStatus(row.status),
            channel=AlertChannel(row.channel),
            escalation_level=AlertEscalationLevel(row.escalation_level),
            title=row.title,
            message=row.message,
            reason=row.reason,
            source_signal_ids=[UUID(signal_id) for signal_id in row.source_signal_ids],
            created_at=_required_datetime(row.created_at),
            sent_at=_normalize_datetime(row.sent_at),
        )


class OrchestrationRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, run: OrchestrationRun) -> OrchestrationRun:
        row = OrchestrationRunRow(id=run.id)
        self._session.add(row)
        self._apply(row, run)
        self._session.flush()
        return self._to_model(row)

    def get(self, run_id: UUID) -> OrchestrationRun | None:
        row = self._session.get(OrchestrationRunRow, run_id)
        if row is None:
            return None
        return self._to_model(row)

    def update(self, run: OrchestrationRun) -> OrchestrationRun:
        row = self._session.get(OrchestrationRunRow, run.id)
        if row is None:
            raise ValueError(f"No orchestration run found for {run.id}.")
        self._apply(row, run)
        self._session.flush()
        return self._to_model(row)

    def get_latest_for_state_date(self, state_date: date) -> OrchestrationRun | None:
        row = self._session.scalar(self._state_date_runs_query(state_date).limit(1))
        if row is None:
            return None
        return self._to_model(row)

    def get_previous_for_state_date(self, state_date: date) -> OrchestrationRun | None:
        row = self._session.scalar(self._state_date_runs_query(state_date).offset(1).limit(1))
        if row is None:
            return None
        return self._to_model(row)

    def list_for_state_date(self, state_date: date) -> list[OrchestrationRun]:
        rows = self._session.scalars(self._state_date_runs_query(state_date)).all()
        return [self._to_model(row) for row in rows]

    def _state_date_runs_query(self, state_date: date) -> Select[tuple[OrchestrationRunRow]]:
        return (
            select(OrchestrationRunRow)
            .where(OrchestrationRunRow.state_date == state_date)
            .order_by(OrchestrationRunRow.executed_at.desc(), OrchestrationRunRow.id.desc())
        )

    def _apply(self, row: OrchestrationRunRow, run: OrchestrationRun) -> None:
        row.state_date = run.state_date
        row.state_fingerprint = run.state_fingerprint
        row.executed_at = run.executed_at
        row.signal_ids = [str(signal_id) for signal_id in run.signal_ids]
        row.alert_ids = [str(alert_id) for alert_id in run.alert_ids]
        row.controller_trajectory = (
            None
            if run.controller_trajectory is None
            else run.controller_trajectory.model_dump(mode="json")
        )
        row.controller_cycle_state = run.controller_cycle_state

    def _to_model(self, row: OrchestrationRunRow) -> OrchestrationRun:
        return OrchestrationRun(
            id=row.id,
            state_date=row.state_date,
            state_fingerprint=row.state_fingerprint,
            executed_at=_required_datetime(row.executed_at),
            signal_ids=[UUID(signal_id) for signal_id in row.signal_ids],
            alert_ids=[UUID(alert_id) for alert_id in row.alert_ids],
            controller_trajectory=(
                None
                if row.controller_trajectory is None
                else ControllerTrajectory.model_validate(row.controller_trajectory)
            ),
            controller_cycle_state=(
                None
                if row.controller_cycle_state is None
                else ControllerCycleState(row.controller_cycle_state)
            ),
        )


class PendingApprovalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, approval: PendingApproval) -> PendingApproval:
        row = PendingApprovalRow(id=approval.id)
        self._session.add(row)
        self._apply(row, approval)
        self._session.flush()
        return self._to_model(row)

    def get(self, approval_id: UUID) -> PendingApproval | None:
        row = self._session.get(PendingApprovalRow, approval_id)
        if row is None:
            return None
        return self._to_model(row)

    def get_by_run(self, run_id: UUID) -> PendingApproval | None:
        row = self._session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.run_id == run_id)
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_pending(self) -> list[PendingApproval]:
        rows = self._session.scalars(
            select(PendingApprovalRow)
            .where(PendingApprovalRow.status == PendingApprovalStatus.PENDING)
            .order_by(PendingApprovalRow.requested_at.asc(), PendingApprovalRow.id.asc())
        ).all()
        return [self._to_model(row) for row in rows]

    def update(self, approval: PendingApproval) -> PendingApproval:
        row = self._session.get(PendingApprovalRow, approval.id)
        if row is None:
            raise ValueError(f"No pending approval found for {approval.id}.")
        self._apply(row, approval)
        self._session.flush()
        return self._to_model(row)

    def _apply(self, row: PendingApprovalRow, approval: PendingApproval) -> None:
        row.run_id = approval.run_id
        row.decision_id = approval.decision_id
        row.status = approval.status
        row.requested_at = approval.requested_at
        row.resolved_at = approval.resolved_at
        row.reason = approval.reason
        row.decision_summary = approval.decision_summary
        row.proposed_action = approval.proposed_action

    def _to_model(self, row: PendingApprovalRow) -> PendingApproval:
        return PendingApproval(
            id=row.id,
            run_id=row.run_id,
            decision_id=row.decision_id,
            status=PendingApprovalStatus(row.status),
            requested_at=_required_datetime(row.requested_at),
            resolved_at=_normalize_datetime(row.resolved_at),
            reason=row.reason,
            decision_summary=row.decision_summary,
            proposed_action=row.proposed_action,
        )


class SkillRegistrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_name(self, name: str) -> SkillRegistration | None:
        row = self._session.scalar(
            select(SkillRegistrationRow).where(SkillRegistrationRow.name == name)
        )
        if row is None:
            return None
        return self._to_model(row)

    def list_enabled(self) -> list[SkillRegistration]:
        rows = self._session.scalars(
            select(SkillRegistrationRow)
            .where(SkillRegistrationRow.enabled.is_(True))
            .order_by(SkillRegistrationRow.name.asc())
        ).all()
        return [self._to_model(row) for row in rows]

    def upsert(self, registration: SkillRegistration) -> SkillRegistration:
        row = self._session.scalar(
            select(SkillRegistrationRow).where(SkillRegistrationRow.name == registration.name)
        )
        if row is None:
            row = SkillRegistrationRow(id=registration.id, name=registration.name)
            self._session.add(row)

        row.kind = registration.kind
        row.mcp_url = registration.mcp_url
        row.enabled = registration.enabled
        row.encrypted_token = registration.encrypted_token
        row.created_at = registration.created_at
        row.updated_at = registration.updated_at
        self._session.flush()
        return self._to_model(row)

    def _to_model(self, row: SkillRegistrationRow) -> SkillRegistration:
        return SkillRegistration(
            id=row.id,
            name=row.name,
            kind=SkillRegistrationKind(row.kind),
            mcp_url=row.mcp_url,
            enabled=row.enabled,
            encrypted_token=row.encrypted_token,
            created_at=_required_datetime(row.created_at),
            updated_at=_required_datetime(row.updated_at),
        )


class SkillInvocationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, invocation: SkillInvocation) -> SkillInvocation:
        row = SkillInvocationRow(
            id=invocation.id,
            occurred_at=invocation.occurred_at,
            channel=invocation.channel,
            skill_kind=invocation.skill_kind,
            skill_name=invocation.skill_name,
            tool_name=invocation.tool_name,
            summary=invocation.summary,
            payload=invocation.payload,
            is_error=invocation.is_error,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_model(row)

    def list_recent(self, limit: int = 50) -> list[SkillInvocation]:
        rows = self._session.scalars(
            select(SkillInvocationRow).order_by(SkillInvocationRow.occurred_at.desc()).limit(limit)
        ).all()
        return [self._to_model(row) for row in rows]

    def _to_model(self, row: SkillInvocationRow) -> SkillInvocation:
        return SkillInvocation(
            id=row.id,
            occurred_at=_required_datetime(row.occurred_at),
            channel=row.channel,
            skill_kind=SkillKind(row.skill_kind),
            skill_name=row.skill_name,
            tool_name=row.tool_name,
            summary=row.summary,
            payload=row.payload,
            is_error=row.is_error,
        )


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _required_datetime(value: datetime | None) -> datetime:
    normalized = _normalize_datetime(value)
    if normalized is None:
        raise ValueError("Expected persisted datetime value")
    return normalized
