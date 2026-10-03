from __future__ import annotations

import subprocess
from contextvars import ContextVar
from pathlib import Path

from .fs_authority import (
    protected_write_reason,
    read_text_nofollow,
    reject_final_symlink,
    replace_text_atomically,
    resolve_execution_root,
)
from .models import ExecutionResult

# Dispatch-lock descriptors held by the current dispatch. Subprocesses inherit them,
# so the lock stays held while a child outlives a killed parent.
DISPATCH_HOLD_FDS: ContextVar[tuple[int, ...]] = ContextVar("DISPATCH_HOLD_FDS", default=())


class ExecutionRoot:
    """Filesystem and command authority rooted at one confined path.

    The root is always the configured execution root or a descendant of it; see
    `fs_authority`. This bounds what ARI's own tools request. It is not OS
    containment of the commands those tools run.
    """

    ALLOWED_COMMANDS = {"pytest", "ls", "cat"}

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = resolve_execution_root(root)

    def resolve_path(self, raw_path: str | Path) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError(f"path escapes execution root: {raw_path}")
        return resolved

    def resolve_write_path(self, raw_path: str | Path) -> Path:
        """Resolve a mutation target, refusing symlinks and protected ARI internals."""
        reject_final_symlink(self.root, raw_path)
        resolved = self.resolve_path(raw_path)
        reason = protected_write_reason(self.root, resolved)
        if reason is not None:
            raise ValueError(reason)
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
        return read_text_nofollow(self.resolve_path(path))

    def write_file(self, path: str | Path, content: str) -> Path:
        resolved = self.resolve_write_path(path)
        return replace_text_atomically(self.root, resolved, content)

    def patch_file(self, path: str | Path, find_text: str, replace_text: str) -> Path:
        if not find_text:
            raise ValueError("find_text is required")
        resolved = self.resolve_write_path(path)
        content = read_text_nofollow(resolved)
        if find_text not in content:
            raise ValueError("patch target not found")
        return replace_text_atomically(
            self.root, resolved, content.replace(find_text, replace_text, 1)
        )

    def run_command(self, command: list[str], timeout_seconds: int = 30) -> ExecutionResult:
        self._validate_command(command)
        completed = subprocess.run(
            command,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            pass_fds=DISPATCH_HOLD_FDS.get(),
        )
        return ExecutionResult(
            success=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
