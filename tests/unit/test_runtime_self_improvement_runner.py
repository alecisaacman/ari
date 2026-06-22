from __future__ import annotations

import sys
from pathlib import Path

from ari_core.modules.coordination.db import list_coordination_entities, put_coordination_entity
from ari_core.runtime.codex_adapter import CodexInvocationResult
from ari_core.runtime.loop_runner import LoopRunnerResult
from ari_core.runtime.self_improvement_runner import ImprovementSlice, SelfImprovementRunner


def test_self_improvement_runner_selects_missing_slice_and_continues(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []

    catalog = (
        ImprovementSlice(
            key="slice-a",
            title="Create first file",
            prompt_hint="Create first file.",
            expected_paths=("a.txt",),
        ),
        ImprovementSlice(
            key="slice-b",
            title="Create second file",
            prompt_hint="Create second file.",
            expected_paths=("b.txt",),
        ),
    )

    def fake_loop_run(goal, *, max_cycles, cwd, db_path, adapter, prepared_prompt=None):
        calls.append(goal)
        assert prepared_prompt is not None
        if "[self-improvement:slice-a]" in goal:
            (Path(cwd) / "a.txt").write_text("a\n", encoding="utf-8")
        if "[self-improvement:slice-b]" in goal:
            (Path(cwd) / "b.txt").write_text("b\n", encoding="utf-8")
        return LoopRunnerResult(
            loop_id=f"loop-{len(calls)}",
            goal=goal,
            status="stop",
            reason="usable result",
            cycles_run=1,
            worker_runs=[
                CodexInvocationResult(
                    backend="stub",
                    command=["codex", "exec", goal],
                    cwd=str(Path(cwd).resolve()),
                    success=True,
                    retryable=False,
                    exit_code=0,
                    stdout="implemented change",
                    stderr="",
                )
            ],
            persisted_loop={"id": f"loop-{len(calls)}"},
        )

    runner = SelfImprovementRunner(
        db_path=db_path,
        loop_run_callable=fake_loop_run,
        slice_catalog=catalog,
    )
    result = runner.run("Close the next bounded runtime gaps", max_cycles=3, cwd=repo_root)

    assert result.status == "stop"
    assert result.cycles_run == 2
    assert [cycle.slice_key for cycle in result.cycles] == ["slice-a", "slice-b"]
    assert (repo_root / "a.txt").exists()
    assert (repo_root / "b.txt").exists()


def test_self_improvement_runner_skips_completed_previous_slice(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "a.txt").write_text("a\n", encoding="utf-8")

    put_coordination_entity(
        "runtime_loop_record",
        {
            "id": "runtime-loop-1",
            "goal": "[self-improvement:slice-a] previous goal",
            "status": "stop",
            "reason": "done",
            "cycles_run": 1,
            "max_cycles": 1,
            "final_output": "done",
            "final_error": "",
            "last_worker_run_id": None,
            "created_at": "2026-04-21T00:00:00Z",
            "updated_at": "2026-04-21T00:00:00Z",
        },
        db_path=db_path,
    )

    catalog = (
        ImprovementSlice(key="slice-a", title="Create first file", prompt_hint="Create first file.", expected_paths=("a.txt",)),
        ImprovementSlice(key="slice-b", title="Create second file", prompt_hint="Create second file.", expected_paths=("b.txt",)),
    )
    captured_goals: list[str] = []

    def fake_loop_run(goal, *, max_cycles, cwd, db_path, adapter, prepared_prompt=None):
        captured_goals.append(goal)
        assert prepared_prompt is not None
        (Path(cwd) / "b.txt").write_text("b\n", encoding="utf-8")
        return LoopRunnerResult(
            loop_id="loop-2",
            goal=goal,
            status="stop",
            reason="usable result",
            cycles_run=1,
            worker_runs=[
                CodexInvocationResult(
                    backend="stub",
                    command=["codex", "exec", goal],
                    cwd=str(Path(cwd).resolve()),
                    success=True,
                    retryable=False,
                    exit_code=0,
                    stdout="implemented change",
                    stderr="",
                )
            ],
            persisted_loop={"id": "loop-2"},
        )

    runner = SelfImprovementRunner(
        db_path=db_path,
        loop_run_callable=fake_loop_run,
        slice_catalog=catalog,
    )
    result = runner.run("Continue bounded runtime improvement", max_cycles=2, cwd=repo_root)

    assert result.status == "continue" or result.status == "stop"
    assert captured_goals
    assert captured_goals[0].startswith("[self-improvement:slice-b]")


def test_self_improvement_runner_prefers_execution_intent_aligned_slice_and_persists_controller_decision(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "EXECUTION_INTENT.md").write_text(
        "## Next objective\nBuild a stronger governed coding loop.\n",
        encoding="utf-8",
    )

    catalog = (
        ImprovementSlice(
            key="surface-polish",
            title="Polish the terminal surface",
            prompt_hint="Tighten terminal copy.",
            milestone="terminal surface",
            priority=80,
            expected_paths=("surface.txt",),
        ),
        ImprovementSlice(
            key="governed-loop",
            title="Strengthen governed coding loop quality",
            prompt_hint="Improve controller-quality loop behavior.",
            milestone="governed coding loop",
            priority=80,
            route_keywords=("governed coding loop", "controller"),
            expected_paths=("loop.txt",),
        ),
    )

    def fake_loop_run(goal, *, max_cycles, cwd, db_path, adapter, prepared_prompt=None):
        assert prepared_prompt is not None
        assert "Milestone: governed coding loop" in prepared_prompt
        if "[self-improvement:governed-loop]" in goal:
            (Path(cwd) / "loop.txt").write_text("done\n", encoding="utf-8")
        return LoopRunnerResult(
            loop_id="loop-1",
            goal=goal,
            status="stop",
            reason="usable result",
            cycles_run=1,
            worker_runs=[
                CodexInvocationResult(
                    backend="stub",
                    command=["codex", "exec", goal],
                    cwd=str(Path(cwd).resolve()),
                    success=True,
                    retryable=False,
                    exit_code=0,
                    stdout="implemented change",
                    stderr="",
                )
            ],
            persisted_loop={"id": "loop-1"},
        )

    runner = SelfImprovementRunner(
        db_path=db_path,
        loop_run_callable=fake_loop_run,
        slice_catalog=catalog,
    )
    result = runner.run("Improve ARI's governed coding loop safely", max_cycles=1, cwd=repo_root)

    assert result.cycles
    assert result.cycles[0].slice_key == "governed-loop"
    rows = list_coordination_entities("runtime_controller_decision", limit=10, db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["selected_slice_key"] == "governed-loop"
    assert "governed coding loop" in rows[0]["selection_reason"].lower()


def test_self_improvement_runner_retries_same_slice_when_verification_evidence_is_incomplete(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []

    catalog = (
        ImprovementSlice(
            key="controller-loop",
            title="Strengthen controller loop",
            prompt_hint="Improve the bounded controller loop.",
            milestone="governed coding loop",
            priority=100,
            expected_paths=("controller.py",),
            expected_symbols={"controller.py": ("READY",)},
            verification_commands=((sys.executable, "-m", "pytest", "--version"),),
        ),
    )

    prompts: list[str] = []

    def fake_loop_run(goal, *, max_cycles, cwd, db_path, adapter, prepared_prompt=None):
        calls.append(goal)
        prompts.append(prepared_prompt or "")
        target = Path(cwd) / "controller.py"
        if len(calls) == 1:
            target.write_text("STATE = 'PENDING'\n", encoding="utf-8")
        else:
            target.write_text("READY = True\n", encoding="utf-8")
        return LoopRunnerResult(
            loop_id=f"loop-{len(calls)}",
            goal=goal,
            status="stop",
            reason="usable result",
            cycles_run=1,
            worker_runs=[
                CodexInvocationResult(
                    backend="stub",
                    command=["codex", "exec", goal],
                    cwd=str(Path(cwd).resolve()),
                    success=True,
                    retryable=False,
                    exit_code=0,
                    stdout="implemented change",
                    stderr="",
                )
            ],
            persisted_loop={"id": f"loop-{len(calls)}"},
        )

    runner = SelfImprovementRunner(
        db_path=db_path,
        loop_run_callable=fake_loop_run,
        slice_catalog=catalog,
    )
    result = runner.run("Tighten the governed coding loop", max_cycles=2, cwd=repo_root)

    assert result.cycles_run == 2
    assert [cycle.verification_status for cycle in result.cycles] == ["retry", "continue"]
    assert [cycle.slice_key for cycle in result.cycles] == ["controller-loop", "controller-loop"]
    assert "Previous verification gaps:" in prompts[1]
    assert "Specifically resolve:" in prompts[1]
    action_plan_rows = list_coordination_entities("runtime_action_plan", limit=10, db_path=db_path)
    assert len(action_plan_rows) == 2
    assert action_plan_rows[0]["attempt_kind"] in {"retry", "initial"}


def test_self_improvement_runner_escalates_after_repeated_verification_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    catalog = (
        ImprovementSlice(
            key="controller-loop",
            title="Strengthen controller loop",
            prompt_hint="Improve the bounded controller loop.",
            milestone="governed coding loop",
            priority=100,
            expected_paths=("controller.py",),
            verification_commands=((sys.executable, "-c", "raise SystemExit(1)"),),
        ),
    )

    def fake_loop_run(goal, *, max_cycles, cwd, db_path, adapter, prepared_prompt=None):
        assert prepared_prompt is not None
        (Path(cwd) / "controller.py").write_text("READY = True\n", encoding="utf-8")
        return LoopRunnerResult(
            loop_id="loop-1",
            goal=goal,
            status="stop",
            reason="usable result",
            cycles_run=1,
            worker_runs=[
                CodexInvocationResult(
                    backend="stub",
                    command=["codex", "exec", goal],
                    cwd=str(Path(cwd).resolve()),
                    success=True,
                    retryable=False,
                    exit_code=0,
                    stdout="implemented change",
                    stderr="",
                )
            ],
            persisted_loop={"id": "loop-1"},
        )

    runner = SelfImprovementRunner(
        db_path=db_path,
        loop_run_callable=fake_loop_run,
        slice_catalog=catalog,
    )
    result = runner.run("Tighten the governed coding loop", max_cycles=2, cwd=repo_root)

    assert result.status == "escalate"
    assert [cycle.verification_status for cycle in result.cycles] == ["retry", "escalate"]
