from __future__ import annotations

from pathlib import Path

from ari_core.modules.decision.dispatch import dispatch_decision
from ari_core.modules.decision.engine import Decision, ProposedAction


def test_dispatch_decision_auto_executes_safe_read_action(tmp_path: Path) -> None:
    execution_root = tmp_path / "execution-root"
    execution_root.mkdir(parents=True, exist_ok=True)
    (execution_root / "sample.txt").write_text("hello from ari\n", encoding="utf-8")

    decision = Decision(
        intent="inspect_workspace_file",
        decision_type="act",
        priority=80,
        reasoning="The file can be read safely.",
        confidence=0.9,
        related_signal_ids=("signal-1",),
        proposed_action=ProposedAction("read_file", {"path": "sample.txt", "signal_id": "signal-1"}),
    )

    result = dispatch_decision(decision, execution_root=execution_root)

    assert result.status == "executed"
    assert result.execution_result is not None
    assert result.execution_result["success"] is True
    assert result.execution_result["content"] == "hello from ari\n"


def test_dispatch_decision_requires_approval_for_patch_action() -> None:
    decision = Decision(
        intent="modify_workspace_file",
        decision_type="act",
        priority=85,
        reasoning="Patching a file is more consequential than the auto-exec subset.",
        confidence=0.88,
        related_signal_ids=("signal-2",),
        proposed_action=ProposedAction(
            "patch_file",
            {
                "path": "sample.txt",
                "find": "old",
                "replace": "new",
                "signal_id": "signal-2",
            },
        ),
        requires_approval=True,
    )

    result = dispatch_decision(decision)

    assert result.status == "requires_approval"
    assert "requires explicit approval" in result.reason
    assert result.execution_result is None
