from __future__ import annotations

from ari_core.decision.models import Decision, ProposedAction


def test_decision_model_exposes_typed_action_and_reasoning() -> None:
    decision = Decision(
        intent="inspect_workspace_surface",
        decision_type="act",
        priority=95,
        reasoning="A critical workspace signal should trigger a bounded inspect action.",
        confidence=0.88,
        related_signal_ids=("signal-1",),
        related_entity_type="workspace",
        related_entity_id="2026-04-22",
        proposed_action=ProposedAction(
            "run_command",
            {
                "command": ["ls"],
                "signal_id": "signal-1",
            },
        ),
        requires_approval=False,
    )

    payload = decision.to_dict()

    assert decision.action == {"type": "run_command", "command": ["ls"], "signal_id": "signal-1"}
    assert payload["decision_type"] == "act"
    assert payload["proposed_action"]["type"] == "run_command"
    assert payload["requires_approval"] is False
