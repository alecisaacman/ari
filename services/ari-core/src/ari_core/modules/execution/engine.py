from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Literal

from ...core.paths import DB_PATH, EXECUTION_ROOT
from .db import (
    create_coding_action,
    create_command_run,
    create_file_mutation,
    get_coding_action,
    get_command_run,
    list_coding_actions,
    list_command_runs,
    list_file_mutations,
    new_id,
    now_iso,
    row_to_coding_action_payload,
    row_to_command_run_payload,
    row_to_file_mutation_payload,
    sync_action_execution_outcome,
    update_coding_action,
)

ALLOWED_WRITE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".txt",
    ".css",
    ".sql",
    ".yml",
    ".yaml",
}

RETRYABLE_PATTERNS = (
    "timed out",
    "timeout",
    "temporar",
    "eaddrinuse",
    "connection reset",
    "network",
)
DISALLOWED_COMMAND_TOKENS = ("&&", "||", "|", ";", ">", "<", "$(", "`", "\n")


def _execution_root() -> Path:
    return EXECUTION_ROOT.expanduser().resolve()


def _timestamp() -> str:
    return now_iso()


def _is_within_root(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def resolve_execution_path(
    raw_path: str,
    *,
    must_exist: bool = False,
    allow_directory: bool = False,
) -> Path:
    if not raw_path.strip():
        raise ValueError("path is required")

    root = _execution_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()

    if not _is_within_root(resolved, root):
        raise ValueError(f"Path escapes the execution root: {raw_path}")

    if ".git" in resolved.parts:
        raise ValueError("Paths inside .git are not allowed.")

    if must_exist and not resolved.exists():
        raise ValueError(f"Path does not exist: {raw_path}")

    if must_exist and resolved.is_dir() and not allow_directory:
        raise ValueError(f"Expected a file path, not a directory: {raw_path}")

    return resolved


def _sha256_for_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_relpath(path: Path) -> str:
    return path.relative_to(_execution_root()).as_posix()


def _record_mutation(
    *,
    action_id: str | None,
    path: Path,
    operation: Literal["write", "patch"],
    success: bool,
    details: str,
    previous_content: str | None,
    new_content: str | None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    row = create_file_mutation(
        {
            "id": new_id("mutation"),
            "action_id": action_id,
            "path": _safe_relpath(path),
            "operation": operation,
            "success": success,
            "details": details,
            "previous_sha256": (
                _sha256_for_content(previous_content)
                if previous_content is not None
                else None
            ),
            "new_sha256": _sha256_for_content(new_content) if new_content is not None else None,
            "created_at": _timestamp(),
        },
        db_path=db_path,
    )
    return row_to_file_mutation_payload(row)


def _validate_mutation_path(path: Path) -> None:
    if path.suffix not in ALLOWED_WRITE_SUFFIXES:
        raise ValueError(f"Mutating {path.suffix or 'extensionless'} files is not allowed yet.")


def read_file(path: str) -> dict[str, Any]:
    resolved = resolve_execution_path(path, must_exist=True)
    return {
        "success": True,
        "path": _safe_relpath(resolved),
        "content": resolved.read_text(encoding="utf-8"),
    }


def write_file(
    path: str,
    content: str,
    *,
    action_id: str | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    resolved = resolve_execution_path(path)
    _validate_mutation_path(resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    previous_content = resolved.read_text(encoding="utf-8") if resolved.exists() else None
    resolved.write_text(content, encoding="utf-8")
    mutation = _record_mutation(
        action_id=action_id,
        path=resolved,
        operation="write",
        success=True,
        details="File content replaced.",
        previous_content=previous_content,
        new_content=content,
        db_path=db_path,
    )
    return {
        "success": True,
        "path": mutation["path"],
        "mutation": mutation,
    }


def patch_file(
    path: str,
    *,
    find_text: str,
    replace_text: str,
    action_id: str | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    if not find_text:
        raise ValueError("find_text is required for patch operations.")

    resolved = resolve_execution_path(path, must_exist=True)
    _validate_mutation_path(resolved)
    original = resolved.read_text(encoding="utf-8")
    if find_text not in original:
        raise ValueError("Patch target text was not found in the file.")

    updated = original.replace(find_text, replace_text, 1)
    resolved.write_text(updated, encoding="utf-8")
    mutation = _record_mutation(
        action_id=action_id,
        path=resolved,
        operation="patch",
        success=True,
        details="Applied a single search/replace patch.",
        previous_content=original,
        new_content=updated,
        db_path=db_path,
    )
    return {
        "success": True,
        "path": mutation["path"],
        "mutation": mutation,
    }


def _validate_command(command: str) -> list[str]:
    if not command.strip():
        raise ValueError("command is required")
    if any(token in command for token in DISALLOWED_COMMAND_TOKENS):
        raise ValueError("Shell control operators are not allowed.")

    argv = shlex.split(command)
    if not argv:
        raise ValueError("command is required")

    if not _command_is_allowed(argv):
        raise ValueError(f"Command is not allowed yet: {command}")

    return argv


def _command_is_allowed(argv: list[str]) -> bool:
    if argv[:2] == ["npm", "test"]:
        return True
    if argv[:3] in (["npm", "run", "build"], ["npm", "run", "lint"]):
        return True
    if len(argv) >= 2 and argv[0] == "node" and argv[1] in {"--test", "--check"}:
        return True
    if len(argv) >= 3 and argv[1:3] == ["-m", "pytest"]:
        executable = Path(argv[0]).name
        return executable.startswith("python") or executable == "python"
    return False


def classify_result(result: dict[str, Any]) -> dict[str, Any]:
    combined = f"{result['stdout']}\n{result['stderr']}".lower()
    retryable = bool(result["timed_out"]) or any(
        pattern in combined for pattern in RETRYABLE_PATTERNS
    )
    return {
        "success": bool(result["success"]),
        "failure": not bool(result["success"]),
        "retryable": retryable,
    }


def execute_command(command: str, *, cwd: str = ".", timeout_seconds: int = 60) -> dict[str, Any]:
    argv = _validate_command(command)
    resolved_cwd = resolve_execution_path(cwd, must_exist=True, allow_directory=True)
    if not resolved_cwd.is_dir():
        raise ValueError("cwd must point to a directory inside the execution root.")

    try:
        completed = subprocess.run(
            argv,
            cwd=str(resolved_cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        result = {
            "success": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
            "timed_out": False,
            "cwd": _safe_relpath(resolved_cwd),
            "command": command,
        }
    except subprocess.TimeoutExpired as error:
        result = {
            "success": False,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
            "exit_code": -1,
            "timed_out": True,
            "cwd": _safe_relpath(resolved_cwd),
            "command": command,
        }

    result["classification"] = classify_result(result)
    return result


def _normalize_operations(
    operations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    target_paths: list[str] = []

    if not operations:
        raise ValueError("At least one file operation is required.")

    for operation in operations:
        op_type = operation.get("type")
        if op_type not in {"write", "patch"}:
            raise ValueError(f"Unsupported operation type: {op_type}")

        path = resolve_execution_path(str(operation.get("path", "")))
        _validate_mutation_path(path)
        target_paths.append(_safe_relpath(path))

        if op_type == "write":
            normalized.append(
                {
                    "type": "write",
                    "path": _safe_relpath(path),
                    "content": str(operation.get("content", "")),
                }
            )
            continue

        find_text = str(operation.get("find", ""))
        if not find_text:
            raise ValueError("Patch operations require find text.")
        normalized.append(
            {
                "type": "patch",
                "path": _safe_relpath(path),
                "find": find_text,
                "replace": str(operation.get("replace", "")),
            }
        )

    return normalized, target_paths


def _is_risky_action(
    target_paths: list[str],
    operations: list[dict[str, Any]],
    verify_command: str,
) -> bool:
    if len(target_paths) > 1:
        return True
    if any(operation["type"] == "write" for operation in operations):
        return True
    return not bool(verify_command.strip())


def create_operator_action(
    *,
    title: str,
    summary: str,
    operations: list[dict[str, Any]],
    verify_command: str = "",
    working_directory: str = ".",
    approval_required: bool | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    normalized_ops, target_paths = _normalize_operations(operations)
    resolved_cwd = resolve_execution_path(working_directory, must_exist=False, allow_directory=True)
    risky = _is_risky_action(target_paths, normalized_ops, verify_command)
    requires_approval = risky if approval_required is None else approval_required
    timestamp = _timestamp()
    row = create_coding_action(
        {
            "id": new_id("code"),
            "title": title.strip() or "Untitled coding action",
            "summary": summary.strip() or title.strip() or "Untitled coding action",
            "status": "proposed",
            "approval_required": requires_approval,
            "risky": risky,
            "target_paths_json": json.dumps(target_paths),
            "operations_json": json.dumps(normalized_ops),
            "verify_command": verify_command.strip(),
            "working_directory": _safe_relpath(resolved_cwd),
            "current_step": "proposed",
            "last_command_summary": "",
            "result_summary": "Action proposed and waiting to run.",
            "retryable": False,
            "blocked_reason": None,
            "created_at": timestamp,
            "approved_at": None,
            "applied_at": None,
            "tested_at": None,
            "passed_at": None,
            "failed_at": None,
            "verified_at": None,
            "updated_at": timestamp,
        },
        db_path=db_path,
    )
    payload = row_to_coding_action_payload(row)
    sync_action_execution_outcome(
        payload["id"],
        title=payload["title"],
        state="pending",
        stage="proposed",
        state_since=payload["created_at"],
        next_action=(
            "Approve and run the coding action."
            if payload["approval_required"]
            else "Run the coding action."
        ),
        metadata={"target_paths": payload["target_paths"], "status": payload["status"]},
        db_path=db_path,
    )
    return payload


def approve_operator_action(action_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    row = get_coding_action(action_id, db_path=db_path)
    if row is None:
        raise ValueError(f"Unknown coding action: {action_id}")
    payload = row_to_coding_action_payload(row)
    if payload["status"] not in {"proposed", "failed"}:
        return payload

    timestamp = _timestamp()
    updated = update_coding_action(
        action_id,
        {
            "status": "approved",
            "current_step": "approved",
            "approved_at": timestamp,
            "result_summary": "Action approved and ready to run.",
            "blocked_reason": None,
            "updated_at": timestamp,
        },
        db_path=db_path,
    )
    payload = row_to_coding_action_payload(updated)
    sync_action_execution_outcome(
        payload["id"],
        title=payload["title"],
        state="moving",
        stage="approved",
        state_since=timestamp,
        next_action="Apply the change and run verification.",
        metadata={"target_paths": payload["target_paths"], "status": payload["status"]},
        db_path=db_path,
    )
    return payload


def _apply_action_operations(action: dict[str, Any], *, db_path: Path) -> list[dict[str, Any]]:
    mutations: list[dict[str, Any]] = []
    for operation in action["operations"]:
        if operation["type"] == "write":
            mutations.append(
                write_file(
                    operation["path"],
                    operation["content"],
                    action_id=action["id"],
                    db_path=db_path,
                )["mutation"]
            )
        elif operation["type"] == "patch":
            mutations.append(
                patch_file(
                    operation["path"],
                    find_text=operation["find"],
                    replace_text=operation["replace"],
                    action_id=action["id"],
                    db_path=db_path,
                )["mutation"]
            )
    return mutations


def run_operator_action(action_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    row = get_coding_action(action_id, db_path=db_path)
    if row is None:
        raise ValueError(f"Unknown coding action: {action_id}")

    action = row_to_coding_action_payload(row)
    if action["approval_required"] and action["status"] == "proposed":
        raise ValueError("This coding action requires approval before it can run.")

    mutations = _apply_action_operations(action, db_path=db_path)
    applied_at = _timestamp()
    current = row_to_coding_action_payload(
        update_coding_action(
            action_id,
            {
                "status": "applied",
                "current_step": "applied",
                "applied_at": applied_at,
                "result_summary": f"Applied {len(mutations)} file change(s).",
                "blocked_reason": None,
                "updated_at": applied_at,
            },
            db_path=db_path,
        )
    )

    sync_action_execution_outcome(
        current["id"],
        title=current["title"],
        state="moving",
        stage="applied",
        state_since=applied_at,
        next_action="Run the verification command.",
        metadata={"target_paths": current["target_paths"], "status": current["status"]},
        db_path=db_path,
    )

    command_run_payload: dict[str, Any] | None = None
    if current["verify_command"]:
        command_result = execute_command(
            current["verify_command"],
            cwd=current["working_directory"],
            timeout_seconds=90,
        )
        tested_at = _timestamp()
        command_row = create_command_run(
            {
                "id": new_id("run"),
                "action_id": current["id"],
                "command": command_result["command"],
                "cwd": command_result["cwd"],
                "success": command_result["success"],
                "exit_code": command_result["exit_code"],
                "timed_out": command_result["timed_out"],
                "retryable": command_result["classification"]["retryable"],
                "stdout": command_result["stdout"],
                "stderr": command_result["stderr"],
                "classification_json": json.dumps(command_result["classification"]),
                "created_at": tested_at,
            },
            db_path=db_path,
        )
        command_run_payload = row_to_command_run_payload(command_row)

        if command_result["success"]:
            verified_at = tested_at
            current = row_to_coding_action_payload(
                update_coding_action(
                    current["id"],
                    {
                        "status": "verified",
                        "current_step": "verified",
                        "last_command_run_id": command_row["id"],
                        "last_command_summary": current["verify_command"],
                        "result_summary": "Verification passed.",
                        "retryable": False,
                        "tested_at": tested_at,
                        "passed_at": tested_at,
                        "verified_at": verified_at,
                        "updated_at": verified_at,
                    },
                    db_path=db_path,
                )
            )
            sync_action_execution_outcome(
                current["id"],
                title=current["title"],
                state="completed",
                stage="verified",
                state_since=verified_at,
                next_action="No action required.",
                verification_signal="command_passed",
                metadata={
                    "target_paths": current["target_paths"],
                    "last_command_run_id": command_run_payload["id"],
                    "status": current["status"],
                },
                completed_at=verified_at,
                db_path=db_path,
            )
        else:
            failed_at = tested_at
            retryable = bool(command_result["classification"]["retryable"])
            current = row_to_coding_action_payload(
                update_coding_action(
                    current["id"],
                    {
                        "status": "failed",
                        "current_step": "failed",
                        "last_command_run_id": command_row["id"],
                        "last_command_summary": current["verify_command"],
                        "result_summary": "Verification failed.",
                        "retryable": retryable,
                        "blocked_reason": "Verification command failed.",
                        "tested_at": tested_at,
                        "failed_at": failed_at,
                        "updated_at": failed_at,
                    },
                    db_path=db_path,
                )
            )
            sync_action_execution_outcome(
                current["id"],
                title=current["title"],
                state="failed",
                stage="failed_verification",
                state_since=failed_at,
                next_action="Retry the coding action or escalate with the failure output.",
                blocked_reason="Verification command failed.",
                failure_reason=command_result["stderr"][-4000:] or "Verification command failed.",
                metadata={
                    "target_paths": current["target_paths"],
                    "last_command_run_id": command_run_payload["id"],
                    "status": current["status"],
                },
                db_path=db_path,
            )
    else:
        verified_at = applied_at
        current = row_to_coding_action_payload(
            update_coding_action(
                current["id"],
                {
                    "status": "applied",
                    "current_step": "applied",
                    "updated_at": verified_at,
                },
                db_path=db_path,
            )
        )

    return {
        "action": current,
        "mutations": mutations,
        "command_run": command_run_payload,
    }


def get_execution_snapshot(limit: int = 6, db_path: Path = DB_PATH) -> dict[str, Any]:
    actions = [
        row_to_coding_action_payload(row)
        for row in list_coding_actions(limit=limit, db_path=db_path)
    ]
    command_runs = [
        row_to_command_run_payload(row)
        for row in list_command_runs(limit=1, db_path=db_path)
    ]
    mutations = [
        row_to_file_mutation_payload(row)
        for row in list_file_mutations(limit=1, db_path=db_path)
    ]
    current_action = next(
        (item for item in actions if item["status"] != "verified"),
        actions[0] if actions else None,
    )
    return {
        "current_action": current_action,
        "recent_actions": actions,
        "last_command_run": command_runs[0] if command_runs else None,
        "last_file_mutation": mutations[0] if mutations else None,
    }


def get_operator_action(action_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    row = get_coding_action(action_id, db_path=db_path)
    if row is None:
        return None
    return row_to_coding_action_payload(row)


def get_operator_command_run(command_run_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    row = get_command_run(command_run_id, db_path=db_path)
    if row is None:
        return None
    return row_to_command_run_payload(row)
