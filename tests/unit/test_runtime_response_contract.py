from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

def test_build_cli_response_marks_successful_codex_loop_completed() -> None:
    from ari_core.runtime.response_contract import build_cli_response

    response = build_cli_response(
        goal="Implement a tiny runtime slice",
        route="codex_loop",
        route_reason="Explicit runtime invocation.",
        result={
            "status": "stop",
            "reason": "Codex returned a usable result.",
            "cyclesRun": 1,
        },
    )

    payload = response.to_dict()
    assert payload["status"] == "completed"
    assert payload["ok"] is True
    assert "bounded codex worker loop" in payload["summary"].lower()
    assert payload["nextStep"] is None


def test_build_cli_response_marks_dirty_repo_attention_needed() -> None:
    from ari_core.runtime.response_contract import build_cli_response

    response = build_cli_response(
        goal="inspect repo status",
        route="repo_inspect",
        route_reason="Explicit repo inspection.",
        result={
            "gitDirty": True,
            "changedPaths": ["services/ari-core/src/ari_core/runtime/request_router.py"],
        },
    )

    payload = response.to_dict()
    assert payload["status"] == "attention_needed"
    assert payload["ok"] is False
    assert "found 1 changed path" in payload["summary"].lower()


def test_handle_runtime_codex_loop_emits_unified_contract(monkeypatch) -> None:
    from ari_core.runtime.codex_adapter import CodexInvocationResult
    from ari_core.runtime.loop_runner import LoopRunnerResult, handle_runtime_codex_loop

    monkeypatch.setattr(
        "ari_core.runtime.loop_runner.run_goal_loop",
        lambda goal, *, max_cycles, cwd, db_path: LoopRunnerResult(
            loop_id="loop-1",
            goal=goal,
            status="stop",
            reason="Codex returned a usable result.",
            cycles_run=1,
            worker_runs=[
                CodexInvocationResult(
                    backend="command",
                    command=["codex", "exec", goal],
                    cwd=str(cwd),
                    success=True,
                    retryable=False,
                    exit_code=0,
                    stdout="implemented change",
                    stderr="",
                )
            ],
            persisted_loop={"id": "loop-1"},
        ),
    )
    args = SimpleNamespace(goal="Implement a tiny runtime slice", max_cycles=1, cwd=".")

    output = StringIO()
    with redirect_stdout(output):
        exit_code = handle_runtime_codex_loop(args)

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["route"] == "codex_loop"
    assert payload["status"] == "completed"
    assert payload["identity"] == "ARI"


def test_handle_runtime_self_improve_emits_unified_contract(monkeypatch) -> None:
    from ari_core.runtime.self_improvement_runner import SelfImprovementRunResult, handle_runtime_self_improve

    monkeypatch.setattr(
        "ari_core.runtime.self_improvement_runner.run_self_improvement_loop",
        lambda goal, *, max_cycles, cwd, db_path: SelfImprovementRunResult(
            goal=goal,
            status="stop",
            reason="No further bounded self-improvement slice is available.",
            cycles_run=1,
            cycles=[],
        ),
    )
    args = SimpleNamespace(goal="Improve ARI safely", max_cycles=1, cwd=".")

    output = StringIO()
    with redirect_stdout(output):
        exit_code = handle_runtime_self_improve(args)

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["route"] == "self_improve"
    assert payload["status"] == "completed"
    assert payload["identity"] == "ARI"
