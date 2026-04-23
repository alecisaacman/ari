from __future__ import annotations

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
