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
