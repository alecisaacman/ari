from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ari_state.enums import (
    ActionType,
    AlertChannel,
    AlertEscalationLevel,
    AlertStatus,
    AuthorityOutcome,
    ControllerCycleState,
    ControllerEventType,
    ControlOutcome,
    DecisionType,
    EventCategory,
    OpenLoopKind,
    OpenLoopPriority,
    OpenLoopStatus,
    PendingApprovalStatus,
    ProjectStatus,
    SignalSeverity,
    SkillKind,
    SkillRegistrationKind,
    VerificationOutcome,
)


class ARIModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")


ARIId = UUID | str


class DailyState(ARIModel):
    date: date
    priorities: list[str] = Field(default_factory=list, max_length=3)
    win_condition: str = ""
    movement: bool | None = None
    stress: int | None = Field(default=None, ge=1, le=10)
    next_action: str = ""
    last_check_at: datetime | None = None


class WeeklyState(ARIModel):
    week_start: date
    outcomes: list[str] = Field(default_factory=list, max_length=3)
    cannot_drift: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    lesson: str = ""
    last_review_at: datetime | None = None


class OpenLoop(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    status: OpenLoopStatus = OpenLoopStatus.OPEN
    kind: OpenLoopKind = OpenLoopKind.TASK
    priority: OpenLoopPriority = OpenLoopPriority.MEDIUM
    source: str
    notes: str = ""
    company: str | None = None
    project_id: UUID | None = None
    opened_at: datetime
    due_at: datetime | None = None
    last_touched_at: datetime | None = None


class OpenLoopEnrichment(ARIModel):
    """Structured findings attached to an open loop by an automatically
    triggered skill (e.g. company intel for a job_application loop).
    Kept as its own table, not a column on OpenLoop, so a loop can
    accumulate multiple enrichment passes over time (e.g. a fresh search
    right before an interview)."""

    id: UUID = Field(default_factory=uuid4)
    loop_id: UUID
    kind: str
    company: str
    summary: str = ""
    findings: list[dict[str, object]] = Field(default_factory=list)
    source: str
    created_at: datetime


class Project(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    slug: str
    name: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class Signal(ARIModel):
    id: ARIId = Field(default_factory=uuid4)
    state_date: date | None = None
    kind: str
    fingerprint: str = ""
    severity: SignalSeverity
    summary: str
    reason: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    related_entity_type: str | None = None
    related_entity_id: ARIId | None = None
    detected_at: datetime


class EvidenceItem(ARIModel):
    kind: str
    summary: str
    entity_type: str | None = None
    entity_id: ARIId | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class Event(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    source: str
    category: EventCategory = EventCategory.CAPTURE
    occurred_at: datetime
    title: str
    body: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    normalized_text: str = ""


class Alert(ARIModel):
    id: ARIId = Field(default_factory=uuid4)
    state_date: date | None = None
    fingerprint: str = ""
    status: AlertStatus = AlertStatus.PENDING
    channel: AlertChannel
    escalation_level: AlertEscalationLevel = AlertEscalationLevel.VISIBLE
    title: str
    message: str
    reason: str
    source_signal_ids: list[ARIId] = Field(default_factory=list)
    created_at: datetime
    sent_at: datetime | None = None


class ProposedAction(ARIModel):
    action_type: ActionType
    target: str
    instructions: str


class ControllerDecision(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    decision_type: DecisionType = DecisionType.ACT
    decision_summary: str
    proposed_action: str
    requires_approval: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    action_intents: list[ProposedAction] = Field(default_factory=list)


class AuthorityResult(ARIModel):
    decision_id: UUID
    outcome: AuthorityOutcome
    reason: str
    may_execute: bool


class ActionPlan(ARIModel):
    decision_id: UUID
    summary: str
    actions: list[ProposedAction] = Field(default_factory=list)
    is_bounded: bool = True


class ExecutionObservationRecord(ARIModel):
    success: bool
    kind: str
    target: str
    summary: str
    details: str


class WorkerRun(ARIModel):
    decision_id: UUID
    executed_at: datetime
    observations: list[ExecutionObservationRecord] = Field(default_factory=list)


class VerificationResult(ARIModel):
    decision_id: UUID
    outcome: VerificationOutcome
    reason: str


class ControllerTrajectory(ARIModel):
    decision: ControllerDecision
    authority_result: AuthorityResult
    action_plan: ActionPlan | None = None
    worker_run: WorkerRun | None = None
    verification_result: VerificationResult | None = None
    controller_outcome: ControlOutcome


class ControllerEvent(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    sequence_number: int = Field(ge=0)
    occurred_at: datetime
    event_type: ControllerEventType
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)


class PendingApproval(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    decision_id: UUID
    status: PendingApprovalStatus = PendingApprovalStatus.PENDING
    requested_at: datetime
    resolved_at: datetime | None = None
    reason: str
    decision_summary: str
    proposed_action: str


class OrchestrationRun(ARIModel):
    id: ARIId = Field(default_factory=uuid4)
    state_date: date
    state_fingerprint: str
    executed_at: datetime
    signal_ids: list[ARIId] = Field(default_factory=list)
    alert_ids: list[ARIId] = Field(default_factory=list)
    controller_trajectory: ControllerTrajectory | None = None
    controller_cycle_state: ControllerCycleState | None = None


class ConversationState(ARIModel):
    """Durable memory for a brain conversation channel (e.g. iMessage):
    the ingestion cursor and the rolling message history sent to Claude.
    Replaces what used to be ad hoc JSON files in state/."""

    id: UUID = Field(default_factory=uuid4)
    channel: str
    cursor: int = 0
    messages: list[dict[str, object]] = Field(default_factory=list)
    updated_at: datetime


class SkillRegistration(ARIModel):
    """A skill the brain can call. `encrypted_token` is ciphertext, never
    a plaintext credential — see ari_core.skills for the Fernet
    encrypt/decrypt boundary. Registering a new MCP-backed skill (e.g.
    Google Calendar) is one row here plus an OAuth token, not new code."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    kind: SkillRegistrationKind = SkillRegistrationKind.MCP
    mcp_url: str
    enabled: bool = True
    encrypted_token: str | None = None
    created_at: datetime
    updated_at: datetime


class SkillInvocation(ARIModel):
    """One audit row per skill call the brain made, regardless of source.
    This is a record of what happened, written after the fact — it is not
    an authorization gate. For MCP/web_search, ARI never has a pre-execution
    moment to intercept (Anthropic resolves the call server-side before the
    response reaches ARI), so this table is necessarily detective, not
    preventive. See ari_core.skills.record_skill_invocation."""

    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime
    channel: str
    skill_kind: SkillKind
    skill_name: str
    tool_name: str
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)
    is_error: bool = False
