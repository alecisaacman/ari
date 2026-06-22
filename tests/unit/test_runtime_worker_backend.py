from __future__ import annotations

import subprocess

from ari_core.runtime.codex_adapter import CodexAdapter, CodexInvocationResult
from ari_core.runtime.worker_backend import (
    CommandWorkerBackend,
    StubWorkerBackend,
    resolve_worker_backend,
)


def test_resolve_worker_backend_uses_env_selected_stub(monkeypatch) -> None:
    monkeypatch.setenv("ARI_WORKER_BACKEND", "stub")
    monkeypatch.setenv("ARI_WORKER_STUB_COMMAND", "stub-worker")

    backend = resolve_worker_backend()

    assert isinstance(backend, StubWorkerBackend)
    assert backend.command_prefix == ["stub-worker"]


def test_stub_worker_backend_executes_with_stub_identity(tmp_path) -> None:
    def fake_runner(command, **kwargs):
        assert command[:1] == ["stub-worker"]
        assert kwargs["cwd"] == str(tmp_path.resolve())
        return subprocess.CompletedProcess(command, 0, stdout="stub completed", stderr="")

    backend = StubWorkerBackend(command_prefix=["stub-worker"], runner=fake_runner)
    result = backend.invoke("bounded prompt", cwd=tmp_path)

    assert result == CodexInvocationResult(
        backend="stub",
        command=["stub-worker", "bounded prompt"],
        cwd=str(tmp_path.resolve()),
        success=True,
        retryable=False,
        exit_code=0,
        stdout="stub completed",
        stderr="",
    )


def test_command_worker_backend_executes_with_command_identity(tmp_path) -> None:
    def fake_runner(command, **kwargs):
        assert command[:2] == ["codex", "exec"]
        assert "implement this slice" in command[-1]
        return subprocess.CompletedProcess(command, 0, stdout="worker completed", stderr="")

    backend = CommandWorkerBackend(command_prefix=["codex", "exec"], runner=fake_runner)
    result = backend.invoke("implement this slice", cwd=tmp_path)

    assert result.backend == "command"
    assert result.success is True
    assert result.stdout == "worker completed"


def test_codex_adapter_uses_command_backend_mode(tmp_path) -> None:
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    adapter = CodexAdapter(
        backend_mode="command",
        command_prefix=["worker-command"],
        runner=fake_runner,
    )
    result = adapter.invoke("goal", cwd=tmp_path)

    assert result.backend == "command"
    assert result.command[:1] == ["worker-command"]
