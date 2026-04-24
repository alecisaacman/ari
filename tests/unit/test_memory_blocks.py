from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from io import StringIO
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


def test_memory_block_persistence_and_search(tmp_path: Path) -> None:
    from ari_core.modules.memory import (
        create_memory_block,
        get_memory_block,
        list_memory_blocks,
        memory_block_to_payload,
        search_memory_blocks,
    )

    db_path = tmp_path / "state" / "networking.db"
    block = create_memory_block(
        layer="session",
        kind="execution_reflection",
        title="Execution core hardening",
        body="Planner fallback is visible in execution results.",
        source="execution-run-1",
        importance=4,
        confidence=0.91,
        tags=["execution", "phase-1"],
        subject_ids=["execution-run-1"],
        evidence=[{"type": "test", "id": "test_execution_controller"}],
        db_path=db_path,
    )

    payload = memory_block_to_payload(block)
    listed = [memory_block_to_payload(row) for row in list_memory_blocks(db_path=db_path)]
    found = [
        memory_block_to_payload(row) for row in search_memory_blocks("fallback", db_path=db_path)
    ]
    loaded = get_memory_block(payload["id"], db_path=db_path)

    assert payload["layer"] == "session"
    assert payload["importance"] == 4
    assert payload["tags"] == ["execution", "phase-1"]
    assert listed[0]["id"] == payload["id"]
    assert found[0]["id"] == payload["id"]
    assert loaded is not None


def test_memory_block_cli_create_list_get(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"
    create_output = StringIO()
    with redirect_stdout(create_output):
        exit_code = main(
            [
                "api",
                "memory",
                "blocks",
                "create",
                "--layer",
                "long_term",
                "--kind",
                "architecture_principle",
                "--title",
                "Single brain",
                "--body",
                "ARI owns decision logic; ACE stays interface-only.",
                "--source",
                "phase-2-test",
                "--tags-json",
                json.dumps(["architecture"]),
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    created = json.loads(create_output.getvalue())
    assert created["layer"] == "long_term"

    list_output = StringIO()
    with redirect_stdout(list_output):
        exit_code = main(
            ["api", "memory", "blocks", "list", "--layer", "long_term", "--json"],
            db_path=db_path,
        )
    assert exit_code == 0
    assert json.loads(list_output.getvalue())["blocks"][0]["id"] == created["id"]

    get_output = StringIO()
    with redirect_stdout(get_output):
        exit_code = main(
            ["api", "memory", "blocks", "get", "--id", created["id"], "--json"],
            db_path=db_path,
        )
    assert exit_code == 0
    assert json.loads(get_output.getvalue())["title"] == "Single brain"


def test_memory_block_api_create_list_get(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    _purge_modules()

    from ari_api import create_app

    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/memory/blocks",
            json={
                "layer": "self_model",
                "kind": "behavior_consistency",
                "title": "Fail closed",
                "body": "ARI rejects unsafe planner outputs instead of improvising.",
                "source": "phase-2-test",
                "importance": 5,
                "confidence": 0.95,
                "tags": ["safety"],
                "subjectIds": ["execution-core"],
                "evidence": [{"type": "test", "id": "model_planner_rejects_unsafe_command"}],
            },
        )
        assert created.status_code == 200
        block_id = created.json()["id"]

        listed = client.get("/memory/blocks", params={"layer": "self_model"})
        assert listed.status_code == 200
        assert listed.json()["blocks"][0]["id"] == block_id

        loaded = client.get(f"/memory/blocks/{block_id}")
        assert loaded.status_code == 200
        assert loaded.json()["importance"] == 5


def test_capture_execution_run_memory_is_idempotent(tmp_path: Path) -> None:
    from ari_core.modules.execution import ExecutionGoal, run_execution_goal
    from ari_core.modules.memory.capture import capture_execution_run_memory
    from ari_core.modules.memory.db import list_memory_blocks, memory_block_to_payload

    db_path = tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir()
    run = run_execution_goal(
        ExecutionGoal(objective="write file proof.txt with remembered", max_cycles=1),
        execution_root=root,
        db_path=db_path,
    )

    first = capture_execution_run_memory(run.id, db_path=db_path)
    second = capture_execution_run_memory(run.id, db_path=db_path)
    blocks = [
        memory_block_to_payload(row) for row in list_memory_blocks(layer="session", db_path=db_path)
    ]

    assert first["id"] == second["id"]
    assert first["kind"] == "execution_run_summary"
    assert first["source"] == run.id
    assert "Objective: write file proof.txt with remembered" in str(first["body"])
    assert first["subject_ids"][0] == run.id
    assert len(blocks) == 1


def test_memory_capture_execution_cli(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"
    execution_root = tmp_path / "repo"
    execution_root.mkdir()
    goal_output = StringIO()
    with redirect_stdout(goal_output):
        assert (
            main(
                [
                    "api",
                    "execution",
                    "goal",
                    "--goal",
                    "write file cli-proof.txt with captured",
                    "--execution-root",
                    str(execution_root),
                ],
                db_path=db_path,
            )
            == 0
        )
    run_id = json.loads(goal_output.getvalue())["id"]

    capture_output = StringIO()
    with redirect_stdout(capture_output):
        exit_code = main(
            ["api", "memory", "capture", "execution", "--id", run_id, "--json"],
            db_path=db_path,
        )

    assert exit_code == 0
    block = json.loads(capture_output.getvalue())["block"]
    assert block["source"] == run_id
    assert block["layer"] == "session"
    assert block["tags"][0] == "execution"


def test_memory_capture_execution_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(tmp_path / "repo"))
    (tmp_path / "repo").mkdir()
    _purge_modules()

    from ari_api import create_app

    app = create_app()
    with TestClient(app) as client:
        run = client.post(
            "/execution/goals",
            json={"goal": "write file api-proof.txt with captured", "maxCycles": 1},
        )
        assert run.status_code == 200
        run_id = run.json()["id"]

        captured = client.post("/memory/capture/execution", json={"runId": run_id})
        assert captured.status_code == 200
        assert captured.json()["block"]["source"] == run_id

        listed = client.get("/memory/blocks", params={"query": "api-proof"})
        assert listed.status_code == 200
        assert listed.json()["blocks"][0]["source"] == run_id
