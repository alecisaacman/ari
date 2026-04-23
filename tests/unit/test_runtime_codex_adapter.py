from __future__ import annotations

import subprocess
from pathlib import Path

from ari_core.runtime.codex_adapter import CodexAdapter, CodexInvocationResult


def test_codex_adapter_captures_command_and_output(tmp_path: Path) -> None:
    def fake_runner(command, **kwargs):
        assert command[:2] == ["codex", "exec"]
        assert "capture this prompt" in command[-1]
        assert kwargs["cwd"] == str(tmp_path.resolve())
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    adapter = CodexAdapter(backend_mode="command", runner=fake_runner)
    result = adapter.invoke("capture this prompt", cwd=tmp_path)

    assert isinstance(result, CodexInvocationResult)
    assert result.backend == "command"
    assert result.success is True
    assert result.stdout == "done"
    assert result.stderr == ""
    assert result.exit_code == 0


def test_codex_adapter_marks_timeout_retryable(tmp_path: Path) -> None:
    def fake_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"], stderr="timed out")

    adapter = CodexAdapter(backend_mode="command", runner=fake_runner)
    result = adapter.invoke("goal", cwd=tmp_path, timeout_seconds=5)

    assert result.backend == "command"
    assert result.success is False
    assert result.retryable is True
    assert result.exit_code == -1
