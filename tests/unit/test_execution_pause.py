from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "ari_core" or module_name.startswith("ari_core.") or module_name == "ari_api" or module_name.startswith("ari_api."):
            sys.modules.pop(module_name, None)


def _setup_env(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    execution_root = tmp_path / "execution-root"
    execution_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(execution_root))
    _purge_modules()
    return execution_root


def test_engine_functions_raise_and_do_not_mutate_when_paused(tmp_path: Path, monkeypatch) -> None:
    execution_root = _setup_env(tmp_path, monkeypatch)

    from ari_core.core.pause import pause, resume
    from ari_core.modules.execution.engine import (
        create_operator_action,
        execute_command,
        get_execution_snapshot,
        patch_file,
        write_file,
    )

    target = execution_root / "target.py"
    target.write_text("x = 1\n", encoding="utf-8")

    pause("smoke test")

    with pytest.raises(ValueError, match="paused"):
        write_file("new.py", "x = 1\n")
    assert not (execution_root / "new.py").exists()

    with pytest.raises(ValueError, match="paused"):
        patch_file("target.py", find_text="x = 1", replace_text="x = 2")
    assert target.read_text(encoding="utf-8") == "x = 1\n"

    with pytest.raises(ValueError, match="paused"):
        execute_command("python -m pytest --version")

    with pytest.raises(ValueError, match="paused"):
        create_operator_action(
            title="t",
            summary="s",
            operations=[{"type": "write", "path": "blocked.py", "content": "x = 1\n"}],
        )
    assert get_execution_snapshot()["recent_actions"] == []
    assert not (execution_root / "blocked.py").exists()

    resume()

    result = write_file("new.py", "x = 1\n")
    assert result["success"] is True
    assert (execution_root / "new.py").exists()


def test_run_operator_action_raises_when_paused_after_approval(tmp_path: Path, monkeypatch) -> None:
    execution_root = _setup_env(tmp_path, monkeypatch)

    from ari_core.core.pause import pause
    from ari_core.modules.execution.engine import (
        approve_operator_action,
        create_operator_action,
        run_operator_action,
    )

    action = create_operator_action(
        title="t",
        summary="s",
        operations=[{"type": "write", "path": "pending.py", "content": "x = 1\n"}],
        approval_required=True,
    )
    approve_operator_action(action["id"])

    pause("smoke test")

    with pytest.raises(ValueError, match="paused"):
        run_operator_action(action["id"])
    assert not (execution_root / "pending.py").exists()

    with pytest.raises(ValueError, match="paused"):
        approve_operator_action(action["id"])


def test_cli_pause_resume_paused_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _setup_env(tmp_path, monkeypatch)

    from ari_core.ari import main

    assert main(["paused"]) == 0
    assert main(["pause", "--reason", "cli test"]) == 0
    with pytest.raises(ValueError, match="paused"):
        main(["api", "execution", "write-file", "--path", "x.py", "--content", "x=1"])
    assert main(["resume"]) == 0
    assert main(["api", "execution", "write-file", "--path", "x.py", "--content", "x=1"]) == 0


def test_http_pause_resume_paused_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _setup_env(tmp_path, monkeypatch)

    from ari_api import create_app

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/paused").json()["paused"] is False

        paused = client.post("/pause", json={"reason": "api test"}).json()
        assert paused["paused"] is True
        assert paused["reason"] == "api test"

        blocked = client.post("/execution/files/write", json={"path": "x.py", "content": "x=1"})
        assert blocked.status_code == 400
        assert "paused" in blocked.json()["detail"]

        resumed = client.post("/resume").json()
        assert resumed["paused"] is False

        allowed = client.post("/execution/files/write", json={"path": "x.py", "content": "x=1"})
        assert allowed.status_code == 200
