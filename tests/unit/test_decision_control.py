from __future__ import annotations

from ari_core.modules.decision.evaluate import EvaluationResult, LoopControlResult, summarize_evaluation_results


def test_summarize_evaluation_results_waits_for_approval_when_blocked() -> None:
    summary = summarize_evaluation_results(
        [
            EvaluationResult(
                decision_reference="decision-1",
                status="blocked",
                reason="patch_file requires explicit approval before execution.",
                next_step="request_approval",
            )
        ]
    )

    assert isinstance(summary, LoopControlResult)
    assert summary.status == "wait_for_approval"


def test_summarize_evaluation_results_escalates_when_any_result_escalates() -> None:
    summary = summarize_evaluation_results(
        [
            EvaluationResult(
                decision_reference="decision-1",
                status="completed",
                reason="completed",
                next_step="stop",
            ),
            EvaluationResult(
                decision_reference="decision-2",
                status="escalated",
                reason="manual inspection is required",
                next_step="inspect_failure",
            ),
        ]
    )

    assert summary.status == "escalate"
    assert "manual inspection" in summary.reason
