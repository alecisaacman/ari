from __future__ import annotations

import json
import shlex
import sys
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if (
            module_name == "ari_core"
            or module_name.startswith("ari_core.")
            or module_name == "ari_api"
            or module_name.startswith("ari_api.")
        ):
            sys.modules.pop(module_name, None)


def test_canonical_api_exposes_core_memory_tasks_notes_coordination_and_awareness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(tmp_path / "execution-root"))
    execution_root = tmp_path / "execution-root"
    execution_root.mkdir(parents=True, exist_ok=True)
    (execution_root / "operator_target.py").write_text(
        "status = 'pending'\n", encoding="utf-8"
    )
    (execution_root / "operator_check_test.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                "",
                "def test_operator_target_is_ready():",
                "    assert 'ready' in Path('operator_target.py').read_text()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _purge_modules()

    from ari_api import create_app
    from ari_core.core.paths import DB_PATH
    from ari_core.modules.execution import (
        ModelPlanner,
        get_coding_loop_retry_approval,
        run_one_step_coding_loop,
        store_coding_loop_retry_approval,
    )

    app = create_app()
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "ari-api"

        memory = client.post(
            "/memory",
            json={
                "type": "goal",
                "title": "Canonical convergence",
                "content": "Replace placeholder services with the real ARI system.",
                "tags": ["canon", "integration"],
            },
        )
        assert memory.status_code == 200
        assert memory.json()["type"] == "goal"

        task = client.post(
            "/tasks",
            json={
                "title": "Wire ari-hub to canonical ari-core",
                "notes": "Use the new services/ari-core package target.",
            },
        )
        assert task.status_code == 200
        assert task.json()["status"] == "open"

        note = client.post(
            "/notes",
            json={
                "title": "Integration proof",
                "content": "The canonical repo now holds the real ACE and ARI code.",
            },
        )
        assert note.status_code == 200
        assert note.json()["title"] == "Integration proof"

        project = client.put(
            "/coordination/project",
            json={
                "payload": {
                    "id": "proj-1",
                    "title": "Canonical repo integration",
                    "goal": "Collapse the imported prototypes into the real service structure.",
                    "completion_criteria": (
                        "ari-core, ari-api, and ari-hub all run from canonical services."
                    ),
                    "status": "active",
                    "source": "integration",
                    "created_at": "2026-04-15T02:00:00Z",
                    "updated_at": "2026-04-15T02:00:00Z",
                }
            },
        )
        assert project.status_code == 200
        assert project.json()["id"] == "proj-1"

        coordination = client.get("/coordination/project")
        assert coordination.status_code == 200
        assert coordination.json()["records"][0]["id"] == "proj-1"

        awareness = client.post(
            "/awareness/derive",
            json={
                "payload": {
                    "pendingApprovals": [],
                    "recentIntent": ["Finish converging ARI into the canonical repository."],
                    "recentDecisions": [],
                }
            },
        )
        assert awareness.status_code == 200
        assert awareness.json()["summary"]
        assert awareness.json()["currentFocus"]

        stored_awareness = client.post(
            "/awareness/store",
            json={"payload": awareness.json()},
        )
        assert stored_awareness.status_code == 200
        assert stored_awareness.json()["snapshot"]["summary"] == awareness.json()["summary"]

        latest_awareness = client.get("/awareness/latest")
        assert latest_awareness.status_code == 200
        assert latest_awareness.json()["snapshot"]["summary"] == awareness.json()["summary"]

        classify = client.post(
            "/policy/orchestration/classify",
            json={
                "rawOutput": "Implemented the ari-api routes and verified the hub still loads.",
                "currentPriority": "canonical repo convergence",
                "latestDecision": "move the real runtime inward",
            },
        )
        assert classify.status_code == 200
        assert classify.json()["classification"] in {
            "auto_pass",
            "auto_summarize",
            "escalate_to_alec",
        }

        action = client.post(
            "/execution/actions",
            json={
                "title": "Promote operator target",
                "summary": "Patch a file and verify it.",
                "operations": [
                        {
                            "type": "patch",
                            "path": "operator_target.py",
                            "find": "pending",
                            "replace": "ready",
                        }
                    ],
                    "verifyCommand": (
                        f"{shlex.quote(sys.executable)} "
                        "-m pytest operator_check_test.py -q"
                    ),
                    "workingDirectory": ".",
                    "approvalRequired": False,
                },
        )
        assert action.status_code == 200
        action_id = action.json()["action"]["id"]

        approved = client.post(f"/execution/actions/{action_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["action"]["status"] == "approved"

        ran = client.post(f"/execution/actions/{action_id}/run")
        assert ran.status_code == 200, ran.text
        assert ran.json()["action"]["status"] == "verified"
        assert ran.json()["command_run"]["success"] is True
        assert ran.json()["mutations"][0]["path"] == "operator_target.py"

        snapshot = client.get("/execution/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.json()["current_action"]["id"] == action_id
        assert snapshot.json()["last_command_run"]["success"] is True

        goal = client.post(
            "/execution/goals",
            json={
                "goal": "write file goal-proof.txt with canonical goal execution",
                "maxCycles": 1,
            },
        )
        assert goal.status_code == 200
        assert goal.json()["status"] == "completed"
        assert goal.json()["decisions"][0]["planner_name"] == "rule_based"
        assert (execution_root / "goal-proof.txt").read_text(
            encoding="utf-8"
        ) == "canonical goal execution"

        plan = client.post(
            "/execution/plans",
            json={
                "goal": "write file preview-proof.txt with not yet",
                "maxCycles": 1,
            },
        )
        assert plan.status_code == 200
        assert plan.json()["status"] == "planned"
        assert plan.json()["decision"]["planner_name"] == "rule_based"
        assert not (execution_root / "preview-proof.txt").exists()

        plans = client.get("/execution/plans")
        assert plans.status_code == 200
        assert plans.json()["plans"][0]["id"] == plan.json()["id"]

        shown_plan = client.get(f"/execution/plans/{plan.json()['id']}")
        assert shown_plan.status_code == 200
        assert shown_plan.json()["plan"]["status"] == "planned"

        coding_loop = client.post(
            "/execution/coding-loop",
            json={
                "goal": "write file loop-api-proof.txt with inspected through api",
                "executionRoot": str(execution_root),
            },
        )
        assert coding_loop.status_code == 200
        coding_loop_payload = coding_loop.json()["coding_loop"]
        assert coding_loop_payload["status"] == "success"
        assert coding_loop_payload["reason"]
        assert coding_loop_payload["preview_id"]
        assert coding_loop_payload["execution_run_id"]
        assert coding_loop_payload["execution_occurred"] is True
        assert coding_loop_payload["approval_required_reason"] is None
        assert coding_loop_payload["retry_proposal"] is None
        assert coding_loop_payload["retry_approval"] is None
        assert coding_loop_payload["retry_approval_status"] is None
        assert (execution_root / "loop-api-proof.txt").read_text(
            encoding="utf-8"
        ) == "inspected through api"

        coding_loops = client.get("/execution/coding-loop/results")
        assert coding_loops.status_code == 200
        assert coding_loops.json()["coding_loops"][0]["id"] == coding_loop_payload["id"]

        shown_coding_loop = client.get(
            f"/execution/coding-loop/results/{coding_loop_payload['id']}"
        )
        assert shown_coding_loop.status_code == 200
        assert shown_coding_loop.json()["coding_loop"]["status"] == "success"
        assert shown_coding_loop.json()["coding_loop"]["execution_run_id"] == (
            coding_loop_payload["execution_run_id"]
        )

        unsafe_loop = client.post(
            "/execution/coding-loop",
            json={
                "goal": "run rm -rf .",
                "executionRoot": str(execution_root),
            },
        )
        assert unsafe_loop.status_code == 200
        unsafe_loop_payload = unsafe_loop.json()["coding_loop"]
        assert unsafe_loop_payload["status"] == "unsafe"
        assert unsafe_loop_payload["execution_run_id"] is None
        assert unsafe_loop_payload["execution_occurred"] is False

        ask_user_loop = client.post(
            "/execution/coding-loop",
            json={
                "goal": "Invent a broad product strategy",
                "executionRoot": str(execution_root),
            },
        )
        assert ask_user_loop.status_code == 200
        ask_user_loop_payload = ask_user_loop.json()["coding_loop"]
        assert ask_user_loop_payload["status"] == "ask_user"
        assert ask_user_loop_payload["execution_run_id"] is None
        assert ask_user_loop_payload["execution_occurred"] is False

        retry_result = run_one_step_coding_loop(
            "Create a proof file",
            execution_root=execution_root,
            db_path=DB_PATH,
            planner=ModelPlanner(
                lambda payload: json.dumps(
                    {
                        "confidence": 0.9,
                        "reason": "Write content that will fail explicit verification.",
                        "actions": [
                            {
                                "type": "write_file",
                                "path": "loop-api-proof.txt",
                                "content": "wrong",
                            }
                        ],
                        "verification": [
                            {
                                "type": "file_content",
                                "target": "loop-api-proof.txt",
                                "expected": "inspected through api",
                            }
                        ],
                    }
                )
            ),
        )
        assert retry_result.retry_approval is not None
        retry_approval_id = retry_result.retry_approval.approval_id

        retry_approvals = client.get("/execution/coding-loop/retry-approvals")
        assert retry_approvals.status_code == 200
        assert retry_approvals.json()["retry_approvals"][0]["approval_id"] == retry_approval_id
        assert retry_approvals.json()["retry_approvals"][0]["approval_status"] == "pending"

        retry_approval = client.get(
            f"/execution/coding-loop/retry-approvals/{retry_approval_id}"
        )
        assert retry_approval.status_code == 200
        assert (
            retry_approval.json()["retry_approval"]["source_execution_run_id"]
            == retry_result.execution_run_id
        )
        assert (
            retry_approval.json()["retry_approval"]["proposed_retry_goal"]
            == "write file loop-api-proof.txt with inspected through api"
        )

        approved_retry = client.post(
            f"/execution/coding-loop/retry-approvals/{retry_approval_id}/approve",
            json={"approvedBy": "alec"},
        )
        assert approved_retry.status_code == 200
        assert approved_retry.json()["retry_approval"]["approval_status"] == "approved"
        assert approved_retry.json()["retry_approval"]["approval"]["approved_by"] == "alec"
        assert (execution_root / "loop-api-proof.txt").read_text(encoding="utf-8") == "wrong"

        executed_retry = client.post(
            f"/execution/coding-loop/retry-approvals/{retry_approval_id}/execute"
        )
        assert executed_retry.status_code == 200
        assert (
            executed_retry.json()["retry_approval"]["retry_execution_status"]
            == "completed"
        )
        assert executed_retry.json()["execution_run"]["status"] == "completed"
        assert (execution_root / "loop-api-proof.txt").read_text(
            encoding="utf-8"
        ) == "inspected through api"

        retry_review = client.get(
            f"/execution/coding-loop/retry-approvals/{retry_approval_id}/review"
        )
        assert retry_review.status_code == 200
        assert retry_review.json()["review"]["status"] == "stop"
        assert retry_review.json()["review"]["retry_execution_status"] == "completed"
        assert retry_review.json()["review"]["approval_required"] is False
        assert retry_review.json()["continuation"]["eligible"] is False
        assert retry_review.json()["continuation"]["status"] == "stop"

        (execution_root / "loop-api-second-proof.txt").write_text(
            "old",
            encoding="utf-8",
        )
        second_retry_result = run_one_step_coding_loop(
            "Create a second proof file",
            execution_root=execution_root,
            db_path=DB_PATH,
            planner=ModelPlanner(
                lambda payload: json.dumps(
                    {
                        "confidence": 0.9,
                        "reason": "Write content that will fail explicit verification.",
                        "actions": [
                            {
                                "type": "write_file",
                                "path": "loop-api-second-proof.txt",
                                "content": "wrong",
                            }
                        ],
                        "verification": [
                            {
                                "type": "file_content",
                                "target": "loop-api-second-proof.txt",
                                "expected": "inspected twice through api",
                            }
                        ],
                    }
                )
            ),
        )
        assert second_retry_result.retry_approval is not None
        second_approval = get_coding_loop_retry_approval(
            second_retry_result.retry_approval.approval_id,
            db_path=DB_PATH,
        )
        assert second_approval is not None
        store_coding_loop_retry_approval(
            replace(
                second_approval,
                retry_execution_run_id=second_retry_result.execution_run_id,
                retry_execution_status="exhausted",
                retry_execution_reason=(
                    "Retryable execution failed until max_cycles was exhausted."
                ),
                executed_at="2026-05-04T14:10:00Z",
            ),
            db_path=DB_PATH,
        )
        proposed_next = client.post(
            "/execution/coding-loop/retry-approvals/"
            f"{second_retry_result.retry_approval.approval_id}/propose-next"
        )
        assert proposed_next.status_code == 200
        assert proposed_next.json()["retry_approval"]["approval_status"] == "pending"
        assert (
            proposed_next.json()["retry_approval"]["prior_retry_approval_id"]
            == second_retry_result.retry_approval.approval_id
        )
        assert proposed_next.json()["retry_approval"][
            "prior_retry_execution_run_id"
        ] == second_retry_result.execution_run_id

        shown_second_result = client.get(
            f"/execution/coding-loop/results/{second_retry_result.id}"
        )
        assert shown_second_result.status_code == 200
        assert shown_second_result.json()["coding_loop"]["next_retry_approval_id"] == (
            proposed_next.json()["retry_approval"]["approval_id"]
        )
        assert shown_second_result.json()["coding_loop"]["post_run_review"]["status"] == (
            "propose_retry"
        )

        runs = client.get("/execution/runs")
        assert runs.status_code == 200
        assert any(
            run["id"] == coding_loop_payload["execution_run_id"]
            for run in runs.json()["runs"]
        )

        run = client.get(f"/execution/runs/{goal.json()['id']}")
        assert run.status_code == 200
        assert run.json()["run"]["status"] == "completed"
        assert run.json()["run"]["results"][0]["verified"] is True

        tools = client.get("/execution/tools")
        assert tools.status_code == 200
        assert "run_command" in tools.json()["allowed_actions"]
        assert tools.json()["tools"][0]["action_type"] == "read_file"

        context = client.get("/execution/context")
        assert context.status_code == 200
        assert context.json()["context"]["repo_root"] == str(execution_root.resolve())
        assert "operator_target.py" in context.json()["context"]["files_sample"]
        assert context.json()["context"]["language_summary"]["python"] >= 1

        fallback_goal = client.post(
            "/execution/goals",
            json={
                "goal": "compose a broad autonomous rewrite",
                "maxCycles": 1,
                "planner": "model",
            },
        )
        assert fallback_goal.status_code == 200
        assert fallback_goal.json()["status"] == "rejected"
        assert fallback_goal.json()["planner_config"]["requested"] == "model"
        assert "no completion function" in fallback_goal.json()["planner_config"]["fallback_reason"]

        fallback_run = client.get(f"/execution/runs/{fallback_goal.json()['id']}")
        assert fallback_run.status_code == 200
        assert fallback_run.json()["run"]["results"][0]["error"]
