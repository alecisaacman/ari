from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from ...core.paths import DB_PATH
from .controller import plan_execution_goal, run_execution_goal
from .models import (
    ApprovalRequirement,
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

CodingLoopStatus = Literal[
    "success",
    "retryable_failure",
    "blocked",
    "unsafe",
    "ask_user",
    "requires_approval",
]


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
    approval_required_reason: str | None
    retry_proposal: dict[str, Any] | None
    retry_approval: CodingLoopRetryApproval | None
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
            "approval_required_reason": self.approval_required_reason,
            "retry_proposal": self.retry_proposal,
            "retry_approval": (
                None if self.retry_approval is None else self.retry_approval.to_dict()
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class CodingLoopRetryApproval:
    approval_id: str
    source_coding_loop_result_id: str
    source_preview_id: str | None
    source_execution_run_id: str | None
    original_goal: str
    proposed_retry_goal: str
    proposed_retry_action: dict[str, Any] | None
    proposed_retry_action_description: str
    reason: str
    failed_verification_summary: str
    approval: ApprovalRequirement
    approval_status: str
    retry_execution_requires_approval: bool
    proposed_action_requires_approval: bool
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "source_coding_loop_result_id": self.source_coding_loop_result_id,
            "source_preview_id": self.source_preview_id,
            "source_execution_run_id": self.source_execution_run_id,
            "original_goal": self.original_goal,
            "proposed_retry_goal": self.proposed_retry_goal,
            "proposed_retry_action": self.proposed_retry_action,
            "proposed_retry_action_description": self.proposed_retry_action_description,
            "reason": self.reason,
            "failed_verification_summary": self.failed_verification_summary,
            "approval": self.approval.to_dict(),
            "approval_status": self.approval_status,
            "retry_execution_requires_approval": self.retry_execution_requires_approval,
            "proposed_action_requires_approval": self.proposed_action_requires_approval,
            "created_at": self.created_at,
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
    approval_required_reason = _approval_required_reason(preview)
    if approval_required_reason is not None:
        return _result(
            loop_request,
            "requires_approval",
            approval_required_reason,
            preview_id=preview_id,
            preview=preview,
            approval_required_reason=approval_required_reason,
            created_at=created_at,
        )

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
    retry_proposal = (
        _retry_proposal(execution_run_payload)
        if status == "retryable_failure"
        else None
    )
    return _result(
        loop_request,
        status,
        reason,
        preview_id=preview_id,
        execution_run_id=execution_run.id,
        preview=preview,
        execution_run=execution_run_payload,
        retry_proposal=retry_proposal,
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


def _approval_required_reason(preview: dict[str, Any]) -> str | None:
    action = _single_preview_action(preview)
    if action is None:
        return None
    if not bool(action.get("requires_approval")):
        return None
    reason = str(
        action.get("reason")
        or preview.get("validation_error")
        or preview.get("reason")
        or "Action requires approval before execution."
    )
    return f"Approval required before one-step execution: {reason}"


def _single_preview_action(preview: dict[str, Any]) -> dict[str, Any] | None:
    decision = preview.get("decision")
    if not isinstance(decision, dict):
        return None
    plan = decision.get("plan")
    if not isinstance(plan, dict):
        return None
    actions = plan.get("actions")
    if not isinstance(actions, list) or len(actions) != 1:
        return None
    action = actions[0]
    return action if isinstance(action, dict) else None


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
    if _verification_failed(run):
        return "retryable_failure", str(
            run.get("reason") or "Action executed but verification failed."
        )
    reason = str(run.get("reason") or "One-step coding loop was blocked.")
    if status == "rejected" and _looks_unsafe(reason):
        return "unsafe", reason
    return "blocked", reason


def _verification_failed(run: dict[str, Any]) -> bool:
    results = run.get("results")
    if not isinstance(results, list) or not results:
        return False
    for result in results:
        if not isinstance(result, dict):
            continue
        action_results = result.get("action_results")
        if isinstance(action_results, list) and any(
            isinstance(item, dict) and not bool(item.get("verified", True))
            for item in action_results
        ):
            return True
        verification_results = result.get("verification_results")
        if isinstance(verification_results, list) and any(
            isinstance(item, dict) and not bool(item.get("verified", True))
            for item in verification_results
        ):
            return True
        if bool(result.get("success")) and not bool(result.get("verified")):
            return True
    return False


def _retry_proposal(run: dict[str, Any]) -> dict[str, Any] | None:
    results = run.get("results")
    first_result = results[0] if isinstance(results, list) and results else None
    if not isinstance(first_result, dict):
        return None

    failed_summary = _failed_verification_summary(first_result)
    suggested_next_action = _suggested_next_action(first_result)
    suggested_next_goal = _suggested_next_goal(first_result, failed_summary)
    approval_required = bool(_action_requires_approval(first_result))
    return {
        "reason": "Verification failed after one controlled action; propose one refined retry.",
        "failed_verification_summary": failed_summary,
        "suggested_next_goal": suggested_next_goal,
        "suggested_next_action": suggested_next_action,
        "approval_required": approval_required,
    }


def _suggested_next_action(result: dict[str, Any]) -> dict[str, Any] | None:
    action = _first_action(result)
    if action is None:
        return None
    suggested = dict(action)
    if str(suggested.get("type") or "") == "write_file":
        expected = _first_failed_expected(result)
        if expected is not None:
            suggested["content"] = expected
    return suggested


def _failed_verification_summary(result: dict[str, Any]) -> str:
    verification_results = result.get("verification_results")
    if isinstance(verification_results, list):
        for item in verification_results:
            if isinstance(item, dict) and not bool(item.get("verified", True)):
                expectation = item.get("expectation")
                if isinstance(expectation, dict):
                    target = str(expectation.get("target") or "<unknown>")
                    expected = expectation.get("expected")
                    if expected is not None:
                        return f"Verification failed for {target}; expected {expected!r}."
                    return f"Verification failed for {target}."
                return str(item.get("reason") or "Verification expectation failed.")

    action_results = result.get("action_results")
    if isinstance(action_results, list):
        for item in action_results:
            if isinstance(item, dict) and not bool(item.get("verified", True)):
                action = item.get("action")
                if isinstance(action, dict):
                    return f"Action verification failed for {action.get('type', '<unknown>')}."
                return str(item.get("error") or "Action verification failed.")

    return str(result.get("error") or "Verification failed.")


def _suggested_next_goal(result: dict[str, Any], failed_summary: str) -> str:
    action = _first_action(result)
    if action is None:
        return f"Propose one corrected action that addresses: {failed_summary}"
    action_type = str(action.get("type") or "<unknown>")
    if action_type == "write_file":
        path = str(action.get("path") or "<unknown>")
        expected = _first_failed_expected(result)
        if expected is not None:
            return f"write file {path} with {expected}"
        return f"Propose one corrected write_file action for {path}."
    return f"Propose one corrected {action_type} action that addresses: {failed_summary}"


def _first_failed_expected(result: dict[str, Any]) -> str | None:
    verification_results = result.get("verification_results")
    if not isinstance(verification_results, list):
        return None
    for item in verification_results:
        if not isinstance(item, dict) or bool(item.get("verified", True)):
            continue
        expectation = item.get("expectation")
        if isinstance(expectation, dict) and expectation.get("expected") is not None:
            return str(expectation["expected"])
    return None


def _first_action(result: dict[str, Any]) -> dict[str, Any] | None:
    action = result.get("action")
    if isinstance(action, dict):
        return action
    action_results = result.get("action_results")
    if not isinstance(action_results, list):
        return None
    for item in action_results:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if isinstance(action, dict):
            return action
    return None


def _action_requires_approval(result: dict[str, Any]) -> bool:
    plan = result.get("plan")
    if not isinstance(plan, dict):
        return False
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        return False
    action = actions[0]
    return isinstance(action, dict) and bool(action.get("requires_approval"))


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
    approval_required_reason: str | None = None,
    retry_proposal: dict[str, Any] | None = None,
    created_at: str,
) -> CodingLoopResult:
    result_id = f"coding-loop-result-{uuid4()}"
    retry_approval = (
        None
        if retry_proposal is None
        else _retry_approval_artifact(
            request,
            result_id,
            preview_id=preview_id,
            execution_run_id=execution_run_id,
            retry_proposal=retry_proposal,
            created_at=_now_iso(),
        )
    )
    return CodingLoopResult(
        id=result_id,
        request=request,
        status=status,
        reason=reason,
        preview_id=preview_id,
        execution_run_id=execution_run_id,
        preview=preview,
        execution_run=execution_run,
        approval_required_reason=approval_required_reason,
        retry_proposal=retry_proposal,
        retry_approval=retry_approval,
        created_at=created_at,
        updated_at=_now_iso(),
    )


def _retry_approval_artifact(
    request: CodingLoopRequest,
    result_id: str,
    *,
    preview_id: str | None,
    execution_run_id: str | None,
    retry_proposal: dict[str, Any],
    created_at: str,
) -> CodingLoopRetryApproval:
    proposed_action = retry_proposal.get("suggested_next_action")
    proposed_retry_action = proposed_action if isinstance(proposed_action, dict) else None
    proposed_action_requires_approval = bool(retry_proposal.get("approval_required"))
    approval = ApprovalRequirement.pending(
        reason="Approval is required before executing a coding-loop retry proposal.",
        authority_note=(
            "ARI produced this retry proposal after verification failed; "
            "the retry has not been executed."
        ),
    )
    return CodingLoopRetryApproval(
        approval_id=f"coding-loop-retry-approval-{result_id.removeprefix('coding-loop-result-')}",
        source_coding_loop_result_id=result_id,
        source_preview_id=preview_id,
        source_execution_run_id=execution_run_id,
        original_goal=request.goal,
        proposed_retry_goal=str(retry_proposal.get("suggested_next_goal") or ""),
        proposed_retry_action=proposed_retry_action,
        proposed_retry_action_description=_describe_retry_action(proposed_retry_action),
        reason=str(retry_proposal.get("reason") or "Retry proposal requires approval."),
        failed_verification_summary=str(
            retry_proposal.get("failed_verification_summary") or ""
        ),
        approval=approval,
        approval_status=approval.status,
        retry_execution_requires_approval=True,
        proposed_action_requires_approval=proposed_action_requires_approval,
        created_at=created_at,
    )


def _describe_retry_action(action: dict[str, Any] | None) -> str:
    if action is None:
        return "No concrete retry action was proposed."
    action_type = str(action.get("type") or "<unknown>")
    if action_type in {"read_file", "write_file", "patch_file"}:
        return f"{action_type} {action.get('path', '<unknown>')}"
    if action_type == "run_command":
        command = action.get("command")
        return f"run_command {command}" if command is not None else "run_command <unknown>"
    return action_type


def _string_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def _float_or_zero(raw: object) -> float:
    if isinstance(raw, bool):
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
