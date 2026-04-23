from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Sequence

from .dispatch import DispatchResult


EvaluationStatus = Literal["completed", "blocked", "escalated"]
LoopControlStatus = Literal["stop", "wait_for_approval", "escalate"]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    decision_reference: str
    status: EvaluationStatus
    reason: str
    next_step: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LoopControlResult:
    status: LoopControlStatus
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def evaluate_dispatch_result(result: DispatchResult) -> EvaluationResult:
    if result.status == "executed":
        execution_result = result.execution_result or {}
        if execution_result.get("success") is True:
            return EvaluationResult(
                decision_reference=result.decision_reference,
                status="completed",
                reason="The authorized action executed successfully.",
                next_step="stop",
            )
        if _is_retryable_failure(execution_result):
            return EvaluationResult(
                decision_reference=result.decision_reference,
                status="escalated",
                reason="The action failed in a retryable way; ARI can attempt another pass later.",
                next_step="retry_allowed",
            )
        return EvaluationResult(
            decision_reference=result.decision_reference,
            status="escalated",
            reason="The action executed but did not succeed; manual inspection is required.",
            next_step="inspect_failure",
        )

    if result.status == "requires_approval":
        return EvaluationResult(
            decision_reference=result.decision_reference,
            status="blocked",
            reason=result.reason,
            next_step="request_approval",
        )

    return EvaluationResult(
        decision_reference=result.decision_reference,
        status="escalated",
        reason=result.reason,
        next_step="review_policy_gap",
    )


def _is_retryable_failure(execution_result: dict[object, object]) -> bool:
    if execution_result.get("retryable") is True:
        return True

    classification = execution_result.get("classification")
    if isinstance(classification, dict) and classification.get("retryable") is True:
        return True

    stderr = str(execution_result.get("stderr", "")).lower()
    stdout = str(execution_result.get("stdout", "")).lower()
    combined = f"{stdout}\n{stderr}"
    patterns = ("timed out", "timeout", "temporar", "eaddrinuse", "connection reset", "network")
    return any(pattern in combined for pattern in patterns)


def summarize_evaluation_results(results: Sequence[EvaluationResult]) -> LoopControlResult:
    if not results:
        return LoopControlResult(
            status="stop",
            reason="No decisions required action in this orchestration cycle.",
        )

    escalated = [result for result in results if result.status == "escalated"]
    if escalated:
        return LoopControlResult(
            status="escalate",
            reason=escalated[0].reason,
        )

    blocked = [result for result in results if result.status == "blocked"]
    if blocked:
        return LoopControlResult(
            status="wait_for_approval",
            reason=blocked[0].reason,
        )

    return LoopControlResult(
        status="stop",
        reason="Authorized decisions completed without requiring escalation.",
    )
