from __future__ import annotations

import json
from pathlib import Path

import pytest

from ari_core.runtime.scenario_harness import run_playground_goal, run_runtime_scenarios


def test_run_runtime_scenarios_executes_default_playground_cases(tmp_path: Path) -> None:
    workspace_root = tmp_path / "playground"

    result = run_runtime_scenarios(workspace=workspace_root, reset_workspace=True)

    assert len(result.scenarios) == 5
    by_name = {scenario.scenario: scenario for scenario in result.scenarios}
    assert set(by_name) == {"repo_inspect", "note_capture", "plan_only", "codex_loop", "self_improve"}

    repo_inspect = by_name["repo_inspect"]
    assert repo_inspect.route == "repo_inspect"
    assert repo_inspect.acceptance.status == "pass"
    assert repo_inspect.summary_path
    assert Path(repo_inspect.summary_path).exists()

    note_capture = by_name["note_capture"]
    assert note_capture.route == "document_or_note_capture"
    assert note_capture.acceptance.status == "pass"
    assert note_capture.response["data"]["id"]

    plan_only = by_name["plan_only"]
    assert plan_only.route == "plan_only"
    assert plan_only.response["status"] == "planned"

    codex_loop = by_name["codex_loop"]
    assert codex_loop.route == "codex_loop"
    assert codex_loop.acceptance.status == "pass"
    assert codex_loop.worker_result is not None
    assert codex_loop.worker_result["backend"] == "stub"
    assert codex_loop.worker_result["success"] is True
    assert "worker-note.txt" in codex_loop.changed_files

    self_improve = by_name["self_improve"]
    assert self_improve.route == "self_improve"
    assert self_improve.acceptance.status == "pass"
    assert self_improve.selected_slice == "playground-self-improve"
    assert self_improve.action_plan is not None
    assert self_improve.worker_result is not None
    assert self_improve.worker_result["backend"] == "stub"
    assert self_improve.semantic_verification is not None
    assert self_improve.semantic_verification["classification"] == "success"
    assert self_improve.controller_decision is not None
    assert "playground_module.py" in self_improve.changed_files

    persisted_summary = json.loads(Path(self_improve.summary_path).read_text(encoding="utf-8"))
    assert persisted_summary["scenario"] == "self_improve"
    assert persisted_summary["controller_decision"]["selectedSliceKey"] == "playground-self-improve"


def test_run_runtime_scenarios_rejects_unknown_scenario_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown scenario name"):
        run_runtime_scenarios(workspace=tmp_path / "playground", scenario_names=["does-not-exist"], reset_workspace=True)


def test_run_playground_goal_routes_and_persists_summary(tmp_path: Path) -> None:
    result = run_playground_goal(
        "inspect repo status and what changed",
        workspace=tmp_path / "playground",
        reset_workspace=True,
    )

    assert result.route == "repo_inspect"
    assert result.acceptance.status == "partial"
    assert result.summary_path
    assert Path(result.summary_path).exists()
