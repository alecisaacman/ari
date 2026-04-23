from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .worker_backend import (
    CommandWorkerBackend,
    Runner,
    StubWorkerBackend,
    WorkerBackend,
    WorkerBackendMode,
    WorkerInvocationResult,
    resolve_worker_backend,
)


CodexInvocationResult = WorkerInvocationResult


class CodexAdapter:
    def __init__(
        self,
        *,
        backend: WorkerBackend | None = None,
        backend_mode: WorkerBackendMode | None = None,
        command_prefix: Sequence[str] | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.backend = backend or resolve_worker_backend(
            backend_mode=backend_mode,
            command_prefix=command_prefix,
            runner=runner,
        )

    def invoke(
        self,
        prompt: str,
        *,
        cwd: Path | str | None = None,
        timeout_seconds: int = 600,
    ) -> CodexInvocationResult:
        return self.backend.invoke(prompt, cwd=cwd, timeout_seconds=timeout_seconds)


__all__ = [
    "CodexAdapter",
    "CodexInvocationResult",
    "CommandWorkerBackend",
    "StubWorkerBackend",
]
