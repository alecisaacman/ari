from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from ari_core.core import paths as core_paths
from ari_core.execution_types import ActionIntent, ActionType
from ari_core.executor import execute_intent
from ari_core.modules.execution import (
    WORKER_INVOCATION_ACTION,
    ActionIdempotencyState,
    ExecutionLedger,
    ResumeDecision,
    RuntimeExecutionAdapter,
    RuntimeStepRequest,
    TaskLifecycleState,
)
from ari_core.runtime.codex_adapter import CodexInvocationResult
from ari_core.runtime.loop_runner import LoopRunner
from ari_core.runtime.verification_profiles import canonical_command_runner


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass
class RecordingWorker:
    """A provider worker double. It records every prompt ARI actually dispatched."""

    outcome: CodexInvocationResult | Exception | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def invoke(self, prompt: str, *, cwd: Any = None, timeout_seconds: int = 600) -> Any:
        self.calls.append((prompt, Path(cwd)))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome or _worker_result(cwd)


def _worker_result(cwd: Any, *, success: bool = True, retryable: bool = False) -> CodexInvocationResult:
    return CodexInvocationResult(
        backend="stub",
        command=["worker"],
        cwd=str(cwd),
        success=success,
        retryable=retryable,
        exit_code=0 if success else 1,
        stdout="implemented change" if success else "",
        stderr="" if success else "temporary network error",
    )


def _not_paused() -> dict[str, Any]:
    return {"paused": False, "reason": None}


@pytest.fixture
def ledger_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Kept outside the execution root: ARI refuses roots that contain its own state.
    return tmp_path_factory.mktemp("ledger") / "ari.db"


def _worker_request(**overrides: Any) -> RuntimeStepRequest:
    request = RuntimeStepRequest(
        action={"type": WORKER_INVOCATION_ACTION, "worker": "worker-a", "prompt": "Do the slice."},
        objective="Implement a bounded slice.",
        reason="Hand the slice to the worker.",
        worker_identity="worker-a",
        loop_id="loop-1",
        restrictions=("no automatic side effects",),
    )
    return replace(request, **overrides)


def test_worker_step_crosses_the_canonical_gateway_once(tmp_path: Path, ledger_path: Path) -> None:
    worker = RecordingWorker()
    adapter = RuntimeExecutionAdapter(
        ledger_path,
        execution_root=tmp_path,
        workers={"worker-a": worker},
        pause_state_reader=_not_paused,
    )

    step = adapter.run_step(_worker_request())

    assert step.decision is ResumeDecision.ALLOW
    assert step.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert step.succeeded
    assert worker.calls == [("Do the slice.", tmp_path.resolve())]
    task = ExecutionLedger(ledger_path).get_task(step.task_id)
    assert task is not None
    assert task["linked_task_id"] == "loop-1"
    assert task["lifecycle_state"] == TaskLifecycleState.SUCCEEDED
    assert task["restrictions"] == ["no automatic side effects"]
    assert task["authority_scope"] == {"permitted_side_effects": [WORKER_INVOCATION_ACTION]}
    inspection = adapter.gateway.inspect_task(step.task_id)
    assert [execution["state"] for execution in inspection["executions"]] == ["succeeded"]
    # A worker invocation is unbounded: once crossed it is never safe to redispatch.
    assert [fence["effect_terminality"] for fence in inspection["dispatch_fences"]] == ["unbounded"]
    assert inspection["redispatch_safety"][0]["safe_to_redispatch"] is False


def test_global_pause_blocks_the_worker_before_dispatch(tmp_path: Path, ledger_path: Path) -> None:
    worker = RecordingWorker()
    adapter = RuntimeExecutionAdapter(
        ledger_path,
        execution_root=tmp_path,
        workers={"worker-a": worker},
        pause_state_reader=lambda: {"paused": True, "reason": "operator stop"},
    )

    step = adapter.run_step(_worker_request())

    assert step.decision is ResumeDecision.BLOCKED
    assert step.executed is False
    assert worker.calls == []


def test_unconfigured_worker_is_refused_by_the_gateway(tmp_path: Path, ledger_path: Path) -> None:
    worker = RecordingWorker()
    adapter = RuntimeExecutionAdapter(
        ledger_path,
        execution_root=tmp_path,
        workers={"worker-a": worker},
        pause_state_reader=_not_paused,
    )

    step = adapter.run_step(
        _worker_request(
            action={"type": WORKER_INVOCATION_ACTION, "worker": "worker-b", "prompt": "x"},
            worker_identity="worker-b",
        )
    )

    assert step.decision is ResumeDecision.BLOCKED
    assert "not configured" in step.reason
    assert worker.calls == []


def test_worker_cannot_run_under_a_no_network_restriction(tmp_path: Path, ledger_path: Path) -> None:
    adapter = RuntimeExecutionAdapter(
        ledger_path, execution_root=tmp_path, workers={"worker-a": RecordingWorker()}
    )

    with pytest.raises(ValueError, match="no network"):
        adapter.run_step(_worker_request(restrictions=("no network",)))


def test_execution_root_outside_the_configured_root_fails_closed(
    ledger_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere")

    with pytest.raises(ValueError):
        RuntimeExecutionAdapter(ledger_path, execution_root=elsewhere)


def test_approval_and_task_state_survive_worker_replacement(tmp_path: Path, ledger_path: Path) -> None:
    clock = FixedClock()
    worker = RecordingWorker()
    adapter = RuntimeExecutionAdapter(
        ledger_path,
        execution_root=tmp_path,
        workers={"worker-a": worker},
        clock=clock,
        pause_state_reader=_not_paused,
        lease_seconds=5,
    )
    prepared = adapter.prepare_step(_worker_request(approval_required=True))

    gated = adapter.dispatch_step(prepared)
    assert gated.decision is ResumeDecision.REQUIRE_APPROVAL
    assert worker.calls == []
    adapter.gateway.approve_next_action(
        task_id=prepared.task_id,
        attempt_id=prepared.attempt_id,
        approved_by="alec",
        reason="Approved for this slice.",
    )

    # The worker is lost after approval and before dispatch.
    clock.advance(seconds=6)
    recovery = adapter.sessions.reconcile_stale_attempt(
        prepared.attempt_id,
        replacement_worker_identity="worker-a",
        lease_seconds=300,
    )
    assert recovery.replacement_attempt_id is not None
    assert recovery.continuation_packet_id is not None
    adapter._acknowledge(recovery.continuation_packet_id, "worker-a")
    replacement = adapter.sessions.inspect_task(prepared.task_id)
    assert replacement is not None
    resumed = replace(
        prepared,
        attempt_id=recovery.replacement_attempt_id,
        session_id=str(replacement["session"]["active_attempt"]["session_id"]),
    )

    step = adapter.dispatch_step(resumed)

    assert step.decision is ResumeDecision.ALLOW
    assert step.succeeded
    assert len(worker.calls) == 1
    task = ExecutionLedger(ledger_path).get_task(prepared.task_id)
    assert task is not None
    assert task["restrictions"] == ["no automatic side effects"]
    assert task["approval_state"] == {"required": True, "status": "pending"}

    # One-action resume: the completed action is never dispatched again.
    again = adapter.dispatch_step(resumed)
    assert again.executed is False
    assert len(worker.calls) == 1


def test_loop_runner_routes_each_cycle_through_canonical_steps(tmp_path: Path, ledger_path: Path) -> None:
    class FlakyAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, prompt: str, *, cwd: Any = None, timeout_seconds: int = 600) -> Any:
            self.calls += 1
            return _worker_result(cwd, success=self.calls > 1, retryable=self.calls == 1)

    adapter = FlakyAdapter()
    result = LoopRunner(adapter=adapter, db_path=ledger_path).run("Goal", max_cycles=2, cwd=tmp_path)

    assert result.status == "stop"
    assert adapter.calls == 2
    assert len(result.canonical_steps) == 2
    # The retry is a newly planned canonical step, not a redispatch of the first.
    assert len({step.task_id for step in result.canonical_steps}) == 2
    ledger = ExecutionLedger(ledger_path)
    for step in result.canonical_steps:
        task = ledger.get_task(step.task_id)
        assert task is not None
        assert task["linked_task_id"] == result.loop_id


def test_loop_runner_never_retries_an_uncertain_worker_effect(tmp_path: Path, ledger_path: Path) -> None:
    class CrashingAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, prompt: str, *, cwd: Any = None, timeout_seconds: int = 600) -> Any:
            self.calls += 1
            raise RuntimeError("worker crashed mid-edit: temporary network error")

    adapter = CrashingAdapter()
    result = LoopRunner(adapter=adapter, db_path=ledger_path).run("Goal", max_cycles=3, cwd=tmp_path)

    assert adapter.calls == 1
    assert result.status == "escalate"
    assert "uncertain" in result.reason
    assert result.canonical_steps[0].idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN


def test_loop_runner_blocks_without_a_permitted_execution_root(
    ledger_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    worker = RecordingWorker()

    result = LoopRunner(adapter=worker, db_path=ledger_path).run(
        "Goal", max_cycles=1, cwd=tmp_path_factory.mktemp("elsewhere")
    )

    assert result.status == "blocked"
    assert result.cycles_run == 0
    assert worker.calls == []


def test_verification_command_outside_the_capabilities_is_refused(
    tmp_path: Path, ledger_path: Path
) -> None:
    run = canonical_command_runner(RuntimeExecutionAdapter(ledger_path, execution_root=tmp_path))

    result = run(["python3", "-c", "open('escaped.txt', 'w').write('x')"])

    assert result.success is False
    assert result.exit_code == -1
    assert "ARI did not run the verification command" in result.stderr
    assert not (tmp_path / "escaped.txt").exists()


def test_verification_pytest_runs_through_the_capability(tmp_path: Path, ledger_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    run = canonical_command_runner(RuntimeExecutionAdapter(ledger_path, execution_root=tmp_path))

    result = run(["python", "-m", "pytest", "test_ok.py", "-q"])

    assert result.success is True
    assert result.exit_code == 0


def test_legacy_controller_reads_go_through_the_canonical_ledger(
    tmp_path: Path, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_paths, "DB_PATH", ledger_path)
    (tmp_path / "notes.txt").write_text("canonical read\n", encoding="utf-8")

    observation = execute_intent(
        ActionIntent(action_type=ActionType.READ_FILE, target="notes.txt", instructions="Read notes.")
    )

    assert observation.success is True
    assert observation.details == "canonical read\n"
    tasks = ExecutionLedger(ledger_path)._many("select * from ari_execution_tasks", ())
    assert len(tasks) == 1
    attempts = ExecutionLedger(ledger_path)._many(
        "select worker_identity from ari_execution_attempts where worker_identity is not null", ()
    )
    assert [row["worker_identity"] for row in attempts] == ["ari-legacy-controller"]


@pytest.mark.unset_execution_root
def test_legacy_controller_fails_closed_without_a_configured_root(
    ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_paths, "DB_PATH", ledger_path)

    observation = execute_intent(
        ActionIntent(action_type=ActionType.RUN_COMMAND, target="pytest -q", instructions="Run tests.")
    )

    assert observation.success is False
    assert observation.kind == "execution_root_refused"
