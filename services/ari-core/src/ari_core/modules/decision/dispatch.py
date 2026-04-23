from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .engine import Decision


DispatchStatus = Literal["executed", "requires_approval", "rejected"]


@dataclass(frozen=True, slots=True)
class DispatchResult:
    decision_reference: str
    status: DispatchStatus
    reason: str
    action: dict[str, Any]
    execution_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dispatch_decision(
    decision: Decision,
    *,
    execution_root: Path | str | None = None,
) -> DispatchResult:
    status, reason = _authorize_action(decision.action)
    if status != "executed":
        return DispatchResult(
            decision_reference=_decision_reference(decision),
            status=status,
            reason=reason,
            action=decision.action,
        )

    from ... import ari

    execution_result = ari.execute(decision.action, execution_root=execution_root)
    return DispatchResult(
        decision_reference=_decision_reference(decision),
        status="executed",
        reason=reason,
        action=decision.action,
        execution_result=execution_result,
    )


def _authorize_action(action: dict[str, Any]) -> tuple[DispatchStatus, str]:
    action_type = str(action.get("type", "")).strip()

    if action_type == "read_file":
        return "executed", "read_file is safe for automatic execution."

    if action_type == "run_command":
        command = action.get("command")
        if not isinstance(command, list) or not command:
            return "rejected", "run_command requires a non-empty command list."
        head = str(command[0]).strip()
        if head in {"ls", "cat"}:
            return "executed", f"{head} is allowlisted for automatic execution."
        if head in {"pytest"}:
            return "requires_approval", f"{head} requires explicit approval before execution."
        return "rejected", f"{head} is not eligible for automatic dispatch."

    if action_type in {"write_file", "patch_file"}:
        return "requires_approval", f"{action_type} requires explicit approval before execution."

    return "rejected", f"Action type {action_type or '<missing>'} is not dispatchable yet."


def _decision_reference(decision: Decision) -> str:
    action_type = str(decision.action.get("type", "unknown"))
    target = str(
        decision.action.get("path")
        or decision.action.get("target")
        or decision.action.get("signal_id")
        or "none"
    )
    return f"{decision.intent}:{action_type}:{target}"
