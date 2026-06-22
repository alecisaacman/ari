from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .sandbox import ExecutionRoot


@dataclass(frozen=True, slots=True)
class ExecutionTool:
    name: str
    action_type: str
    description: str
    mutates_files: bool
    required_payload_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ExecutionToolRegistry:
    def __init__(self, tools: tuple[ExecutionTool, ...]) -> None:
        self._tools = tools
        self._tools_by_action = {tool.action_type: tool for tool in tools}

    def list_tools(self) -> list[dict[str, object]]:
        return [tool.to_dict() for tool in self._tools]

    def allowed_action_types(self) -> set[str]:
        return set(self._tools_by_action)

    def prompt_payload(self) -> dict[str, object]:
        return {
            "tools": self.list_tools(),
            "allowed_actions": sorted(self.allowed_action_types()),
            "allowed_commands": sorted(ExecutionRoot.ALLOWED_COMMANDS),
        }

    def validate_execution_action(
        self,
        action: dict[str, Any],
        *,
        execution_root: ExecutionRoot,
        allowed_files: set[str] | None = None,
    ) -> str | None:
        action_type = str(action.get("type") or action.get("action_type") or "")
        tool = self._tools_by_action.get(action_type)
        if tool is None:
            return f"Planner action type is not allowed: {action_type or '<missing>'}"

        for key in tool.required_payload_keys:
            if key not in action:
                return f"{action_type} actions require {key}."

        if action_type in {"read_file", "write_file", "patch_file"}:
            path = str(action.get("path") or "")
            if not path:
                return f"{action_type} actions require path."
            if allowed_files is not None and path not in allowed_files:
                return f"Planner referenced a file outside RepoContext: {path}"
            try:
                execution_root.resolve_path(path)
            except ValueError as error:
                return str(error)

        if action_type == "patch_file" and not str(action.get("find") or ""):
            return "patch_file actions require find text."

        if action_type == "run_command":
            command = action.get("command")
            if not isinstance(command, list) or not all(
                isinstance(item, str) for item in command
            ):
                return "run_command actions require command as list[str]."
            try:
                execution_root._validate_command(command)
            except ValueError as error:
                return str(error)

        return None


DEFAULT_EXECUTION_TOOL_REGISTRY = ExecutionToolRegistry(
    (
        ExecutionTool(
            name="Read file",
            action_type="read_file",
            description="Read a file inside the execution root.",
            mutates_files=False,
            required_payload_keys=("path",),
        ),
        ExecutionTool(
            name="Write file",
            action_type="write_file",
            description="Replace a file inside the execution root and verify exact content.",
            mutates_files=True,
            required_payload_keys=("path", "content"),
        ),
        ExecutionTool(
            name="Patch file",
            action_type="patch_file",
            description="Apply an exact search/replace patch inside the execution root.",
            mutates_files=True,
            required_payload_keys=("path", "find", "replace"),
        ),
        ExecutionTool(
            name="Run command",
            action_type="run_command",
            description="Run an allowlisted command inside the execution root.",
            mutates_files=False,
            required_payload_keys=("command",),
        ),
    )
)


def get_execution_tool_registry() -> ExecutionToolRegistry:
    return DEFAULT_EXECUTION_TOOL_REGISTRY
