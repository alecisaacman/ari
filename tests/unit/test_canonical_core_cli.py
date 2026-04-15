from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "ari_core" or module_name.startswith("ari_core."):
            sys.modules.pop(module_name, None)


def test_canonical_core_cli_persists_notes_tasks_memory_and_project_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"

    memory_output = StringIO()
    with redirect_stdout(memory_output):
        exit_code = main(
            [
                "api",
                "memory",
                "remember",
                "--type",
                "priority",
                "--title",
                "Canonical focus",
                "--body",
                "Converge ARI into the canonical repo.",
                "--tags-json",
                json.dumps(["canon", "integration"]),
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_memory = json.loads(memory_output.getvalue())
    assert saved_memory["type"] == "priority"
    assert saved_memory["title"] == "Canonical focus"

    task_output = StringIO()
    with redirect_stdout(task_output):
        exit_code = main(
            [
                "api",
                "tasks",
                "create",
                "--title",
                "Finish canonical repo convergence",
                "--notes",
                "Route the hub through the canonical brain seams.",
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_task = json.loads(task_output.getvalue())
    assert saved_task["title"] == "Finish canonical repo convergence"
    assert saved_task["status"] == "open"

    note_output = StringIO()
    with redirect_stdout(note_output):
        exit_code = main(
            [
                "api",
                "notes",
                "save",
                "--title",
                "Canonical integration note",
                "--body",
                "ACE now points at ari-core inside services/ari-core.",
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_note = json.loads(note_output.getvalue())
    assert saved_note["title"] == "Canonical integration note"

    project_payload = {
        "id": "project-canon",
        "title": "Canonical repo convergence",
        "goal": "Make ARI the single brain in the canonical repository.",
        "completion_criteria": "Core, API, and hub all resolve through canonical services.",
        "status": "active",
        "source": "integration",
        "created_at": "2026-04-15T01:30:00Z",
        "updated_at": "2026-04-15T01:30:00Z",
    }
    project_output = StringIO()
    with redirect_stdout(project_output):
        exit_code = main(
            [
                "api",
                "coordination",
                "put",
                "--entity",
                "project",
                "--payload-json",
                json.dumps(project_payload),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_project = json.loads(project_output.getvalue())
    assert saved_project["id"] == "project-canon"
    assert saved_project["title"] == "Canonical repo convergence"

    awareness_output = StringIO()
    with redirect_stdout(awareness_output):
        exit_code = main(
            [
                "api",
                "policy",
                "awareness",
                "derive",
                "--payload-json",
                json.dumps(
                    {
                        "pendingApprovals": [],
                        "recentIntent": ["Integrate the real ARI system into the canonical repo."],
                        "recentDecisions": [],
                    }
                ),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    awareness = json.loads(awareness_output.getvalue())
    assert awareness["summary"]
    assert awareness["currentFocus"]
    assert db_path.exists()
