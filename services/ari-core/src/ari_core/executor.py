from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ari_core.execution_types import ActionIntent, ActionType, ExecutionObservation

REPO_ROOT = Path(__file__).resolve().parents[4]

ALLOWED_COMMANDS = {
    "pytest -q",
    "pytest tests/unit -q",
}


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
    target_path = _resolve_repo_path(intent.target)

    if target_path is None:
        return ExecutionObservation(
            success=False,
            kind="read_file_blocked",
            target=intent.target,
            summary="Read blocked: target escaped repo root.",
            details=intent.target,
        )

    if not target_path.exists() or not target_path.is_file():
        return ExecutionObservation(
            success=False,
            kind="read_file_missing",
            target=intent.target,
            summary="Read failed: file does not exist.",
            details=str(target_path),
        )

    content = target_path.read_text(encoding="utf-8")

    return ExecutionObservation(
        success=True,
        kind="read_file",
        target=intent.target,
        summary=f"Read file successfully: {intent.target}",
        details=content[:4000],
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

    completed = subprocess.run(
        shlex.split(command),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    details = "\n".join(
        [
            f"returncode={completed.returncode}",
            "--- STDOUT ---",
            completed.stdout,
            "--- STDERR ---",
            completed.stderr,
        ]
    )

    return ExecutionObservation(
        success=completed.returncode == 0,
        kind="run_command",
        target=command,
        summary=(
            "Command completed successfully."
            if completed.returncode == 0
            else "Command failed."
        ),
        details=details[:6000],
    )


def _resolve_repo_path(target: str) -> Path | None:
    resolved_target = (REPO_ROOT / target).resolve()
    try:
        resolved_target.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return resolved_target
