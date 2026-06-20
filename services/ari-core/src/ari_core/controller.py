from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ari_state import (
    ActionPlan,
    AuthorityResult,
    ControllerDecision,
    ControllerTrajectory,
    ControlOutcome,
    ExecutionObservationRecord,
    VerificationOutcome,
    VerificationResult,
    WorkerRun,
)

from ari_core.authority import evaluate_decision_authority
from ari_core.evaluator import evaluate_observations
from ari_core.execution_types import ActionIntent, ExecutionObservation
from ari_core.executor import execute_intent

IntentExecutor = Callable[[ActionIntent], ExecutionObservation]


def run_controller_cycle(
    decision: ControllerDecision,
    *,
    executed_at: datetime,
    intent_executor: IntentExecutor = execute_intent,
) -> ControllerTrajectory:
    authority_result = evaluate_decision_authority(decision)
    if not authority_result.may_execute:
        return ControllerTrajectory(
            decision=decision,
            authority_result=authority_result,
            controller_outcome=_blocked_outcome(authority_result.outcome),
        )
    return _execute_decision(
        decision=decision,
        authority_result=authority_result,
        executed_at=executed_at,
        intent_executor=intent_executor,
    )


def resume_controller_cycle(
    trajectory: ControllerTrajectory,
    *,
    resumed_at: datetime,
    intent_executor: IntentExecutor = execute_intent,
) -> ControllerTrajectory:
    return _execute_decision(
        decision=trajectory.decision,
        authority_result=trajectory.authority_result,
        executed_at=resumed_at,
        intent_executor=intent_executor,
    )


def _execute_decision(
    *,
    decision: ControllerDecision,
    authority_result: AuthorityResult,
    executed_at: datetime,
    intent_executor: IntentExecutor,
) -> ControllerTrajectory:
    action_plan = ActionPlan(
        decision_id=decision.id,
        summary=decision.proposed_action,
        actions=[action.model_copy(deep=True) for action in decision.action_intents],
        is_bounded=True,
    )
    runtime_intents = [
        ActionIntent(
            action_type=action.action_type,
            target=action.target,
            instructions=action.instructions,
        )
        for action in action_plan.actions
    ]
    observations = [intent_executor(intent) for intent in runtime_intents]
    worker_run = WorkerRun(
        decision_id=decision.id,
        executed_at=executed_at,
        observations=[
            ExecutionObservationRecord(
                success=observation.success,
                kind=observation.kind,
                target=observation.target,
                summary=observation.summary,
                details=observation.details,
            )
            for observation in observations
        ],
    )
    verification_result = _build_verification_result(
        decision=decision,
        intents=runtime_intents,
        observations=observations,
    )
    return ControllerTrajectory(
        decision=decision,
        authority_result=authority_result,
        action_plan=action_plan,
        worker_run=worker_run,
        verification_result=verification_result,
        controller_outcome=_final_outcome(verification_result.outcome),
    )


def _build_verification_result(
    *,
    decision: ControllerDecision,
    intents: list[ActionIntent],
    observations: list[ExecutionObservation],
) -> VerificationResult:
    evaluation = evaluate_observations(intents, observations)
    outcome = VerificationOutcome(evaluation.lower())
    if outcome == VerificationOutcome.SUCCESS:
        reason = "All dispatched actions completed successfully."
    elif outcome == VerificationOutcome.RETRY:
        reason = "One or more dispatched actions failed verification."
    else:
        reason = "Execution requires user input before the cycle can continue."
    return VerificationResult(
        decision_id=decision.id,
        outcome=outcome,
        reason=reason,
    )


def _blocked_outcome(authority_outcome: str) -> ControlOutcome:
    if authority_outcome == "require_approval":
        return ControlOutcome.REQUIRE_APPROVAL
    if authority_outcome == "deny":
        return ControlOutcome.DENIED
    return ControlOutcome.DEFERRED


def _final_outcome(verification_outcome: VerificationOutcome) -> ControlOutcome:
    if verification_outcome == VerificationOutcome.SUCCESS:
        return ControlOutcome.SUCCESS
    return ControlOutcome.RETRY
