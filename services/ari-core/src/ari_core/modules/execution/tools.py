from __future__ import annotations

from dataclasses import asdict, dataclass

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

    def list_tools(self) -> list[dict[str, object]]:
        return [tool.to_dict() for tool in self._tools]

    def allowed_action_types(self) -> set[str]:
        return {tool.action_type for tool in self._tools}

    def prompt_payload(self) -> dict[str, object]:
        return {
            "tools": self.list_tools(),
            "allowed_actions": sorted(self.allowed_action_types()),
            "allowed_commands": sorted(ExecutionRoot.ALLOWED_COMMANDS),
        }


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
