from __future__ import annotations

import subprocess
from pathlib import Path

from ari_core.modules.coordination.db import list_coordination_entities
from ari_core.runtime.codex_adapter import CodexAdapter, CodexInvocationResult
from ari_core.runtime.loop_runner import LoopRunner


class FakeAdapter:
    def __init__(self, results):
        self._results = list(results)
        self.prompts: list[str] = []

    def invoke(self, prompt: str, *, cwd=None, timeout_seconds=600):
        self.prompts.append(prompt)
        return self._results.pop(0)


def test_loop_runner_stops_on_success_and_persists_records(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    adapter = FakeAdapter(
        [
            CodexInvocationResult(
                backend="stub",
                command=["codex", "exec", "goal"],
                cwd=str(tmp_path.resolve()),
                success=True,
                retryable=False,
                exit_code=0,
                stdout="implemented change",
                stderr="",
            )
        ]
    )
    runner = LoopRunner(adapter=adapter, db_path=db_path)

    result = runner.run("Implement a tiny coding slice", max_cycles=1, cwd=tmp_path)

    assert result.status == "stop"
    assert result.cycles_run == 1
    assert len(result.worker_runs) == 1

    loop_rows = list_coordination_entities("runtime_loop_record", limit=10, db_path=db_path)
    worker_rows = list_coordination_entities("runtime_worker_run", limit=10, db_path=db_path)
    assert len(loop_rows) == 1
    assert loop_rows[0]["status"] == "stop"
    assert len(worker_rows) == 1
    assert worker_rows[0]["backend"] == "stub"
    assert worker_rows[0]["success"] == 1


def test_loop_runner_retries_once_then_stops(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    adapter = FakeAdapter(
        [
            CodexInvocationResult(
                backend="stub",
                command=["codex", "exec", "goal"],
                cwd=str(tmp_path.resolve()),
                success=False,
                retryable=True,
                exit_code=1,
                stdout="",
                stderr="temporary network timeout",
            ),
            CodexInvocationResult(
                backend="stub",
                command=["codex", "exec", "goal"],
                cwd=str(tmp_path.resolve()),
                success=True,
                retryable=False,
                exit_code=0,
                stdout="implemented after retry",
                stderr="",
            ),
        ]
    )
    runner = LoopRunner(adapter=adapter, db_path=db_path)

    result = runner.run("Retryable coding goal", max_cycles=2, cwd=tmp_path)

    assert result.status == "stop"
    assert result.cycles_run == 2
    assert len(adapter.prompts) == 2
    assert "Previous stderr" in adapter.prompts[1]


def test_loop_runner_uses_prepared_prompt_when_provided(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    adapter = FakeAdapter(
        [
            CodexInvocationResult(
                backend="stub",
                command=["codex", "exec", "goal"],
                cwd=str(tmp_path.resolve()),
                success=True,
                retryable=False,
                exit_code=0,
                stdout="implemented change",
                stderr="",
            )
        ]
    )
    runner = LoopRunner(adapter=adapter, db_path=db_path)

    runner.run("High-level goal", max_cycles=1, cwd=tmp_path, prepared_prompt="EXPLICIT ACTION PLAN PROMPT")

    assert adapter.prompts[0] == "EXPLICIT ACTION PLAN PROMPT"


def test_loop_runner_persists_command_backend_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="command backend ok", stderr="")

    runner = LoopRunner(
        adapter=CodexAdapter(
            backend_mode="command",
            command_prefix=["command-worker"],
            runner=fake_runner,
        ),
        db_path=db_path,
    )

    result = runner.run("Implement a bounded coding slice", max_cycles=1, cwd=tmp_path)

    assert result.worker_runs[0].backend == "command"
    worker_rows = list_coordination_entities("runtime_worker_run", limit=10, db_path=db_path)
    assert len(worker_rows) == 1
    assert worker_rows[0]["backend"] == "command"
