from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

from .command_capabilities import (
    PreparedCommand,
    prepare_command,
    run_prepared_command,
)
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

    def prepare_command(self, command: list[str]) -> PreparedCommand:
        """Resolve a command request to an explicit capability; see `command_capabilities`."""
        return prepare_command(command, root=self.root)

    def _validate_command(self, command: list[str]) -> None:
        self.prepare_command(command)

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
        prepared = self.prepare_command(command)
        completed = run_prepared_command(
            prepared,
            timeout_seconds=timeout_seconds,
            pass_fds=DISPATCH_HOLD_FDS.get(),
        )
        return ExecutionResult(
            success=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
