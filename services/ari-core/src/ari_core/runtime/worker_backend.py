from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]
WorkerBackendMode = Literal["stub", "command"]
RETRYABLE_PATTERNS = ("timed out", "timeout", "temporar", "connection reset", "network")


@dataclass(frozen=True, slots=True)
class WorkerInvocationResult:
    backend: WorkerBackendMode
    command: list[str]
    cwd: str
    success: bool
    retryable: bool
    exit_code: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WorkerBackend(Protocol):
    backend: WorkerBackendMode

    def invoke(
        self,
        prompt: str,
        *,
        cwd: Path | str | None = None,
        timeout_seconds: int = 600,
    ) -> WorkerInvocationResult:
        ...


class StubWorkerBackend:
    def __init__(
        self,
        *,
        command_prefix: Sequence[str] | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.backend: WorkerBackendMode = "stub"
        self.command_prefix = list(command_prefix or _default_stub_command_prefix())
        self.runner = runner or subprocess.run

    def invoke(
        self,
        prompt: str,
        *,
        cwd: Path | str | None = None,
        timeout_seconds: int = 600,
    ) -> WorkerInvocationResult:
        return _invoke_worker_command(
            backend=self.backend,
            command_prefix=self.command_prefix,
            prompt=prompt,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            runner=self.runner,
        )


class CommandWorkerBackend:
    def __init__(
        self,
        *,
        command_prefix: Sequence[str] | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.backend: WorkerBackendMode = "command"
        self.command_prefix = list(command_prefix or _default_command_prefix())
        self.runner = runner or subprocess.run

    def invoke(
        self,
        prompt: str,
        *,
        cwd: Path | str | None = None,
        timeout_seconds: int = 600,
    ) -> WorkerInvocationResult:
        return _invoke_worker_command(
            backend=self.backend,
            command_prefix=self.command_prefix,
            prompt=prompt,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            runner=self.runner,
        )


def resolve_worker_backend(
    *,
    backend_mode: WorkerBackendMode | None = None,
    command_prefix: Sequence[str] | None = None,
    runner: Runner | None = None,
) -> WorkerBackend:
    mode = _resolve_backend_mode(backend_mode)
    if mode == "stub":
        return StubWorkerBackend(command_prefix=command_prefix, runner=runner)
    return CommandWorkerBackend(command_prefix=command_prefix, runner=runner)


def _resolve_backend_mode(backend_mode: WorkerBackendMode | None) -> WorkerBackendMode:
    if backend_mode is not None:
        return backend_mode
    raw = os.environ.get("ARI_WORKER_BACKEND", "").strip().lower()
    if raw == "stub":
        return "stub"
    return "command"


def _invoke_worker_command(
    *,
    backend: WorkerBackendMode,
    command_prefix: Sequence[str],
    prompt: str,
    cwd: Path | str | None,
    timeout_seconds: int,
    runner: Runner,
) -> WorkerInvocationResult:
    command = [*command_prefix, prompt]
    resolved_cwd = str(Path(cwd or Path.cwd()).expanduser().resolve())
    try:
        completed = runner(
            command,
            cwd=resolved_cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return WorkerInvocationResult(
            backend=backend,
            command=command,
            cwd=resolved_cwd,
            success=completed.returncode == 0,
            retryable=_is_retryable(completed.stdout, completed.stderr),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as error:
        return WorkerInvocationResult(
            backend=backend,
            command=command,
            cwd=resolved_cwd,
            success=False,
            retryable=True,
            exit_code=-1,
            stdout=error.stdout or "",
            stderr=error.stderr or "Worker invocation timed out.",
        )
    except FileNotFoundError as error:
        return WorkerInvocationResult(
            backend=backend,
            command=command,
            cwd=resolved_cwd,
            success=False,
            retryable=False,
            exit_code=-1,
            stdout="",
            stderr=str(error),
        )


def _default_command_prefix() -> list[str]:
    parsed = _parse_command_from_env("ARI_WORKER_COMMAND_JSON", "ARI_WORKER_COMMAND")
    if parsed:
        return parsed
    parsed = _parse_command_from_env("ARI_CODEX_COMMAND_JSON", "ARI_CODEX_COMMAND")
    if parsed:
        return parsed
    return ["codex", "exec"]


def _default_stub_command_prefix() -> list[str]:
    parsed = _parse_command_from_env("ARI_WORKER_STUB_COMMAND_JSON", "ARI_WORKER_STUB_COMMAND")
    if parsed:
        return parsed
    return [
        sys.executable,
        "-c",
        (
            "import sys; "
            "prompt = sys.argv[1] if len(sys.argv) > 1 else ''; "
            "print('stub worker received prompt: ' + prompt[:120])"
        ),
    ]


def _parse_command_from_env(json_key: str, text_key: str) -> list[str]:
    raw_json = os.environ.get(json_key, "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and all(isinstance(item, str) and item for item in parsed):
                return list(parsed)
        except json.JSONDecodeError:
            pass

    raw_command = os.environ.get(text_key, "").strip()
    if raw_command:
        parsed = shlex.split(raw_command)
        if parsed:
            return parsed
    return []


def _is_retryable(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    return any(pattern in combined for pattern in RETRYABLE_PATTERNS)
