from __future__ import annotations

import shlex
from pathlib import Path

from ari_core.core import paths as core_paths
from ari_core.execution_types import ActionIntent, ActionType, ExecutionObservation
from ari_core.modules.execution.runtime_adapter import (
    CanonicalStepResult,
    RuntimeExecutionAdapter,
    RuntimeStepRequest,
)

REPO_ROOT = Path(__file__).resolve().parents[4]

# Controller policy: the only commands the legacy controller may ask for. Each still
# has to resolve to an explicit command capability at the canonical boundary.
ALLOWED_COMMANDS = {
    "pytest -q",
    "pytest tests/unit -q",
}
LEGACY_CONTROLLER_IDENTITY = "ari-legacy-controller"
LEGACY_COMMAND_TIMEOUT_SECONDS = 600


def execute_intent(intent: ActionIntent) -> ExecutionObservation:
    if intent.action_type == ActionType.READ_FILE:
        return _read_file(intent)

    if intent.action_type == ActionType.RUN_COMMAND:
        return _run_command(intent)

    if intent.action_type == ActionType.ASK_USER:
        return ExecutionObservation(
            success=False,
            kind="ask_user",
            target=intent.target,
            summary="Execution paused for user input.",
            details=intent.instructions,
        )

    if intent.action_type == ActionType.EDIT_FILE:
        return ExecutionObservation(
            success=False,
            kind="edit_file_blocked",
            target=intent.target,
            summary="Edit blocked: typed edit execution is not implemented safely yet.",
            details=intent.instructions,
        )

    return ExecutionObservation(
        success=False,
        kind="unknown_action",
        target=intent.target,
        summary="Unknown action type.",
        details=str(intent),
    )


def _read_file(intent: ActionIntent) -> ExecutionObservation:
    execution = _canonical_execution()
    if isinstance(execution, ExecutionObservation):
        return _refused(execution, intent.target)

    try:
        target_path = execution.execution_root.resolve_path(intent.target)
    except ValueError as error:
        return ExecutionObservation(
            success=False,
            kind="read_file_blocked",
            target=intent.target,
            summary="Read blocked: target escaped the execution root.",
            details=str(error),
        )

    if not target_path.exists() or not target_path.is_file():
        return ExecutionObservation(
            success=False,
            kind="read_file_missing",
            target=intent.target,
            summary="Read failed: file does not exist.",
            details=str(target_path),
        )

    step = _run_step(execution, {"type": "read_file", "path": intent.target}, intent)
    if not step.succeeded or step.result is None:
        return _not_completed(step, kind="read_file_blocked", target=intent.target)

    return ExecutionObservation(
        success=True,
        kind="read_file",
        target=intent.target,
        summary=f"Read file successfully: {intent.target}",
        details=str(step.result.get("content") or "")[:4000],
    )


def _run_command(intent: ActionIntent) -> ExecutionObservation:
    command = intent.target.strip()

    if command not in ALLOWED_COMMANDS:
        return ExecutionObservation(
            success=False,
            kind="run_command_blocked",
            target=command,
            summary="Command blocked: not allowlisted.",
            details=command,
        )

    execution = _canonical_execution()
    if isinstance(execution, ExecutionObservation):
        return _refused(execution, command)

    step = _run_step(
        execution,
        {
            "type": "run_command",
            "command": shlex.split(command),
            "timeout_seconds": LEGACY_COMMAND_TIMEOUT_SECONDS,
        },
        intent,
    )
    if not step.executed or step.result is None:
        return _not_completed(step, kind="run_command_blocked", target=command)

    result = step.result
    returncode = result.get("exit_code")
    details = "\n".join(
        [
            f"returncode={returncode}",
            "--- STDOUT ---",
            str(result.get("stdout") or ""),
            "--- STDERR ---",
            str(result.get("stderr") or ""),
        ]
    )

    return ExecutionObservation(
        success=bool(result.get("success")),
        kind="run_command",
        target=command,
        summary=(
            "Command completed successfully."
            if result.get("success")
            else "Command failed."
        ),
        details=details[:6000],
    )


def _canonical_execution() -> RuntimeExecutionAdapter | ExecutionObservation:
    """The canonical adapter, or a refusal when ARI has no permitted execution root."""
    try:
        return RuntimeExecutionAdapter(core_paths.DB_PATH)
    except ValueError as error:
        return ExecutionObservation(
            success=False,
            kind="execution_root_refused",
            target="",
            summary="Execution blocked: ARI has no permitted execution root.",
            details=str(error),
        )


def _run_step(
    execution: RuntimeExecutionAdapter,
    action: dict[str, object],
    intent: ActionIntent,
) -> CanonicalStepResult:
    return execution.run_step(
        RuntimeStepRequest(
            action=action,
            objective=intent.instructions or f"Legacy controller {intent.action_type} intent.",
            reason=f"Legacy controller intent: {intent.action_type} {intent.target}",
            worker_identity=LEGACY_CONTROLLER_IDENTITY,
            worker_capabilities=(str(action["type"]),),
        )
    )


def _refused(refusal: ExecutionObservation, target: str) -> ExecutionObservation:
    return ExecutionObservation(
        success=False,
        kind=refusal.kind,
        target=target,
        summary=refusal.summary,
        details=refusal.details,
    )


def _not_completed(step: CanonicalStepResult, *, kind: str, target: str) -> ExecutionObservation:
    return ExecutionObservation(
        success=False,
        kind=kind,
        target=target,
        summary=f"ARI did not complete the action ({step.decision}, {step.idempotency_state}).",
        details=step.reason,
    )
