from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from ari_core import OrchestrationRunComparison, OrchestrationRunDetails
from ari_state import (
    ActionPlan,
    Alert,
    AuthorityResult,
    ControllerDecision,
    ControllerEvent,
    ControllerTrajectory,
    DailyState,
    EvidenceItem,
    ExecutionObservationRecord,
    OpenLoop,
    OpenLoopKind,
    OpenLoopPriority,
    PendingApproval,
    ProposedAction,
    Signal,
    VerificationResult,
    WeeklyState,
    WorkerRun,
)
from pydantic import BaseModel, ConfigDict, Field


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


class ProposedActionResponse(APIModel):
    action_type: str
    target: str
    instructions: str


class ControllerDecisionResponse(APIModel):
    id: UUID
    decision_type: str
    decision_summary: str
    proposed_action: str
    requires_approval: bool
    confidence: float
    action_intents: list[ProposedActionResponse]


class AuthorityResultResponse(APIModel):
    decision_id: UUID
    outcome: str
    reason: str
    may_execute: bool


class ActionPlanResponse(APIModel):
    decision_id: UUID
    summary: str
    actions: list[ProposedActionResponse]
    is_bounded: bool


class ExecutionObservationResponse(APIModel):
    success: bool
    kind: str
    target: str
    summary: str
    details: str


class WorkerRunResponse(APIModel):
    decision_id: UUID
    executed_at: datetime
    observations: list[ExecutionObservationResponse]


class VerificationResultResponse(APIModel):
    decision_id: UUID
    outcome: str
    reason: str


class ControllerTrajectoryResponse(APIModel):
    decision: ControllerDecisionResponse
    authority_result: AuthorityResultResponse
    action_plan: ActionPlanResponse | None
    worker_run: WorkerRunResponse | None
    verification_result: VerificationResultResponse | None
    controller_outcome: str


class ControllerEventResponse(APIModel):
    id: UUID
    run_id: UUID
    sequence_number: int
    occurred_at: datetime
    event_type: str
    summary: str
    payload: dict[str, object]


class PendingApprovalResponse(APIModel):
    id: UUID
    run_id: UUID
    decision_id: UUID
    status: str
    requested_at: datetime
    resolved_at: datetime | None
    reason: str
    decision_summary: str
    proposed_action: str


class PendingApprovalsResponse(APIModel):
    approvals: list[PendingApprovalResponse]


class ApprovalActionRequest(APIModel):
    resolved_at: datetime | None = None


class RunSummaryResponse(APIModel):
    run_id: UUID
    state_date: date
    executed_at: datetime
    state_fingerprint: str
    signal_ids: list[UUID]
    alert_ids: list[UUID]
    controller_trajectory: ControllerTrajectoryResponse | None
    controller_cycle_state: str | None
    pending_approval: PendingApprovalResponse | None


class OrchestrationRunResponse(APIModel):
    run: RunSummaryResponse
    signals: list[SignalResponse]
    alerts: list[AlertResponse]
    controller_events: list[ControllerEventResponse]


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
    latest_controller_events: list[ControllerEventResponse]
    previous_controller_events: list[ControllerEventResponse]


class DailyStateResponse(APIModel):
    date: date
    priorities: list[str]
    win_condition: str
    movement: bool | None
    stress: int | None
    next_action: str
    last_check_at: datetime | None


class DailyStateWriteRequest(APIModel):
    priorities: list[str] | None = Field(default=None, max_length=3)
    win_condition: str | None = None
    movement: bool | None = None
    stress: int | None = Field(default=None, ge=1, le=10)
    next_action: str | None = None
    checked_at: datetime | None = None


class WeeklyStateResponse(APIModel):
    week_start: date
    outcomes: list[str]
    cannot_drift: list[str]
    blockers: list[str]
    lesson: str
    last_review_at: datetime | None


class WeeklyPlanWriteRequest(APIModel):
    outcomes: list[str] | None = Field(default=None, max_length=3)
    cannot_drift: list[str] | None = None
    blockers: list[str] | None = None
    reviewed_at: datetime | None = None


class WeeklyReflectionWriteRequest(APIModel):
    lesson: str
    blockers: list[str] | None = None
    reviewed_at: datetime | None = None


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


class OpenLoopCreateRequest(APIModel):
    title: str
    source: str
    kind: OpenLoopKind = OpenLoopKind.TASK
    priority: OpenLoopPriority = OpenLoopPriority.MEDIUM
    notes: str = ""
    project_id: UUID | None = None
    due_at: datetime | None = None
    opened_at: datetime | None = None


class OpenLoopResolveRequest(APIModel):
    resolved_at: datetime | None = None


class ActiveOpenLoopsResponse(APIModel):
    loops: list[OpenLoopResponse]


def build_run_response(details: OrchestrationRunDetails) -> OrchestrationRunResponse:
    return OrchestrationRunResponse(
        run=_build_run_summary(details),
        signals=[_build_signal_response(signal) for signal in details.signals],
        alerts=[_build_alert_response(alert) for alert in details.alerts],
        controller_events=[
            _build_controller_event_response(event) for event in details.controller_events
        ],
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
        latest_controller_events=[
            _build_controller_event_response(event) for event in latest.controller_events
        ],
        previous_controller_events=[
            _build_controller_event_response(event) for event in previous.controller_events
        ],
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


def build_open_loop_response(loop: OpenLoop) -> OpenLoopResponse:
    return _build_open_loop_response(loop)


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
        controller_trajectory=_build_controller_trajectory_response(run.controller_trajectory),
        controller_cycle_state=run.controller_cycle_state,
        pending_approval=_build_pending_approval_response(details.pending_approval),
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


def _build_controller_trajectory_response(
    trajectory: ControllerTrajectory | None,
) -> ControllerTrajectoryResponse | None:
    if trajectory is None:
        return None
    return ControllerTrajectoryResponse(
        decision=_build_controller_decision_response(trajectory.decision),
        authority_result=_build_authority_result_response(trajectory.authority_result),
        action_plan=_build_action_plan_response(trajectory.action_plan),
        worker_run=_build_worker_run_response(trajectory.worker_run),
        verification_result=_build_verification_result_response(trajectory.verification_result),
        controller_outcome=trajectory.controller_outcome,
    )


def _build_controller_decision_response(
    decision: ControllerDecision,
) -> ControllerDecisionResponse:
    return ControllerDecisionResponse(
        id=decision.id,
        decision_type=decision.decision_type,
        decision_summary=decision.decision_summary,
        proposed_action=decision.proposed_action,
        requires_approval=decision.requires_approval,
        confidence=decision.confidence,
        action_intents=[
            _build_proposed_action_response(action) for action in decision.action_intents
        ],
    )


def _build_authority_result_response(result: AuthorityResult) -> AuthorityResultResponse:
    return AuthorityResultResponse(
        decision_id=result.decision_id,
        outcome=result.outcome,
        reason=result.reason,
        may_execute=result.may_execute,
    )


def _build_action_plan_response(plan: ActionPlan | None) -> ActionPlanResponse | None:
    if plan is None:
        return None
    return ActionPlanResponse(
        decision_id=plan.decision_id,
        summary=plan.summary,
        actions=[_build_proposed_action_response(action) for action in plan.actions],
        is_bounded=plan.is_bounded,
    )


def _build_worker_run_response(run: WorkerRun | None) -> WorkerRunResponse | None:
    if run is None:
        return None
    return WorkerRunResponse(
        decision_id=run.decision_id,
        executed_at=run.executed_at,
        observations=[
            _build_execution_observation_response(observation)
            for observation in run.observations
        ],
    )


def _build_execution_observation_response(
    observation: ExecutionObservationRecord,
) -> ExecutionObservationResponse:
    return ExecutionObservationResponse(
        success=observation.success,
        kind=observation.kind,
        target=observation.target,
        summary=observation.summary,
        details=observation.details,
    )


def _build_verification_result_response(
    result: VerificationResult | None,
) -> VerificationResultResponse | None:
    if result is None:
        return None
    return VerificationResultResponse(
        decision_id=result.decision_id,
        outcome=result.outcome,
        reason=result.reason,
    )


def _build_proposed_action_response(action: ProposedAction) -> ProposedActionResponse:
    return ProposedActionResponse(
        action_type=action.action_type,
        target=action.target,
        instructions=action.instructions,
    )


def _build_controller_event_response(event: ControllerEvent) -> ControllerEventResponse:
    return ControllerEventResponse(
        id=event.id,
        run_id=event.run_id,
        sequence_number=event.sequence_number,
        occurred_at=event.occurred_at,
        event_type=event.event_type,
        summary=event.summary,
        payload=dict(event.payload),
    )


def build_pending_approvals_response(
    approvals: list[PendingApproval],
) -> PendingApprovalsResponse:
    return PendingApprovalsResponse(
        approvals=[
            _build_pending_approval_response(approval)
            for approval in approvals
            if approval is not None
        ]
    )


def _build_pending_approval_response(
    approval: PendingApproval | None,
) -> PendingApprovalResponse | None:
    if approval is None:
        return None
    return PendingApprovalResponse(
        id=approval.id,
        run_id=approval.run_id,
        decision_id=approval.decision_id,
        status=approval.status,
        requested_at=approval.requested_at,
        resolved_at=approval.resolved_at,
        reason=approval.reason,
        decision_summary=approval.decision_summary,
        proposed_action=approval.proposed_action,
    )


class NoteCreateRequest(APIModel):
    title: str
    content: str


class TaskCreateRequest(APIModel):
    title: str
    notes: str = ""


class MemoryCreateRequest(APIModel):
    type: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class MemoryBlockCreateRequest(APIModel):
    layer: Literal["session", "daily", "weekly", "open_loop", "long_term", "self_model"]
    kind: str
    title: str
    body: str
    source: str = "manual"
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    subjectIds: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class MemoryCaptureExecutionRequest(APIModel):
    runId: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class CoordinationUpsertRequest(APIModel):
    payload: dict[str, Any]


class PolicyPayloadRequest(APIModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class OrchestrationClassifyRequest(APIModel):
    rawOutput: str
    currentPriority: str = ""
    latestDecision: str = ""


class ProjectDraftRequest(APIModel):
    goal: str
    source: Literal["goal", "active_project", "manual"] = "manual"


class PauseRequest(APIModel):
    reason: str = ""


class ExecutionCommandRequest(APIModel):
    command: str
    cwd: str = "."
    timeoutSeconds: int = 60


class ExecutionReadFileRequest(APIModel):
    path: str


class ExecutionWriteFileRequest(APIModel):
    path: str
    content: str
    actionId: str | None = None


class ExecutionPatchFileRequest(APIModel):
    path: str
    find: str
    replace: str
    actionId: str | None = None


class ExecutionGoalRequest(APIModel):
    goal: str
    maxCycles: int = 1
    planner: Literal["rule_based", "model"] = "rule_based"


class CodingLoopGoalRequest(APIModel):
    goal: str
    planner: Literal["rule_based", "model"] = "rule_based"
    executionRoot: str | None = None


class RetryApprovalApproveRequest(APIModel):
    approvedBy: str


class RetryApprovalRejectRequest(APIModel):
    reason: str
    rejectedBy: str | None = None


class CodingOperation(APIModel):
    type: Literal["write", "patch"]
    path: str
    content: str | None = None
    find: str | None = None
    replace: str | None = None


class CodingActionCreateRequest(APIModel):
    title: str
    summary: str = ""
    operations: list[CodingOperation] = Field(default_factory=list)
    verifyCommand: str = ""
    workingDirectory: str = "."
    approvalRequired: bool | None = None
