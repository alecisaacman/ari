from __future__ import annotations

from pathlib import Path

from ari_state import (
    ActionType,
    AuthorityOutcome,
    AuthorityResult,
    ControllerDecision,
    DecisionType,
)

from ari_core.executor import ALLOWED_COMMANDS, REPO_ROOT

ALLOW_CONFIDENCE_THRESHOLD = 0.75
DEFER_CONFIDENCE_THRESHOLD = 0.5
MAX_BOUNDED_ACTIONS = 4


def evaluate_decision_authority(decision: ControllerDecision) -> AuthorityResult:
    if decision.decision_type != DecisionType.ACT:
        return _result(
            decision=decision,
            outcome=AuthorityOutcome.DEFER,
            reason="Only act decisions are dispatchable in controller integration v1.",
        )

    if not decision.action_intents:
        return _result(
            decision=decision,
            outcome=AuthorityOutcome.DEFER,
            reason="Decision has no bounded proposed actions to dispatch.",
        )

    if decision.requires_approval:
        return _result(
            decision=decision,
            outcome=AuthorityOutcome.REQUIRE_APPROVAL,
            reason="Decision is explicitly marked as requiring approval.",
        )

    if decision.confidence < DEFER_CONFIDENCE_THRESHOLD:
        return _result(
            decision=decision,
            outcome=AuthorityOutcome.DEFER,
            reason="Decision confidence is below the minimum execution threshold.",
        )

    if decision.confidence < ALLOW_CONFIDENCE_THRESHOLD:
        return _result(
            decision=decision,
            outcome=AuthorityOutcome.REQUIRE_APPROVAL,
            reason="Decision confidence is below the autonomous allow threshold.",
        )

    if len(decision.action_intents) > MAX_BOUNDED_ACTIONS:
        return _result(
            decision=decision,
            outcome=AuthorityOutcome.DEFER,
            reason="Decision exceeds the bounded action-count limit for v1 dispatch.",
        )

    for action in decision.action_intents:
        if action.action_type == ActionType.READ_FILE:
            if _resolve_repo_path(action.target) is None:
                return _result(
                    decision=decision,
                    outcome=AuthorityOutcome.DENY,
                    reason="Read action escapes the repository boundary.",
                )
            continue

        if action.action_type == ActionType.RUN_COMMAND:
            if action.target.strip() not in ALLOWED_COMMANDS:
                return _result(
                    decision=decision,
                    outcome=AuthorityOutcome.DENY,
                    reason="Run command is outside the bounded allowlist.",
                )
            continue

        if action.action_type in {ActionType.ASK_USER, ActionType.EDIT_FILE}:
            return _result(
                decision=decision,
                outcome=AuthorityOutcome.REQUIRE_APPROVAL,
                reason=f"{action.action_type} actions require explicit approval.",
            )

        return _result(
            decision=decision,
            outcome=AuthorityOutcome.DENY,
            reason=f"Unsupported action type for autonomous dispatch: {action.action_type}.",
        )

    return _result(
        decision=decision,
        outcome=AuthorityOutcome.ALLOW,
        reason="Decision is bounded, within confidence threshold, and safe to execute.",
    )


def _result(
    *,
    decision: ControllerDecision,
    outcome: AuthorityOutcome,
    reason: str,
) -> AuthorityResult:
    return AuthorityResult(
        decision_id=decision.id,
        outcome=outcome,
        reason=reason,
        may_execute=outcome == AuthorityOutcome.ALLOW,
    )


def _resolve_repo_path(target: str) -> Path | None:
    resolved_target = (REPO_ROOT / target).resolve()
    try:
        resolved_target.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return resolved_target
