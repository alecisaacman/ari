from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ari_core import build_controller_decision, evaluate_decision_authority, run_controller_cycle
from ari_core.decision_translate import translate_worker_decision
from ari_core.evaluator import evaluate_observations
from ari_core.execution_types import (
    ActionIntent,
    ActionType,
    ExecutionObservation,
    parse_worker_decision,
)
from ari_core.executor import execute_intent
from ari_core.worker_client import AriWorkerClient
from ari_state import (
    AuthorityOutcome,
    ControllerDecision,
    ControlOutcome,
    DecisionType,
    ProposedAction,
)


def _controller_decision(
    *,
    confidence: float = 0.9,
    requires_approval: bool = False,
    decision_type: DecisionType = DecisionType.ACT,
    actions: list[ProposedAction] | None = None,
) -> ControllerDecision:
    return ControllerDecision(
        decision_type=decision_type,
        decision_summary="Inspect the target test file.",
        proposed_action="Inspect the target test file.",
        requires_approval=requires_approval,
        confidence=confidence,
        action_intents=actions
        or [
            ProposedAction(
                action_type=ActionType.READ_FILE,
                target="tests/unit/test_models.py",
                instructions="Read the target test before changing anything.",
            )
        ],
    )


def test_parse_and_translate_worker_decision_returns_typed_action_intents() -> None:
    payload = {
        "decision_summary": "Inspect the test file and rerun unit tests.",
        "confidence": 0.82,
        "action_intents": [
            {
                "action_type": "READ_FILE",
                "target": "tests/unit/test_models.py",
                "instructions": "Read the target test before changing anything.",
            },
            {
                "action_type": "RUN_COMMAND",
                "target": "pytest tests/unit -q",
                "instructions": "Run the targeted unit suite.",
            },
        ],
    }

    decision = parse_worker_decision(payload)
    intents = translate_worker_decision(decision)

    assert decision.decision_summary == "Inspect the test file and rerun unit tests."
    assert decision.confidence == 0.82
    assert intents == [
        ActionIntent(
            action_type=ActionType.READ_FILE,
            target="tests/unit/test_models.py",
            instructions="Read the target test before changing anything.",
        ),
        ActionIntent(
            action_type=ActionType.RUN_COMMAND,
            target="pytest tests/unit -q",
            instructions="Run the targeted unit suite.",
        ),
    ]


def test_build_controller_decision_promotes_worker_decision_to_canonical_decision() -> None:
    payload = {
        "decision_summary": "Inspect the test file and rerun unit tests.",
        "confidence": 0.82,
        "action_intents": [
            {
                "action_type": "READ_FILE",
                "target": "tests/unit/test_models.py",
                "instructions": "Read the target test before changing anything.",
            }
        ],
    }

    decision = build_controller_decision(payload)

    assert decision.decision_type == DecisionType.ACT
    assert decision.proposed_action == "Inspect the test file and rerun unit tests."
    assert decision.requires_approval is False
    assert decision.action_intents[0].action_type == ActionType.READ_FILE


def test_execute_intent_keeps_reads_bounded_to_repo_root() -> None:
    observation = execute_intent(
        ActionIntent(
            action_type=ActionType.READ_FILE,
            target="../outside.txt",
            instructions="Attempt an invalid read.",
        )
    )

    assert observation.success is False
    assert observation.kind == "read_file_blocked"


def test_worker_client_contract_error_is_clear() -> None:
    client = AriWorkerClient()

    with pytest.raises(ValueError, match="typed action_intents contract") as exc_info:
        client._parse_decision_payload(
            {
                "decision_summary": "Legacy format",
                "action": "Run pytest -q",
                "confidence": 0.86,
            }
        )

    assert "action_intents" in str(exc_info.value)


def test_execute_intent_blocks_edit_file_until_safe_implementation_exists() -> None:
    observation = execute_intent(
        ActionIntent(
            action_type=ActionType.EDIT_FILE,
            target="tests/unit/test_models.py",
            instructions="Apply a small patch.",
        )
    )

    assert observation.success is False
    assert observation.kind == "edit_file_blocked"
    assert "not implemented safely yet" in observation.summary


def test_authority_engine_allows_bounded_high_confidence_act_decision() -> None:
    result = evaluate_decision_authority(_controller_decision())

    assert result.outcome == AuthorityOutcome.ALLOW
    assert result.may_execute is True


def test_authority_engine_requires_approval_for_explicit_approval_flag() -> None:
    result = evaluate_decision_authority(_controller_decision(requires_approval=True))

    assert result.outcome == AuthorityOutcome.REQUIRE_APPROVAL
    assert result.may_execute is False


def test_authority_engine_requires_approval_for_ask_user_action() -> None:
    result = evaluate_decision_authority(
        _controller_decision(
            actions=[
                ProposedAction(
                    action_type=ActionType.ASK_USER,
                    target="operator",
                    instructions="Ask whether to proceed.",
                )
            ]
        )
    )

    assert result.outcome == AuthorityOutcome.REQUIRE_APPROVAL
    assert result.may_execute is False


def test_authority_engine_denies_non_allowlisted_command() -> None:
    result = evaluate_decision_authority(
        _controller_decision(
            actions=[
                ProposedAction(
                    action_type=ActionType.RUN_COMMAND,
                    target="pytest -k auth -q",
                    instructions="Run an unapproved command.",
                )
            ]
        )
    )

    assert result.outcome == AuthorityOutcome.DENY
    assert result.may_execute is False


def test_authority_engine_defers_low_confidence_decision() -> None:
    result = evaluate_decision_authority(_controller_decision(confidence=0.4))

    assert result.outcome == AuthorityOutcome.DEFER
    assert result.may_execute is False


def test_controller_cycle_executes_only_allowed_decisions() -> None:
    executed_targets: list[str] = []

    def fake_executor(intent: ActionIntent) -> ExecutionObservation:
        executed_targets.append(intent.target)
        return ExecutionObservation(
            success=True,
            kind="read_file",
            target=intent.target,
            summary="Read file successfully.",
            details="...",
        )

    trajectory = run_controller_cycle(
        _controller_decision(),
        executed_at=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
        intent_executor=fake_executor,
    )

    assert executed_targets == ["tests/unit/test_models.py"]
    assert trajectory.action_plan is not None
    assert trajectory.worker_run is not None
    assert trajectory.verification_result is not None
    assert trajectory.controller_outcome == ControlOutcome.SUCCESS


@pytest.mark.parametrize(
    ("decision", "expected_outcome"),
    [
        (_controller_decision(requires_approval=True), ControlOutcome.REQUIRE_APPROVAL),
        (
            _controller_decision(
                actions=[
                    ProposedAction(
                        action_type=ActionType.RUN_COMMAND,
                        target="pytest -k auth -q",
                        instructions="Run an unapproved command.",
                    )
                ]
            ),
            ControlOutcome.DENIED,
        ),
        (_controller_decision(confidence=0.4), ControlOutcome.DEFERRED),
    ],
)
def test_controller_cycle_does_not_execute_non_allowed_decisions(
    decision: ControllerDecision,
    expected_outcome: ControlOutcome,
) -> None:
    calls: list[str] = []

    def fake_executor(intent: ActionIntent) -> ExecutionObservation:
        calls.append(intent.target)
        return ExecutionObservation(
            success=True,
            kind="read_file",
            target=intent.target,
            summary="Read file successfully.",
            details="...",
        )

    trajectory = run_controller_cycle(
        decision,
        executed_at=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
        intent_executor=fake_executor,
    )

    assert calls == []
    assert trajectory.action_plan is None
    assert trajectory.worker_run is None
    assert trajectory.verification_result is None
    assert trajectory.controller_outcome == expected_outcome


def test_evaluate_observations_requires_every_returned_intent_to_succeed() -> None:
    intents = [
        ActionIntent(
            action_type=ActionType.READ_FILE,
            target="tests/unit/test_models.py",
            instructions="Read the test file.",
        ),
        ActionIntent(
            action_type=ActionType.RUN_COMMAND,
            target="pytest tests/unit -q",
            instructions="Run the test suite.",
        ),
    ]
    observations = [
        ExecutionObservation(
            success=True,
            kind="read_file",
            target="tests/unit/test_models.py",
            summary="Read file successfully.",
            details="...",
        ),
        ExecutionObservation(
            success=False,
            kind="run_command",
            target="pytest tests/unit -q",
            summary="Command failed.",
            details="returncode=1",
        ),
    ]

    assert evaluate_observations(intents, observations) == "RETRY"


def test_evaluate_observations_returns_success_only_when_all_intents_succeed() -> None:
    intents = [
        ActionIntent(
            action_type=ActionType.READ_FILE,
            target="tests/unit/test_models.py",
            instructions="Read the test file.",
        )
    ]
    observations = [
        ExecutionObservation(
            success=True,
            kind="read_file",
            target="tests/unit/test_models.py",
            summary="Read file successfully.",
            details="...",
        )
    ]

    assert evaluate_observations(intents, observations) == "SUCCESS"
