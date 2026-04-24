from __future__ import annotations

import sys
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
    (execution_root / "operator-target.js").write_text(
        "export const status = 'pending';\n", encoding="utf-8"
    )
    (execution_root / "operator-check.test.mjs").write_text(
        "\n".join(
            [
                "import assert from 'node:assert/strict';",
                "import fs from 'node:fs';",
                "import test from 'node:test';",
                "",
                "test('operator target is ready', () => {",
                "  const source = fs.readFileSync(",
                "    new URL('./operator-target.js', import.meta.url),",
                "    'utf8',",
                "  );",
                "  assert.match(source, /ready/);",
                "});",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _purge_modules()

    from ari_api import create_app

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
                        "path": "operator-target.js",
                        "find": "pending",
                        "replace": "ready",
                    }
                ],
                "verifyCommand": "node --test operator-check.test.mjs",
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
        assert ran.status_code == 200
        assert ran.json()["action"]["status"] == "verified"
        assert ran.json()["command_run"]["success"] is True
        assert ran.json()["mutations"][0]["path"] == "operator-target.js"

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

        runs = client.get("/execution/runs")
        assert runs.status_code == 200
        assert runs.json()["runs"][0]["id"] == goal.json()["id"]

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
        assert "operator-target.js" in context.json()["context"]["files_sample"]
        assert context.json()["context"]["language_summary"]["javascript"] >= 1

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
