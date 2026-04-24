from __future__ import annotations

import sys
from pathlib import Path


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "ari_core" or module_name.startswith("ari_core."):
            sys.modules.pop(module_name, None)


def test_bounded_execution_can_write_patch_and_run_cat(tmp_path: Path, monkeypatch) -> None:
    execution_root = tmp_path / "execution-root"
    execution_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(execution_root))
    _purge_modules()

    from ari_core import ari

    write_result = ari.execute(
        {
            "type": "write_file",
            "path": "sample.txt",
            "content": "hello pending world\n",
        }
    )
    assert write_result["success"] is True
    assert (execution_root / "sample.txt").read_text(encoding="utf-8") == "hello pending world\n"

    patch_result = ari.execute(
        {
            "type": "patch_file",
            "path": "sample.txt",
            "find": "pending",
            "replace": "ready",
        }
    )
    assert patch_result["success"] is True
    assert (execution_root / "sample.txt").read_text(encoding="utf-8") == "hello ready world\n"

    command_result = ari.execute(
        {
            "type": "run_command",
            "command": ["cat", "sample.txt"],
        }
    )
    assert command_result == {
        "success": True,
        "stdout": "hello ready world\n",
        "stderr": "",
        "exit_code": 0,
    }


def test_bounded_execution_prefers_explicit_root_over_environment(
    tmp_path: Path, monkeypatch
) -> None:
    env_root = tmp_path / "env-root"
    explicit_root = tmp_path / "explicit-root"
    env_root.mkdir(parents=True, exist_ok=True)
    explicit_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(env_root))
    _purge_modules()

    from ari_core import ari

    result = ari.execute(
        {
            "type": "write_file",
            "path": "sample.txt",
            "content": "explicit wins\n",
        },
        execution_root=explicit_root,
    )

    assert result["success"] is True
    assert (explicit_root / "sample.txt").read_text(encoding="utf-8") == "explicit wins\n"
    assert not (env_root / "sample.txt").exists()


def test_execution_tool_registry_lists_canonical_bounded_tools() -> None:
    from ari_core.modules.execution import get_execution_tool_registry

    registry = get_execution_tool_registry()
    payload = registry.prompt_payload()

    assert payload["allowed_actions"] == [
        "patch_file",
        "read_file",
        "run_command",
        "write_file",
    ]
    assert "cat" in payload["allowed_commands"]
    assert {tool["action_type"] for tool in payload["tools"]} == set(payload["allowed_actions"])
