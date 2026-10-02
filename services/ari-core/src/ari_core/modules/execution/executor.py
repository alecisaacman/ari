from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .sandbox import ExecutionRoot


def execute_action(
    action: dict[str, Any],
    execution_root: Path | str | None = None,
) -> dict[str, Any]:
    sandbox = ExecutionRoot(execution_root)
    action_type = str(action.get("type") or action.get("kind") or "").strip()

    if action_type == "read_file":
        content = sandbox.read_file(str(action["path"]))
        return {
            "success": True,
            "content": content,
            "path": str(action["path"]),
        }

    if action_type == "write_file":
        resolved = sandbox.write_file(str(action["path"]), str(action["content"]))
        return {
            "success": True,
            "path": str(resolved.relative_to(sandbox.root)),
        }

    if action_type == "patch_file":
        resolved = sandbox.patch_file(
            str(action["path"]),
            str(action["find"]),
            str(action["replace"]),
        )
        return {
            "success": True,
            "path": str(resolved.relative_to(sandbox.root)),
        }

    if action_type == "run_command":
        result = sandbox.run_command(
            list(action["command"]),
            int(action.get("timeout_seconds", 30)),
        )
        return result.to_dict()

    raise ValueError(f"unsupported execution action: {action_type}")


def verify_action_result(
    action: dict[str, Any],
    result: dict[str, Any],
    execution_root: Path | str | None = None,
) -> dict[str, Any]:
    """Verify one normalized action independently from any worker or provider."""
    sandbox = ExecutionRoot(execution_root)
    action_type = str(action.get("type") or action.get("kind") or "").strip()
    verified = bool(result.get("success"))
    evidence: dict[str, Any] = {"action_type": action_type}

    try:
        if verified and action_type == "write_file":
            resolved = sandbox.resolve_path(str(action["path"]))
            expected = str(action["content"])
            actual = resolved.read_text(encoding="utf-8")
            verified = actual == expected
            evidence.update(_file_evidence(resolved, sandbox, expected=expected))
        elif verified and action_type == "patch_file":
            resolved = sandbox.resolve_path(str(action["path"]))
            replacement = str(action["replace"])
            actual = resolved.read_text(encoding="utf-8")
            verified = replacement in actual
            evidence.update(_file_evidence(resolved, sandbox, expected=replacement))
        elif action_type == "read_file":
            evidence["path"] = str(action.get("path") or "")
        elif action_type == "run_command":
            evidence.update(
                {
                    "command": list(action.get("command") or []),
                    "exit_code": result.get("exit_code"),
                }
            )
    except (OSError, ValueError, KeyError) as error:
        verified = False
        evidence["verification_error"] = str(error)

    return {"verified": verified, "evidence": evidence}


def _file_evidence(
    resolved: Path,
    sandbox: ExecutionRoot,
    *,
    expected: str,
) -> dict[str, Any]:
    content = resolved.read_bytes()
    return {
        "path": str(resolved.relative_to(sandbox.root)),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "expected_fragment_sha256": hashlib.sha256(expected.encode("utf-8")).hexdigest(),
    }
