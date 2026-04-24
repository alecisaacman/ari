from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

WorkerActionType = Literal["read_file", "write_file", "patch_file", "run_command"]
WorkerDecisionStatus = Literal["act", "reject", "retry", "stop"]
ExecutionRunStatus = Literal["completed", "failed", "rejected", "exhausted"]
VerificationExpectationType = Literal["action_success", "file_content", "path_exists"]


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionGoal:
    objective: str
    max_cycles: int = 1
    id: str = field(default_factory=lambda: f"goal-{uuid4()}")
    created_at: str = field(default_factory=lambda: _now_iso())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepoContext:
    repo_root: str
    git_available: bool
    git_dirty: bool
    changed_paths: tuple[str, ...] = ()
    current_branch: str | None = None
    files_sample: tuple[str, ...] = ()
    directories_sample: tuple[str, ...] = ()
    package_manifests: tuple[str, ...] = ()
    test_commands: tuple[tuple[str, ...], ...] = ()
    language_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkerAction:
    action_type: WorkerActionType
    payload: dict[str, Any]
    reason: str
    requires_approval: bool = False
    id: str = field(default_factory=lambda: f"action-{uuid4()}")

    def to_execution_action(self) -> dict[str, Any]:
        return {"type": self.action_type, **self.payload}

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["execution_action"] = self.to_execution_action()
        return payload


@dataclass(frozen=True, slots=True)
class VerificationExpectation:
    expectation_type: VerificationExpectationType
    target: str
    expected: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkerPlan:
    actions: tuple[WorkerAction, ...]
    verification: tuple[VerificationExpectation, ...]
    reason: str
    id: str = field(default_factory=lambda: f"plan-{uuid4()}")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "actions": [action.to_dict() for action in self.actions],
            "verification": [expectation.to_dict() for expectation in self.verification],
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class FailureContext:
    cycle_index: int
    reason: str
    result: dict[str, Any]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlannerResult:
    status: WorkerDecisionStatus
    reason: str
    confidence: float
    planner_name: str
    plan: WorkerPlan | None = None
    failure_context: FailureContext | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "confidence": self.confidence,
            "planner_name": self.planner_name,
            "plan": None if self.plan is None else self.plan.to_dict(),
            "failure_context": (
                None if self.failure_context is None else self.failure_context.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class WorkerDecision:
    status: WorkerDecisionStatus
    reason: str
    confidence: float
    cycle_index: int
    action: WorkerAction | None = None
    plan: WorkerPlan | None = None
    planner_name: str = "unknown"
    failure_context: FailureContext | None = None
    id: str = field(default_factory=lambda: f"decision-{uuid4()}")
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "reason": self.reason,
            "confidence": self.confidence,
            "cycle_index": self.cycle_index,
            "action": None if self.action is None else self.action.to_dict(),
            "plan": None if self.plan is None else self.plan.to_dict(),
            "planner_name": self.planner_name,
            "failure_context": (
                None if self.failure_context is None else self.failure_context.to_dict()
            ),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRun:
    id: str
    goal: ExecutionGoal
    status: ExecutionRunStatus
    reason: str
    cycles_run: int
    repo_contexts: tuple[RepoContext, ...]
    decisions: tuple[WorkerDecision, ...]
    results: tuple[dict[str, Any], ...]
    created_at: str
    updated_at: str
    planner_config: dict[str, Any] = field(default_factory=dict)
    persisted_run: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "goal": self.goal.to_dict(),
            "status": self.status,
            "reason": self.reason,
            "cycles_run": self.cycles_run,
            "repo_contexts": [context.to_dict() for context in self.repo_contexts],
            "decisions": [decision.to_dict() for decision in self.decisions],
            "results": list(self.results),
            "planner_config": self.planner_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "persisted_run": self.persisted_run,
        }


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
