from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
