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


def _executed_retry_approval(tmp_path: Path, *, db_path: Path | None = None):
    from ari_core.modules.execution import (
        ModelPlanner,
        approve_stored_coding_loop_retry_approval,
        execute_approved_coding_loop_retry_approval,
        run_one_step_coding_loop,
    )

    state_path = db_path or tmp_path / "state" / "networking.db"
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "proof.txt").write_text("old\n", encoding="utf-8")
    result = run_one_step_coding_loop(
        "Create a proof file",
        execution_root=root,
        db_path=state_path,
        planner=ModelPlanner(
            lambda payload: json.dumps(
                {
                    "confidence": 0.9,
                    "reason": "Write content that will fail explicit verification.",
                    "actions": [
                        {
                            "type": "write_file",
                            "path": "proof.txt",
                            "content": "wrong",
                        }
                    ],
                    "verification": [
                        {
                            "type": "file_content",
                            "target": "proof.txt",
                            "expected": "right",
                        }
                    ],
                }
            )
        ),
    )
    assert result.retry_approval is not None
    approved = approve_stored_coding_loop_retry_approval(
        result.retry_approval.approval_id,
        approved_by="alec",
        db_path=state_path,
    )
    executed, execution_run = execute_approved_coding_loop_retry_approval(
        approved.approval_id,
        db_path=state_path,
    )
    assert execution_run["status"] == "completed"
    return executed, execution_run, root, state_path


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


def test_self_model_memory_is_idempotent(tmp_path: Path) -> None:
    from ari_core.modules.memory.self_model import (
        ensure_self_model_memory,
        get_self_model_memory,
    )

    db_path = tmp_path / "state" / "networking.db"

    first = ensure_self_model_memory(db_path=db_path)
    second = ensure_self_model_memory(db_path=db_path)
    loaded = get_self_model_memory(db_path=db_path)

    assert [block["id"] for block in first] == [block["id"] for block in second]
    assert len(loaded) == 3
    assert any(block["title"] == "ARI is the single brain" for block in loaded)
    assert all(block["layer"] == "self_model" for block in loaded)


def test_memory_context_ranks_and_filters_blocks(tmp_path: Path) -> None:
    from ari_core.modules.memory import build_memory_context, create_memory_block

    db_path = tmp_path / "state" / "networking.db"
    create_memory_block(
        layer="long_term",
        kind="architecture",
        title="Low importance context",
        body="ARI remembers broad architecture context.",
        source="test",
        importance=2,
        tags=["architecture"],
        db_path=db_path,
    )
    create_memory_block(
        layer="self_model",
        kind="authority",
        title="High importance context",
        body="ARI is the single brain for architecture decisions.",
        source="test",
        importance=5,
        tags=["architecture"],
        db_path=db_path,
    )

    context = build_memory_context(
        "architecture",
        layers=["self_model", "long_term"],
        db_path=db_path,
    )

    assert context["blocks"][0]["title"] == "High importance context"
    assert context["layers"] == ["self_model", "long_term"]
    assert "Loaded 2 memory block" in str(context["summary"])


def test_self_model_cli_and_api(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_api import create_app
    from ari_core.ari import main

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"
    ensure_output = StringIO()
    with redirect_stdout(ensure_output):
        exit_code = main(
            ["api", "memory", "self-model", "ensure", "--json"],
            db_path=db_path,
        )
    assert exit_code == 0
    ensured = json.loads(ensure_output.getvalue())
    assert len(ensured["blocks"]) == 3

    show_output = StringIO()
    with redirect_stdout(show_output):
        exit_code = main(
            ["api", "memory", "self-model", "show", "--json"],
            db_path=db_path,
        )
    assert exit_code == 0
    assert len(json.loads(show_output.getvalue())["blocks"]) == 3

    app = create_app()
    with TestClient(app) as client:
        api_ensure = client.post("/memory/self-model/ensure")
        assert api_ensure.status_code == 200
        assert len(api_ensure.json()["blocks"]) == 3

        api_show = client.get("/memory/self-model")
        assert api_show.status_code == 200
        assert any(
            block["title"] == "ARI is the single brain" for block in api_show.json()["blocks"]
        )

        context = client.get(
            "/memory/context",
            params={"query": "single brain", "layers": "self_model"},
        )
        assert context.status_code == 200
        assert context.json()["blocks"][0]["layer"] == "self_model"

    context_output = StringIO()
    with redirect_stdout(context_output):
        exit_code = main(
            [
                "api",
                "memory",
                "context",
                "--query",
                "single brain",
                "--layer",
                "self_model",
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    assert json.loads(context_output.getvalue())["blocks"][0]["layer"] == "self_model"


def test_capture_execution_run_memory_is_idempotent(tmp_path: Path) -> None:
    from ari_core.modules.execution import ExecutionGoal, run_execution_goal
    from ari_core.modules.memory.capture import capture_execution_run_memory
    from ari_core.modules.memory.db import list_memory_blocks, memory_block_to_payload
    from ari_core.modules.memory.explain import explain_execution_run

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

    explanation = explain_execution_run(run.id, db_path=db_path)
    assert explanation["status"] == "completed"
    assert explanation["memory_blocks"][0]["id"] == first["id"]
    assert any("Final status reason" in reason for reason in explanation["why"])


def test_capture_coding_loop_retry_approval_memory_is_explainable(
    tmp_path: Path,
) -> None:
    from ari_core.modules.memory.capture import (
        capture_coding_loop_retry_approval_memory,
    )
    from ari_core.modules.memory.db import list_memory_blocks, memory_block_to_payload
    from ari_core.modules.memory.explain import explain_coding_loop_retry_approval

    approval, execution_run, _root, db_path = _executed_retry_approval(tmp_path)

    first = capture_coding_loop_retry_approval_memory(
        approval.approval_id,
        db_path=db_path,
    )
    second = capture_coding_loop_retry_approval_memory(
        approval.approval_id,
        db_path=db_path,
    )
    blocks = [
        memory_block_to_payload(row) for row in list_memory_blocks(layer="session", db_path=db_path)
    ]

    assert first["id"] == second["id"]
    assert first["kind"] == "coding_loop_retry_execution_summary"
    assert first["source"] == approval.approval_id
    assert "Original goal: Create a proof file" in str(first["body"])
    assert "Retry execution status: completed" in str(first["body"])
    assert approval.retry_execution_run_id in first["subject_ids"]
    assert execution_run["id"] in first["subject_ids"]
    assert len(blocks) == 1

    explanation = explain_coding_loop_retry_approval(
        approval.approval_id,
        db_path=db_path,
    )
    assert explanation["subject"]["id"] == approval.approval_id
    assert explanation["approval_status"] == "approved"
    assert explanation["retry_execution_status"] == "completed"
    assert explanation["evidence"]["retry_execution_run"]["id"] == execution_run["id"]
    assert explanation["memory_blocks"][0]["id"] == first["id"]
    assert any("Retry execution run" in reason for reason in explanation["why"])


def test_capture_coding_loop_chain_lifecycle_memory_is_compact_and_idempotent(
    tmp_path: Path,
) -> None:
    from ari_core.modules.execution import list_coding_loop_retry_approvals
    from ari_core.modules.execution.inspection import list_execution_runs
    from ari_core.modules.memory.capture import (
        capture_coding_loop_chain_lifecycle_memory,
    )
    from ari_core.modules.memory.db import list_memory_blocks, memory_block_to_payload
    from ari_core.modules.memory.explain import explain_coding_loop_chain_lifecycle

    approval, execution_run, _root, db_path = _executed_retry_approval(tmp_path)
    result_id = approval.source_coding_loop_result_id
    approval_count_before = len(list_coding_loop_retry_approvals(db_path=db_path))
    run_count_before = len(list_execution_runs(limit=20, db_path=db_path))

    first = capture_coding_loop_chain_lifecycle_memory(result_id, db_path=db_path)
    second = capture_coding_loop_chain_lifecycle_memory(result_id, db_path=db_path)
    blocks = [
        memory_block_to_payload(row) for row in list_memory_blocks(layer="session", db_path=db_path)
    ]

    assert first["id"] == second["id"]
    assert first["kind"] == "coding_loop_chain_lifecycle_summary"
    assert first["source"] == result_id
    assert result_id in first["subject_ids"]
    assert approval.approval_id in first["subject_ids"]
    assert execution_run["id"] in first["subject_ids"]
    assert "Original goal: Create a proof file" in str(first["body"])
    assert "Terminal status: stopped" in str(first["body"])
    assert "Chain depth: 1" in str(first["body"])
    assert "Approvals: 1 total, 1 approved, 0 rejected, 0 pending" in str(first["body"])
    assert "Retry executions: 1" in str(first["body"])
    assert "Final review status: stop" in str(first["body"])
    assert "Lesson:" in str(first["body"])
    assert len(blocks) == 1

    evidence = first["evidence"][0]
    assert evidence["terminal_status"] == "stopped"
    assert evidence["chain_depth"] == 1
    assert evidence["approval_count"] == 1
    assert evidence["approved_count"] == 1
    assert evidence["retry_execution_count"] == 1
    assert evidence["final_execution_status"] == "completed"
    assert evidence["final_post_run_review_status"] == "stop"
    assert "contexts" not in evidence
    assert "decisions" not in evidence
    assert "results" not in evidence

    explanation = explain_coding_loop_chain_lifecycle(result_id, db_path=db_path)
    assert explanation["subject"]["id"] == result_id
    assert explanation["terminal_status"] == "stopped"
    assert explanation["chain_depth"] == 1
    assert explanation["memory_blocks"][0]["id"] == first["id"]
    assert any("Latest review status: stop" in reason for reason in explanation["why"])

    assert len(list_coding_loop_retry_approvals(db_path=db_path)) == approval_count_before
    assert len(list_execution_runs(limit=20, db_path=db_path)) == run_count_before


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

    explain_output = StringIO()
    with redirect_stdout(explain_output):
        exit_code = main(
            ["api", "memory", "explain", "execution", "--id", run_id, "--json"],
            db_path=db_path,
        )
    assert exit_code == 0
    explanation = json.loads(explain_output.getvalue())
    assert explanation["subject"]["id"] == run_id
    assert explanation["memory_blocks"][0]["source"] == run_id


def test_memory_capture_retry_approval_cli(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"
    approval, _execution_run, _root, _state_path = _executed_retry_approval(
        tmp_path,
        db_path=db_path,
    )

    capture_output = StringIO()
    with redirect_stdout(capture_output):
        exit_code = main(
            [
                "api",
                "memory",
                "capture",
                "retry-approval",
                "--id",
                approval.approval_id,
                "--json",
            ],
            db_path=db_path,
        )

    assert exit_code == 0
    block = json.loads(capture_output.getvalue())["block"]
    assert block["source"] == approval.approval_id
    assert block["kind"] == "coding_loop_retry_execution_summary"

    explain_output = StringIO()
    with redirect_stdout(explain_output):
        exit_code = main(
            [
                "api",
                "memory",
                "explain",
                "retry-approval",
                "--id",
                approval.approval_id,
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    explanation = json.loads(explain_output.getvalue())
    assert explanation["subject"]["id"] == approval.approval_id
    assert explanation["retry_execution_status"] == "completed"
    assert explanation["memory_blocks"][0]["source"] == approval.approval_id


def test_memory_capture_coding_loop_chain_cli(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"
    approval, _execution_run, _root, _state_path = _executed_retry_approval(
        tmp_path,
        db_path=db_path,
    )
    result_id = approval.source_coding_loop_result_id

    capture_output = StringIO()
    with redirect_stdout(capture_output):
        exit_code = main(
            [
                "api",
                "memory",
                "capture",
                "coding-loop-chain",
                "--id",
                result_id,
                "--json",
            ],
            db_path=db_path,
        )

    assert exit_code == 0
    block = json.loads(capture_output.getvalue())["block"]
    assert block["source"] == result_id
    assert block["kind"] == "coding_loop_chain_lifecycle_summary"

    explain_output = StringIO()
    with redirect_stdout(explain_output):
        exit_code = main(
            [
                "api",
                "memory",
                "explain",
                "coding-loop-chain",
                "--id",
                result_id,
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    explanation = json.loads(explain_output.getvalue())
    assert explanation["subject"]["id"] == result_id
    assert explanation["terminal_status"] == "stopped"
    assert explanation["memory_blocks"][0]["source"] == result_id


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

        explained = client.get(f"/explain/execution/{run_id}")
        assert explained.status_code == 200
        assert explained.json()["subject"]["id"] == run_id
        assert explained.json()["memory_blocks"][0]["source"] == run_id


def test_memory_capture_retry_approval_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    _purge_modules()

    from ari_api import create_app
    from ari_core.core.paths import DB_PATH

    approval, execution_run, _root, _db_path = _executed_retry_approval(
        tmp_path,
        db_path=DB_PATH,
    )

    app = create_app()
    with TestClient(app) as client:
        captured = client.post(
            f"/memory/capture/coding-loop-retry-approvals/{approval.approval_id}"
        )
        assert captured.status_code == 200
        assert captured.json()["block"]["source"] == approval.approval_id
        assert captured.json()["block"]["kind"] == "coding_loop_retry_execution_summary"

        explained = client.get(
            f"/explain/coding-loop-retry-approvals/{approval.approval_id}"
        )
        assert explained.status_code == 200
        assert explained.json()["subject"]["id"] == approval.approval_id
        assert explained.json()["retry_execution_status"] == "completed"
        assert explained.json()["evidence"]["retry_execution_run"]["id"] == execution_run["id"]
        assert explained.json()["memory_blocks"][0]["source"] == approval.approval_id


def test_memory_capture_coding_loop_chain_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    _purge_modules()

    from ari_api import create_app
    from ari_core.core.paths import DB_PATH

    approval, _execution_run, _root, _db_path = _executed_retry_approval(
        tmp_path,
        db_path=DB_PATH,
    )
    result_id = approval.source_coding_loop_result_id

    app = create_app()
    with TestClient(app) as client:
        captured = client.post(f"/memory/capture/coding-loop-chains/{result_id}")
        assert captured.status_code == 200
        assert captured.json()["block"]["source"] == result_id
        assert captured.json()["block"]["kind"] == "coding_loop_chain_lifecycle_summary"
        assert captured.json()["block"]["evidence"][0]["terminal_status"] == "stopped"

        explained = client.get(f"/explain/coding-loop-chains/{result_id}")
        assert explained.status_code == 200
        assert explained.json()["subject"]["id"] == result_id
        assert explained.json()["terminal_status"] == "stopped"
        assert explained.json()["memory_blocks"][0]["source"] == result_id
