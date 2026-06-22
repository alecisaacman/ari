from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ...core.paths import PROJECT_ROOT
from .models import ExecutionResult


class ExecutionRoot:
    """A bounded filesystem and command sandbox rooted at a single path."""

    ALLOWED_COMMANDS = {"pytest", "ls", "cat"}

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = self._resolve_root(root)

    @staticmethod
    def _resolve_root(root: Path | str | None) -> Path:
        if root is not None:
            base = Path(root)
        else:
            env_root = os.environ.get("ARI_EXECUTION_ROOT")
            base = Path(env_root) if env_root else PROJECT_ROOT
        return base.expanduser().resolve()

    def resolve_path(self, raw_path: str | Path) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError(f"path escapes execution root: {raw_path}")
        return resolved

    def _validate_command(self, command: list[str]) -> None:
        if not command:
            raise ValueError("command is required")
        if command[0] not in self.ALLOWED_COMMANDS:
            raise ValueError(f"command is not allowlisted: {command[0]}")
        if command[0] in {"cat", "ls"}:
            for argument in command[1:]:
                if argument.startswith("-"):
                    continue
                self.resolve_path(argument)

    def read_file(self, path: str | Path) -> str:
        resolved = self.resolve_path(path)
        return resolved.read_text(encoding="utf-8")

    def write_file(self, path: str | Path, content: str) -> Path:
        resolved = self.resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return resolved

    def patch_file(self, path: str | Path, find_text: str, replace_text: str) -> Path:
        if not find_text:
            raise ValueError("find_text is required")
        resolved = self.resolve_path(path)
        content = resolved.read_text(encoding="utf-8")
        if find_text not in content:
            raise ValueError("patch target not found")
        resolved.write_text(content.replace(find_text, replace_text, 1), encoding="utf-8")
        return resolved

    def run_command(self, command: list[str], timeout_seconds: int = 30) -> ExecutionResult:
        self._validate_command(command)
        completed = subprocess.run(
            command,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ExecutionResult(
            success=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
