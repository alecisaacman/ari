from __future__ import annotations

import json
from pathlib import Path

from ari_core.modules.coordination.db import list_coordination_entities
from ari_core.modules.execution import (
    ExecutionGoal,
    ModelPlanner,
    build_repo_context,
    run_execution_goal,
)
from ari_core.modules.execution.inspection import get_execution_run, list_execution_runs


def test_execution_controller_completes_bounded_write_and_persists_trace(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_execution_goal(
        ExecutionGoal(objective="write file notes/proof.txt with phase one ready", max_cycles=2),
        execution_root=root,
        db_path=db_path,
    )

    assert result.status == "completed"
    assert result.cycles_run == 1
    assert (root / "notes" / "proof.txt").read_text(encoding="utf-8") == "phase one ready"
    assert result.decisions[0].action is not None
    assert result.decisions[0].action.action_type == "write_file"
    assert result.results[0]["verified"] is True
    assert result.planner_config["selected"] == "rule_based"

    rows = list_coordination_entities("runtime_execution_run", limit=10, db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert json.loads(rows[0]["decisions_json"])[0]["status"] == "act"
    assert json.loads(rows[0]["results_json"])[0]["verified"] is True


def test_execution_controller_executes_multi_action_plan_with_verification(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_execution_goal(
        "write files alpha.txt with alpha ready; nested/beta.txt with beta ready",
        execution_root=root,
        db_path=db_path,
    )

    assert result.status == "completed"
    assert (root / "alpha.txt").read_text(encoding="utf-8") == "alpha ready"
    assert (root / "nested" / "beta.txt").read_text(encoding="utf-8") == "beta ready"
    assert result.decisions[0].plan is not None
    assert len(result.decisions[0].plan.actions) == 2
    assert len(result.results[0]["action_results"]) == 2
    assert len(result.results[0]["verification_results"]) == 2
    assert result.results[0]["verified"] is True

    rows = list_coordination_entities("runtime_execution_run", limit=10, db_path=db_path)
    persisted_decision = json.loads(rows[0]["decisions_json"])[0]
    assert persisted_decision["plan"]["actions"][1]["payload"]["path"] == "nested/beta.txt"


def test_model_planner_valid_json_becomes_worker_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")

    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.91,
                "reason": "Update the existing README.",
                "actions": [
                    {
                        "type": "write_file",
                        "path": "README.md",
                        "content": "new\n",
                    }
                ],
                "verification": [
                    {
                        "type": "file_content",
                        "target": "README.md",
                        "expected": "new\n",
                    }
                ],
            }
        )
    )

    result = run_execution_goal(
        "Improve the README",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "completed"
    assert (root / "README.md").read_text(encoding="utf-8") == "new\n"
    assert result.decisions[0].planner_name == "model"
    assert result.decisions[0].plan is not None
    assert planner.last_prompt_payload is not None
    assert "tools" in planner.last_prompt_payload
    assert "write_file" in planner.last_prompt_payload["allowed_actions"]


def test_model_planner_invalid_json_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")
    planner = ModelPlanner(lambda payload: "{not-json")

    result = run_execution_goal(
        "Improve the README",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "rejected"
    assert "invalid JSON" in result.reason
    assert (root / "README.md").read_text(encoding="utf-8") == "old\n"
    stored = get_execution_run(result.id, db_path=db_path)
    assert stored is not None
    assert "invalid JSON" in stored["results"][0]["error"]


def test_model_planner_rejects_invented_file(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")
    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.9,
                "actions": [
                    {
                        "type": "write_file",
                        "path": "invented.md",
                        "content": "new\n",
                    }
                ],
            }
        )
    )

    result = run_execution_goal(
        "Improve docs",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "rejected"
    assert "outside RepoContext" in result.reason
    assert not (root / "invented.md").exists()


def test_model_planner_rejects_unsafe_command(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")
    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.9,
                "actions": [
                    {
                        "type": "run_command",
                        "command": ["rm", "-rf", "."],
                    }
                ],
            }
        )
    )

    result = run_execution_goal("Clean repo", execution_root=root, db_path=db_path, planner=planner)

    assert result.status == "rejected"
    assert "allowlisted" in result.reason
    assert (root / "README.md").exists()


def test_model_planner_rejects_low_confidence_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")
    planner = ModelPlanner(
        lambda payload: json.dumps(
            {
                "confidence": 0.2,
                "actions": [
                    {
                        "type": "write_file",
                        "path": "README.md",
                        "content": "new\n",
                    }
                ],
            }
        )
    )

    result = run_execution_goal(
        "Improve docs",
        execution_root=root,
        db_path=db_path,
        planner=planner,
    )

    assert result.status == "rejected"
    assert "below threshold" in result.reason
    assert (root / "README.md").read_text(encoding="utf-8") == "old\n"


def test_planner_config_defaults_to_rule_based(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_execution_goal("inspect repo status", execution_root=root, db_path=db_path)

    assert result.planner_config == {
        "requested": "rule_based",
        "selected": "rule_based",
        "fallback_reason": None,
    }
    assert result.decisions[0].planner_name == "rule_based"


def test_model_planner_mode_without_completion_falls_back_visibly(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_execution_goal(
        "inspect repo status",
        execution_root=root,
        db_path=db_path,
        planner_mode="model",
    )

    assert result.status == "completed"
    assert result.planner_config["requested"] == "model"
    assert result.planner_config["selected"] == "rule_based"
    assert "no completion function" in str(result.planner_config["fallback_reason"])
    assert result.results[0]["planner_config"] == result.planner_config


def test_execution_run_inspection_decodes_persisted_trace(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_execution_goal(
        "write file proof.txt with inspectable",
        execution_root=root,
        db_path=db_path,
    )

    runs = list_execution_runs(limit=5, db_path=db_path)
    stored = get_execution_run(result.id, db_path=db_path)
    assert runs[0]["id"] == result.id
    assert stored is not None
    assert stored["status"] == "completed"
    assert stored["results"][0]["verified"] is True
    assert stored["planner_config"]["selected"] == "rule_based"


def test_model_planner_verification_failure_replans_with_failure_context(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def complete(payload: dict[str, object]) -> str:
        calls.append(payload)
        if len(calls) == 1:
            content = "wrong\n"
        else:
            content = "right\n"
        return json.dumps(
            {
                "confidence": 0.9,
                "actions": [
                    {
                        "type": "write_file",
                        "path": "README.md",
                        "content": content,
                    }
                ],
                "verification": [
                    {
                        "type": "file_content",
                        "target": "README.md",
                        "expected": "right\n",
                    }
                ],
            }
        )

    result = run_execution_goal(
        ExecutionGoal(objective="Improve the README", max_cycles=2),
        execution_root=root,
        db_path=db_path,
        planner=ModelPlanner(complete),
    )

    assert result.status == "completed"
    assert len(calls) == 2
    assert calls[0]["failure_context"] is None
    assert calls[1]["failure_context"] is not None
    assert (root / "README.md").read_text(encoding="utf-8") == "right\n"


def test_model_planner_stops_at_max_cycles(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("old\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def complete(payload: dict[str, object]) -> str:
        calls.append(payload)
        return json.dumps(
            {
                "confidence": 0.9,
                "actions": [
                    {
                        "type": "write_file",
                        "path": "README.md",
                        "content": "still wrong\n",
                    }
                ],
                "verification": [
                    {
                        "type": "file_content",
                        "target": "README.md",
                        "expected": "right\n",
                    }
                ],
            }
        )

    result = run_execution_goal(
        ExecutionGoal(objective="Improve the README", max_cycles=2),
        execution_root=root,
        db_path=db_path,
        planner=ModelPlanner(complete),
    )

    assert result.status == "failed"
    assert result.cycles_run == 2
    assert len(calls) == 2
    assert calls[1]["failure_context"] is not None


def test_execution_controller_rejects_plan_exceeding_action_bound(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    objective = (
        "write files a.txt with a; b.txt with b; c.txt with c; "
        "d.txt with d; e.txt with e; f.txt with f"
    )

    result = run_execution_goal(objective, execution_root=root, db_path=db_path)

    assert result.status == "rejected"
    assert "bounded to 5 actions" in result.reason
    assert not (root / "a.txt").exists()


def test_execution_controller_rejects_unsafe_command_without_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()

    result = run_execution_goal("run rm -rf .", execution_root=root, db_path=db_path)

    assert result.status == "rejected"
    assert result.cycles_run == 1
    assert result.results[0]["success"] is False
    assert "allowlisted" in result.results[0]["error"]


def test_execution_controller_rejects_allowlisted_command_path_escape(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")

    result = run_execution_goal("run cat ../outside.txt", execution_root=root, db_path=db_path)

    assert result.status == "rejected"
    assert result.results[0]["success"] is False
    assert "escapes execution root" in result.results[0]["error"]


def test_execution_controller_completes_read_only_repo_context_loop(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")

    context = build_repo_context(root)
    result = run_execution_goal("inspect repo status", execution_root=root, db_path=db_path)

    assert context.repo_root == str(root.resolve())
    assert "README.md" in context.files_sample
    assert result.status == "completed"
    assert result.results[0]["success"] is True
    assert result.results[0]["verified"] is True
