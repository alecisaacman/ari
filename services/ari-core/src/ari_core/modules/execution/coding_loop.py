from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from ...core.paths import DB_PATH
from .controller import plan_execution_goal, run_execution_goal
from .models import (
    ExecutionGoal,
    FailureContext,
    PlannerResult,
    RepoContext,
    VerificationExpectation,
    VerificationExpectationType,
    WorkerAction,
    WorkerActionType,
    WorkerPlan,
    _now_iso,
)
from .planners import ExecutionPlanner

CodingLoopStatus = Literal["success", "retryable_failure", "blocked", "unsafe", "ask_user"]


@dataclass(frozen=True, slots=True)
class CodingLoopRequest:
    goal: str
    execution_root: str | None = None
    id: str = field(default_factory=lambda: f"coding-loop-request-{uuid4()}")
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodingLoopResult:
    id: str
    request: CodingLoopRequest
    status: CodingLoopStatus
    reason: str
    preview_id: str | None
    execution_run_id: str | None
    preview: dict[str, Any] | None
    execution_run: dict[str, Any] | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "request": self.request.to_dict(),
            "status": self.status,
            "reason": self.reason,
            "preview_id": self.preview_id,
            "execution_run_id": self.execution_run_id,
            "preview": self.preview,
            "execution_run": self.execution_run,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def run_one_step_coding_loop(
    request: CodingLoopRequest | str,
    *,
    execution_root: Path | str | None = None,
    db_path: Path = DB_PATH,
    planner: ExecutionPlanner | None = None,
    planner_mode: str | None = None,
    planner_completion_fn: Any | None = None,
) -> CodingLoopResult:
    loop_request = _coerce_request(request, execution_root)
    created_at = _now_iso()
    goal = ExecutionGoal(objective=loop_request.goal, max_cycles=1)
    root = execution_root or loop_request.execution_root

    preview = plan_execution_goal(
        goal,
        execution_root=root,
        db_path=db_path,
        planner=planner,
        planner_mode=planner_mode,
        planner_completion_fn=planner_completion_fn,
    )
    preview_id = _string_or_none(preview.get("id"))
    preview_block = _preview_block_reason(preview)
    if preview_block is not None:
        return _result(
            loop_request,
            _classify_block(preview_block),
            preview_block,
            preview_id=preview_id,
            preview=preview,
            created_at=created_at,
        )

    plan = _plan_from_preview(preview)
    if isinstance(plan, str):
        return _result(
            loop_request,
            _classify_block(plan),
            plan,
            preview_id=preview_id,
            preview=preview,
            created_at=created_at,
        )

    execution_run = run_execution_goal(
        goal,
        execution_root=root,
        db_path=db_path,
        planner=_FrozenPlanPlanner(plan, preview),
    )
    execution_run_payload = execution_run.to_dict()
    status, reason = _classify_execution_run(execution_run_payload)
    return _result(
        loop_request,
        status,
        reason,
        preview_id=preview_id,
        execution_run_id=execution_run.id,
        preview=preview,
        execution_run=execution_run_payload,
        created_at=created_at,
    )


class _FrozenPlanPlanner:
    planner_name = "coding_loop_preview"

    def __init__(self, plan: WorkerPlan, preview: dict[str, Any]) -> None:
        self.selected_plan = plan
        self.preview = preview

    def plan(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: FailureContext | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        del goal, repo_context, failure_context, memory_context
        decision = self.preview.get("decision")
        reason = self.preview.get("reason")
        confidence = 0.0
        if isinstance(decision, dict):
            confidence = _float_or_zero(decision.get("confidence"))
        return PlannerResult(
            status="act",
            reason=str(reason or "Execute the single validated preview action."),
            confidence=confidence,
            planner_name=self.planner_name,
            plan=self.selected_plan,
        )


def _coerce_request(
    request: CodingLoopRequest | str,
    execution_root: Path | str | None,
) -> CodingLoopRequest:
    if isinstance(request, CodingLoopRequest):
        return request
    return CodingLoopRequest(
        goal=request,
        execution_root=None if execution_root is None else str(execution_root),
    )


def _preview_block_reason(preview: dict[str, Any]) -> str | None:
    status = str(preview.get("status") or "")
    if status != "planned":
        return str(preview.get("reason") or "Planner did not produce a runnable action.")
    decision = preview.get("decision")
    if not isinstance(decision, dict):
        return "Planner preview did not include an inspectable decision."
    plan = decision.get("plan")
    if not isinstance(plan, dict):
        return "Planner preview did not include a bounded action plan."
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        return "Planner preview did not include a candidate action."
    if len(actions) != 1:
        return "One-step coding loop requires exactly one candidate action."
    return None


def _plan_from_preview(preview: dict[str, Any]) -> WorkerPlan | str:
    decision = cast(dict[str, Any], preview["decision"])
    raw_plan = decision.get("plan")
    if not isinstance(raw_plan, dict):
        return "Planner preview did not include a bounded action plan."

    raw_actions = raw_plan.get("actions")
    if not isinstance(raw_actions, list) or len(raw_actions) != 1:
        return "One-step coding loop requires exactly one candidate action."

    action = _action_from_payload(raw_actions[0])
    if isinstance(action, str):
        return action

    raw_verification = raw_plan.get("verification")
    verification = _verification_from_payload(raw_verification)
    if isinstance(verification, str):
        return verification

    return WorkerPlan(
        actions=(action,),
        verification=tuple(verification),
        reason=str(raw_plan.get("reason") or preview.get("reason") or "One-step preview plan."),
    )


def _action_from_payload(raw_action: object) -> WorkerAction | str:
    if not isinstance(raw_action, dict):
        return "Planner preview action was not inspectable."
    payload = raw_action.get("payload")
    if not isinstance(payload, dict):
        return "Planner preview action did not include a payload."
    return WorkerAction(
        action_type=cast(WorkerActionType, str(raw_action.get("action_type") or "")),
        payload=dict(payload),
        reason=str(raw_action.get("reason") or "Execute one validated coding action."),
        requires_approval=bool(raw_action.get("requires_approval")),
    )


def _verification_from_payload(raw_verification: object) -> list[VerificationExpectation] | str:
    if raw_verification is None:
        return []
    if not isinstance(raw_verification, list):
        return "Planner preview verification was not inspectable."
    expectations: list[VerificationExpectation] = []
    for raw_expectation in raw_verification:
        if not isinstance(raw_expectation, dict):
            return "Planner preview verification item was not inspectable."
        expectations.append(
            VerificationExpectation(
                expectation_type=cast(
                    VerificationExpectationType,
                    str(
                        raw_expectation.get("expectation_type")
                        or raw_expectation.get("type")
                        or ""
                    ),
                ),
                target=str(raw_expectation.get("target") or ""),
                expected=(
                    None
                    if raw_expectation.get("expected") is None
                    else str(raw_expectation["expected"])
                ),
                reason=str(raw_expectation.get("reason") or "Verify one-step action."),
            )
        )
    return expectations


def _classify_execution_run(run: dict[str, Any]) -> tuple[CodingLoopStatus, str]:
    status = str(run.get("status") or "")
    if status == "completed":
        return "success", str(run.get("reason") or "One-step coding loop completed.")

    results = run.get("results")
    first_result = results[0] if isinstance(results, list) and results else {}
    if isinstance(first_result, dict) and bool(first_result.get("retryable")):
        return "retryable_failure", str(
            first_result.get("error") or run.get("reason") or "Retryable execution failure."
        )
    reason = str(run.get("reason") or "One-step coding loop was blocked.")
    if status == "rejected" and _looks_unsafe(reason):
        return "unsafe", reason
    return "blocked", reason


def _classify_block(reason: str) -> CodingLoopStatus:
    lowered = reason.lower()
    if "no bounded execution action matched" in lowered or "did not include" in lowered:
        return "ask_user"
    if _looks_unsafe(reason):
        return "unsafe"
    return "blocked"


def _looks_unsafe(reason: str) -> bool:
    lowered = reason.lower()
    return any(
        token in lowered
        for token in (
            "allowlist",
            "not allowed",
            "outside repocontext",
            "policy",
            "unsafe",
            "escapes execution root",
            "requires approval",
        )
    )


def _result(
    request: CodingLoopRequest,
    status: CodingLoopStatus,
    reason: str,
    *,
    preview_id: str | None = None,
    execution_run_id: str | None = None,
    preview: dict[str, Any] | None = None,
    execution_run: dict[str, Any] | None = None,
    created_at: str,
) -> CodingLoopResult:
    return CodingLoopResult(
        id=f"coding-loop-result-{uuid4()}",
        request=request,
        status=status,
        reason=reason,
        preview_id=preview_id,
        execution_run_id=execution_run_id,
        preview=preview,
        execution_run=execution_run,
        created_at=created_at,
        updated_at=_now_iso(),
    )


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def _float_or_zero(raw: object) -> float:
    if isinstance(raw, bool):
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
