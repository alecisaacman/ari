from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionTaskSpec:
    task_id: str
    objective: str
    success_criteria: tuple[str, ...]
    requirements: tuple[str, ...] = ()
    linked_project_id: str | None = None
    linked_task_id: str | None = None
    linked_milestone_id: str | None = None
    linked_goal_id: str | None = None
    authority_snapshot_ref: str | None = None
    authority_snapshot_hash: str | None = None
    restrictions: tuple[str, ...] = ()
    authority_scope: dict[str, Any] = field(default_factory=dict)
    approval_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CheckpointState:
    objective: str
    success_criteria: tuple[str, ...]
    current_plan: dict[str, Any] = field(default_factory=dict)
    completed_steps: tuple[dict[str, Any], ...] = ()
    pending_steps: tuple[dict[str, Any], ...] = ()
    important_findings: tuple[dict[str, Any], ...] = ()
    assumptions: tuple[dict[str, Any], ...] = ()
    decisions: tuple[dict[str, Any], ...] = ()
    artifacts: tuple[dict[str, Any], ...] = ()
    actions_taken: tuple[dict[str, Any], ...] = ()
    verification_results: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    provider: dict[str, Any] = field(default_factory=dict)
    capacity_observations: tuple[dict[str, Any], ...] = ()
    next_recommended_action: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    restrictions: tuple[str, ...] = ()
    authority_scope: dict[str, Any] = field(default_factory=dict)
    approval_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionResultContract:
    task_id: str
    status: str
    objective: str
    outcome: str
    success_criteria_evaluation: tuple[dict[str, Any], ...]
    artifacts: tuple[dict[str, Any], ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    verification: tuple[dict[str, Any], ...] = ()
    unresolved_issues: tuple[dict[str, Any], ...] = ()
    decisions_requiring_alec: tuple[dict[str, Any], ...] = ()
    recommended_next_action: str | None = None
    provider_provenance: tuple[dict[str, Any], ...] = ()
    execution_history: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskLifecycleState(StrEnum):
    ACTIVE = "active"
    WAITING_FOR_WORKER = "waiting_for_worker"
    RECOVERING = "recovering"
    AWAITING_CONTINUATION_ACKNOWLEDGEMENT = "awaiting_continuation_acknowledgement"
    EXECUTION_READY = "execution_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptLifecycleState(StrEnum):
    ACTIVE = "active"
    WAITING_FOR_WORKER = "waiting_for_worker"
    STALE = "stale"
    RECOVERING = "recovering"
    AWAITING_CONTINUATION_ACKNOWLEDGEMENT = "awaiting_continuation_acknowledgement"
    EXECUTION_READY = "execution_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecoveryClassification(StrEnum):
    HEALTHY = "healthy"
    WAITING_FOR_WORKER = "waiting_for_worker"
    STALE = "stale"
    TERMINAL = "terminal"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    RECOVERABLE = "recoverable"
    UNRECOVERABLE = "unrecoverable"


class ResumeDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    BLOCKED = "blocked"


class ActionIdempotencyState(StrEnum):
    NEVER_ATTEMPTED = "never_attempted"
    AUTHORIZED_NOT_RUN = "authorized_not_run"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED_BEFORE_EFFECT = "failed_before_effect"
    EFFECT_UNCERTAIN = "effect_may_have_occurred"
    VERIFICATION_FAILED = "verification_failed"
    ALREADY_COMPLETED = "already_completed"


@dataclass(frozen=True, slots=True)
class RecoveredActionProposal:
    task_id: str
    attempt_id: str
    checkpoint_id: str
    action_id: str
    proposed_action: dict[str, Any]
    action_digest: str
    target_resources: tuple[str, ...]
    authority_snapshot_ref: str | None
    authority_snapshot_hash: str | None
    authority_scope: dict[str, Any]
    approval_required: bool
    approval_reference: str | None
    restrictions: tuple[str, ...]
    idempotency_key: str
    idempotency_state: ActionIdempotencyState
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RecoveredActionResumeResult:
    task_id: str
    attempt_id: str
    decision_id: str
    decision: ResumeDecision
    reason: str
    proposal: RecoveredActionProposal
    executed: bool
    idempotency_state: ActionIdempotencyState
    approval_reference: str | None = None
    pre_checkpoint_id: str | None = None
    result_checkpoint_id: str | None = None
    verification_checkpoint_id: str | None = None
    result: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkerLease:
    owner: str
    started_at: str
    expires_at: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class WorkerSession:
    session_id: str
    task_id: str
    attempt_id: str
    worker_identity: str
    backend_id: str
    state: AttemptLifecycleState
    lease: WorkerLease
    prior_attempt_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerHeartbeat:
    heartbeat_id: str
    task_id: str
    attempt_id: str
    session_id: str
    lease_owner: str
    observed_at: str
    lease_expires_at: str


@dataclass(frozen=True, slots=True)
class ContinuationPacket:
    packet_id: str
    task_id: str
    attempt_id: str
    prior_attempt_id: str
    checkpoint_id: str
    objective: str
    success_criteria: tuple[str, ...]
    current_plan: dict[str, Any]
    completed_steps: tuple[dict[str, Any], ...]
    pending_steps: tuple[dict[str, Any], ...]
    important_findings: tuple[dict[str, Any], ...]
    assumptions: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    artifacts: tuple[dict[str, Any], ...]
    actions_taken: tuple[dict[str, Any], ...]
    verification_results: tuple[dict[str, Any], ...]
    restrictions: tuple[str, ...]
    authority_scope: dict[str, Any]
    approval_state: dict[str, Any]
    authority_snapshot_ref: str | None
    authority_snapshot_hash: str | None
    prior_attempt_provenance: dict[str, Any]
    recovery_reason: str
    recommended_next_action: str | None
    acknowledgement_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContinuationAcknowledgement:
    objective: str
    completed_steps: tuple[dict[str, Any], ...]
    pending_steps: tuple[dict[str, Any], ...]
    restrictions: tuple[str, ...]
    authority_scope: dict[str, Any]
    authority_snapshot_ref: str | None
    next_proposed_action: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AttemptRecoveryDecision:
    task_id: str
    attempt_id: str
    classification: RecoveryClassification
    reason: str
    recoverable: bool
    latest_checkpoint_id: str | None
    replacement_attempt_id: str | None = None
    continuation_packet_id: str | None = None
