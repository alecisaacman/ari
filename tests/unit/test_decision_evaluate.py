from __future__ import annotations

from ari_core.modules.decision.dispatch import DispatchResult
from ari_core.modules.decision.evaluate import EvaluationResult, evaluate_dispatch_result


def test_evaluate_dispatch_result_marks_successful_execution_completed() -> None:
    dispatch = DispatchResult(
        decision_reference="inspect:read_file:sample.txt",
        status="executed",
        reason="read_file is safe for automatic execution.",
        action={"type": "read_file", "path": "sample.txt"},
        execution_result={"success": True, "stdout": "hello\n", "stderr": "", "exit_code": 0},
    )

    evaluation = evaluate_dispatch_result(dispatch)

    assert isinstance(evaluation, EvaluationResult)
    assert evaluation.status == "completed"
    assert evaluation.next_step == "stop"


def test_evaluate_dispatch_result_marks_requires_approval_blocked() -> None:
    dispatch = DispatchResult(
        decision_reference="modify:patch_file:sample.txt",
        status="requires_approval",
        reason="patch_file requires explicit approval before execution.",
        action={"type": "patch_file", "path": "sample.txt"},
        execution_result=None,
    )

    evaluation = evaluate_dispatch_result(dispatch)

    assert evaluation.status == "blocked"
    assert evaluation.next_step == "request_approval"


def test_evaluate_dispatch_result_marks_retryable_failures() -> None:
    dispatch = DispatchResult(
        decision_reference="check:run_command:workspace",
        status="executed",
        reason="cat is allowlisted for automatic execution.",
        action={"type": "run_command", "command": ["cat", "missing.txt"]},
        execution_result={
            "success": False,
            "stdout": "",
            "stderr": "temporary network timeout while reading file metadata",
            "exit_code": 1,
        },
    )

    evaluation = evaluate_dispatch_result(dispatch)

    assert evaluation.status == "escalated"
    assert evaluation.next_step == "retry_allowed"
