"""Proposals ARI makes on Alec's behalf, and his approvals of them.

The brain proposes one change at a time with `propose_action`. Each proposal is a
canonical execution task that waits at the gateway's approval gate, so nothing
runs until Alec approves it. Approval is decided here from Alec's own reply, never
by the model, and the approved action is dispatched once through the gateway.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .core import paths as core_paths
from .modules.execution.contracts import ResumeDecision, TaskLifecycleState
from .modules.execution.runtime_adapter import (
    CanonicalStepResult,
    PreparedRuntimeStep,
    RuntimeExecutionAdapter,
    RuntimeStepRequest,
)

ACTION_DESK_IDENTITY = "ari-action-desk"
PROPOSABLE_ACTIONS = {"write_file", "patch_file", "run_command"}
COMMAND_TIMEOUT_SECONDS = 300

Clock = Callable[[], datetime]
PauseStateReader = Callable[[], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PendingProposal:
    task_id: str
    summary: str
    created_at: str


class ActionDesk:
    """Turn the brain's proposals into approval-gated canonical tasks."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        execution_root: Path | str | None = None,
        clock: Clock | None = None,
        pause_state_reader: PauseStateReader | None = None,
    ) -> None:
        # Raises ValueError when ARI has no permitted workspace; callers then offer
        # no proposals at all.
        self.adapter = RuntimeExecutionAdapter(
            db_path or core_paths.DB_PATH,
            execution_root=execution_root,
            clock=clock,
            pause_state_reader=pause_state_reader,
        )

    def propose(self, tool_input: dict[str, Any], *, surface: str) -> dict[str, Any]:
        """Persist one proposal at the approval gate; return what the brain may tell Alec."""
        summary = str(tool_input.get("summary") or "").strip()
        if not summary:
            return {"error": "A proposal needs a one-sentence summary for Alec."}
        try:
            action = _action_from_input(tool_input)
        except ValueError as error:
            return {"error": str(error)}

        prepared = self.adapter.prepare_step(
            RuntimeStepRequest(
                action=action,
                objective=summary,
                reason=summary,
                worker_identity=ACTION_DESK_IDENTITY,
                approval_required=True,
                worker_capabilities=(str(action["type"]),),
                provenance={"source": "action_desk", "surface": surface},
            )
        )
        gated = self.adapter.dispatch_step(prepared)
        if gated.decision is not ResumeDecision.REQUIRE_APPROVAL:
            # The gateway refused it outright (outside the workspace, not a command
            # capability, paused); there is nothing for Alec to approve.
            return {"error": f"ARI can't run that: {gated.reason}"}
        return {
            "proposal_id": prepared.task_id,
            "summary": summary,
            "status": "awaiting Alec's approval",
        }

    def pending(self) -> list[PendingProposal]:
        """Proposals still waiting for Alec, oldest first."""
        rows = self.adapter.ledger._many(
            """
            select t.task_id, t.objective, t.created_at
            from ari_execution_tasks t
            join ari_execution_attempts a on a.attempt_id = t.active_attempt_id
            where t.lifecycle_state = ? and a.worker_identity = ?
            order by t.created_at, t.task_id
            """,
            (TaskLifecycleState.AWAITING_APPROVAL.value, ACTION_DESK_IDENTITY),
        )
        return [
            PendingProposal(
                task_id=str(row["task_id"]),
                summary=str(row["objective"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def approve(self, task_id: str, *, approved_by: str, reason: str) -> CanonicalStepResult:
        """Bind Alec's approval to the proposal's exact action and dispatch it once."""
        attempt_id = self._active_attempt(task_id)
        self.adapter.gateway.approve_next_action(
            task_id=task_id,
            attempt_id=attempt_id,
            approved_by=approved_by,
            reason=reason,
        )
        prepared = self._prepared(task_id)
        if self.adapter.sessions.classify_attempt(prepared.attempt_id).recoverable:
            # The lease expired while the proposal waited. The approval is bound to
            # the action, not the attempt, so it carries over to the replacement.
            prepared = self._recover(prepared)
        return self.adapter.dispatch_step(prepared)

    def decline(self, task_id: str, *, reason: str) -> None:
        self.adapter.sessions.set_task_lifecycle(
            task_id, TaskLifecycleState.CANCELLED, reason=reason
        )

    def _recover(self, prepared: PreparedRuntimeStep) -> PreparedRuntimeStep:
        recovery = self.adapter.sessions.reconcile_stale_attempt(
            prepared.attempt_id,
            replacement_worker_identity=ACTION_DESK_IDENTITY,
            lease_seconds=self.adapter.lease_seconds,
        )
        if recovery.replacement_attempt_id is None or recovery.continuation_packet_id is None:
            raise ValueError(f"The proposal could not be recovered: {recovery.reason}")
        self.adapter._acknowledge(recovery.continuation_packet_id, ACTION_DESK_IDENTITY)
        return self._prepared(prepared.task_id)

    def _active_attempt(self, task_id: str) -> str:
        task = self.adapter.ledger.get_task(task_id)
        if task is None:
            raise ValueError(f"No proposal {task_id}.")
        return str(task["active_attempt_id"])

    def _prepared(self, task_id: str) -> PreparedRuntimeStep:
        task = self.adapter.ledger.get_task(task_id)
        if task is None or task["latest_checkpoint_id"] is None:
            raise ValueError(f"No proposal {task_id}.")
        attempt = self.adapter.ledger._one(
            "select session_id from ari_execution_attempts where attempt_id = ?",
            (str(task["active_attempt_id"]),),
        )
        checkpoint = self.adapter.ledger.get_checkpoint(str(task["latest_checkpoint_id"]))
        assert attempt is not None and checkpoint is not None
        planned = checkpoint["current_plan"]["actions"][0]
        return PreparedRuntimeStep(
            task_id=task_id,
            action_id=str(planned["id"]),
            action_type=str(planned["action_type"]),
            attempt_id=str(task["active_attempt_id"]),
            session_id=str(attempt["session_id"]),
            worker_identity=ACTION_DESK_IDENTITY,
            objective=str(task["objective"]),
            loop_id=None,
        )


def describe_result(step: CanonicalStepResult) -> str:
    """One plain sentence Alec reads about what actually happened."""
    if not step.executed:
        return f"I didn't run it: {step.reason}"
    if step.effect_uncertain:
        return "It started but I can't confirm what it changed. I won't retry it on my own."
    result = step.result or {}
    if step.action_type == "run_command":
        exit_code = result.get("exit_code")
        output = str(result.get("stdout") or result.get("stderr") or "").strip()
        tail = output.splitlines()[-1] if output else ""
        status = "passed" if result.get("success") else f"exited with code {exit_code}"
        return f"Done. The command {status}." + (f" Last line: {tail}" if tail else "")
    if step.succeeded:
        return f"Done. I updated {result.get('path') or 'the file'} and verified it."
    return "It ran, but I couldn't verify the change, so I'm treating it as unresolved."


def _action_from_input(tool_input: dict[str, Any]) -> dict[str, Any]:
    action_type = str(tool_input.get("action_type") or "")
    if action_type not in PROPOSABLE_ACTIONS:
        raise ValueError(f"ARI can only propose {', '.join(sorted(PROPOSABLE_ACTIONS))}.")
    if action_type == "write_file":
        return {
            "type": action_type,
            "path": _required(tool_input, "path"),
            "content": str(tool_input.get("content") or ""),
        }
    if action_type == "patch_file":
        return {
            "type": action_type,
            "path": _required(tool_input, "path"),
            "find": _required(tool_input, "find"),
            "replace": str(tool_input.get("replace") or ""),
        }
    command = tool_input.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
        raise ValueError("run_command needs command as a list of strings.")
    return {"type": action_type, "command": list(command), "timeout_seconds": COMMAND_TIMEOUT_SECONDS}


def _required(tool_input: dict[str, Any], key: str) -> str:
    value = str(tool_input.get(key) or "")
    if not value:
        raise ValueError(f"{tool_input.get('action_type')} needs {key}.")
    return value
