from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "ari_core" or module_name.startswith("ari_core.") or module_name == "ari_api" or module_name.startswith("ari_api."):
            sys.modules.pop(module_name, None)


def test_canonical_api_exposes_core_memory_tasks_notes_coordination_and_awareness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
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
                    "completion_criteria": "ari-core, ari-api, and ari-hub all run from canonical services.",
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

        stored_awareness = client.post("/awareness/store", json={"payload": awareness.json()})
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
        assert classify.json()["classification"] in {"auto_pass", "auto_summarize", "escalate_to_alec"}
