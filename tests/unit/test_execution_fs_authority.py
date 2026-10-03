from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _modules() -> tuple[ModuleType, type]:
    from ari_core.modules.execution import fs_authority
    from ari_core.modules.execution.sandbox import ExecutionRoot

    return fs_authority, ExecutionRoot


def _configure(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(root))
    return root.resolve()


# --- root authority -----------------------------------------------------------------


def test_configured_root_and_child_roots_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    (configured / "child").mkdir()

    assert ExecutionRoot().root == configured
    assert ExecutionRoot(configured).root == configured
    assert ExecutionRoot(configured / "child").root == configured / "child"
    assert ExecutionRoot("child").root == configured / "child"


@pytest.mark.parametrize(
    "requested",
    ["/", "{tmp}/sibling", "../sibling", "child/../../sibling"],
)
def test_roots_outside_the_configured_root_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requested: str
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    (configured / "child").mkdir()
    (tmp_path / "sibling").mkdir()

    with pytest.raises(ValueError, match="outside the configured execution root"):
        ExecutionRoot(requested.format(tmp=tmp_path))


def test_symlinked_root_escaping_the_configured_root_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    outside = tmp_path / "outside"
    outside.mkdir()
    (configured / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="outside the configured execution root"):
        ExecutionRoot("escape")


def test_filesystem_root_cannot_be_the_configured_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _, ExecutionRoot = _modules()
    monkeypatch.setenv("ARI_EXECUTION_ROOT", "/")

    with pytest.raises(ValueError, match="filesystem root"):
        ExecutionRoot()


def test_roots_overlapping_ari_state_storage_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs_authority, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    ari_home = configured / "ari-home"
    (ari_home / "state").mkdir(parents=True)
    monkeypatch.setattr(fs_authority.core_paths, "ARI_ROOT", ari_home)
    monkeypatch.setattr(fs_authority.core_paths, "DB_PATH", ari_home / "state" / "ari.db")

    with pytest.raises(ValueError, match="ARI state storage"):
        ExecutionRoot()  # configured root contains state
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(ari_home / "state"))
    with pytest.raises(ValueError, match="ARI state storage"):
        ExecutionRoot()  # configured root inside state


# --- file replacement ---------------------------------------------------------------


def test_normal_write_and_patch_succeed_without_leaving_temp_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    root = ExecutionRoot()

    root.write_file("pkg/module.py", "value = 'old'\n")
    root.patch_file("pkg/module.py", "old", "new")

    assert (configured / "pkg" / "module.py").read_text(encoding="utf-8") == "value = 'new'\n"
    assert sorted(path.name for path in (configured / "pkg").iterdir()) == ["module.py"]


def test_replacement_is_an_atomic_rename_and_failure_leaves_target_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs_authority, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    target = configured / "data.txt"
    target.write_text("before\n", encoding="utf-8")
    original_inode = target.stat().st_ino
    root = ExecutionRoot()

    with target.open(encoding="utf-8") as reader:
        root.write_file("data.txt", "after\n")
        assert reader.read() == "before\n"  # the old inode was swapped, not rewritten
    assert target.stat().st_ino != original_inode
    assert target.read_text(encoding="utf-8") == "after\n"

    def failing_fsync(_fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(fs_authority.os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="disk full"):
        root.write_file("data.txt", "partial\n")
    assert target.read_text(encoding="utf-8") == "after\n"
    assert sorted(path.name for path in configured.iterdir()) == ["data.txt"]


def test_existing_file_mode_is_preserved_and_new_files_follow_umask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    script = configured / "run.sh"
    script.write_text("echo old\n", encoding="utf-8")
    script.chmod(0o750)
    root = ExecutionRoot()

    previous_umask = os.umask(0o027)
    try:
        root.write_file("run.sh", "echo new\n")
        root.patch_file("run.sh", "new", "newer")
        root.write_file("fresh.txt", "fresh\n")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(script.stat().st_mode) == 0o750
    assert stat.S_IMODE((configured / "fresh.txt").stat().st_mode) == 0o640


def test_final_symlink_is_never_written_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    real = configured / "real.txt"
    real.write_text("real\n", encoding="utf-8")
    (configured / "link.txt").symlink_to(real)
    root = ExecutionRoot()

    with pytest.raises(ValueError, match="symlink"):
        root.write_file("link.txt", "through link\n")
    with pytest.raises(ValueError, match="symlink"):
        root.patch_file("link.txt", "real", "patched")
    assert real.read_text(encoding="utf-8") == "real\n"
    assert (configured / "link.txt").is_symlink()


def test_symlink_escape_out_of_the_root_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (configured / "out").symlink_to(outside_dir, target_is_directory=True)
    root = ExecutionRoot()

    with pytest.raises(ValueError, match="escapes execution root"):
        root.write_file("out/planted.txt", "planted\n")
    with pytest.raises(ValueError, match="escapes execution root"):
        root.write_file("../outside/planted.txt", "planted\n")
    assert not (outside_dir / "planted.txt").exists()


def test_hardlinked_file_cannot_overwrite_an_outside_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside\n", encoding="utf-8")
    os.link(outside, configured / "alias.txt")
    root = ExecutionRoot()

    with pytest.raises(ValueError, match="hard links"):
        root.write_file("alias.txt", "overwritten\n")
    with pytest.raises(ValueError, match="hard links"):
        root.patch_file("alias.txt", "outside", "overwritten")
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_non_regular_targets_are_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    (configured / "a-directory").mkdir()

    with pytest.raises(ValueError, match="regular files"):
        ExecutionRoot().write_file("a-directory", "x\n")


# --- protected internal paths ---------------------------------------------------------


PROTECTED_TARGETS = [
    "config/migrations/0099_evil.sql",
    "config/migrations/nested/x.sql",
    "config/schema.sql",
    "Config/Migrations/0099_case.sql",
    ".git/config",
    ".git/hooks/pre-commit",
    "vendor/lib/.git/HEAD",
]


@pytest.mark.parametrize("target", PROTECTED_TARGETS)
def test_protected_paths_are_rejected_by_execution_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    existing = configured / target
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("original find-me\n", encoding="utf-8")
    root = ExecutionRoot()

    with pytest.raises(ValueError, match="may not modify"):
        root.write_file(target, "tampered\n")
    with pytest.raises(ValueError, match="may not modify"):
        root.patch_file(target, "find-me", "tampered")
    assert existing.read_text(encoding="utf-8") == "original find-me\n"
    assert root.read_file(target) == "original find-me\n"  # reads stay allowed


@pytest.mark.parametrize("target", PROTECTED_TARGETS)
def test_protected_paths_are_rejected_by_tool_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    from ari_core.modules.execution.tools import get_execution_tool_registry

    _, ExecutionRoot = _modules()
    _configure(monkeypatch, tmp_path / "configured")
    registry = get_execution_tool_registry()

    for action in (
        {"type": "write_file", "path": target, "content": "x"},
        {"type": "patch_file", "path": target, "find": "a", "replace": "b"},
    ):
        error = registry.validate_execution_action(action, execution_root=ExecutionRoot())
        assert error is not None and "may not modify" in error
    assert (
        registry.validate_execution_action(
            {"type": "read_file", "path": target}, execution_root=ExecutionRoot()
        )
        is None
    )


def test_absolute_protected_ari_paths_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs_authority, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    legacy_state = configured / "runtime" / "state"
    legacy_state.mkdir(parents=True)
    monkeypatch.setattr(fs_authority.core_paths, "LEGACY_STATE_DIR", legacy_state)

    with pytest.raises(ValueError, match="protected ARI path"):
        ExecutionRoot().write_file("runtime/state/networking.db", "x")
    with pytest.raises(ValueError, match="protected ARI path"):
        ExecutionRoot().write_file("RUNTIME/State/other.txt", "x")


def test_engine_file_tools_share_the_same_protections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ari_core.modules.execution import engine

    monkeypatch.setattr(engine, "ensure_not_paused", lambda: None)
    configured = _configure(monkeypatch, tmp_path / "configured")
    db_path = tmp_path / "engine.db"
    (configured / "config" / "migrations").mkdir(parents=True)
    real = configured / "real.py"
    real.write_text("value = 1\n", encoding="utf-8")
    (configured / "link.py").symlink_to(real)
    outside = tmp_path / "outside.py"
    outside.write_text("value = 'outside'\n", encoding="utf-8")
    os.link(outside, configured / "alias.py")

    for path, match in (
        ("config/migrations/0099_evil.sql", "may not modify"),
        ("config/schema.sql", "may not modify"),
        ("link.py", "symlink"),
        ("alias.py", "hard links"),
        ("../outside.py", "escapes the execution root"),
    ):
        with pytest.raises(ValueError, match=match):
            engine.write_file(path, "tampered = True\n", db_path=db_path)
    with pytest.raises(ValueError, match="may not modify"):
        engine.create_operator_action(
            title="t",
            summary="s",
            operations=[{"type": "write", "path": "config/schema.sql", "content": "x"}],
            db_path=db_path,
        )

    result = engine.write_file("module.py", "value = 2\n", db_path=db_path)
    engine.patch_file("module.py", find_text="2", replace_text="3", db_path=db_path)
    assert result["success"] is True
    assert (configured / "module.py").read_text(encoding="utf-8") == "value = 3\n"
    assert real.read_text(encoding="utf-8") == "value = 1\n"
    assert outside.read_text(encoding="utf-8") == "value = 'outside'\n"


# --- API and CLI surfaces -------------------------------------------------------------


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name.split(".")[0] in {"ari_core", "ari_api"}:
            sys.modules.pop(module_name, None)


def test_api_execution_root_cannot_exceed_the_configured_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    configured = _configure(monkeypatch, tmp_path / "configured")
    (configured / "child").mkdir()
    (tmp_path / "sibling").mkdir()
    _purge_modules()

    from ari_api import create_app

    with TestClient(create_app()) as client:
        accepted = client.get("/execution/context")
        child = client.get("/execution/context", params={"executionRoot": "child"})
        rejected = [
            client.get("/execution/context", params={"executionRoot": root})
            for root in ("/", str(tmp_path / "sibling"), "../sibling", str(tmp_path))
        ]
        coding_loop = client.post(
            "/execution/coding-loop",
            json={"goal": "write a file", "executionRoot": str(tmp_path / "sibling")},
        )

    assert accepted.status_code == 200
    assert accepted.json()["context"]["repo_root"] == str(configured)
    assert child.status_code == 200
    assert child.json()["context"]["repo_root"] == str(configured / "child")
    for response in rejected:
        assert response.status_code == 400
        assert "outside the configured execution root" in response.json()["detail"]
    assert coding_loop.status_code == 400
    assert "outside the configured execution root" in coding_loop.json()["detail"]
    assert list((tmp_path / "sibling").iterdir()) == []


def test_cli_execution_root_obeys_the_configured_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    _configure(monkeypatch, tmp_path / "configured")
    (tmp_path / "sibling").mkdir()
    _purge_modules()

    from ari_core.ari import main

    with pytest.raises(ValueError, match="outside the configured execution root"):
        main(
            [
                "api",
                "execution",
                "plan",
                "--goal",
                "list files",
                "--execution-root",
                str(tmp_path / "sibling"),
            ]
        )


# --- read aliases -------------------------------------------------------------------


def test_hardlinked_file_cannot_be_read_as_an_alias_for_an_outside_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ari_core.modules.execution import engine

    _, ExecutionRoot = _modules()
    configured = _configure(monkeypatch, tmp_path / "configured")
    monkeypatch.setattr(engine, "ensure_not_paused", lambda: None)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside secret\n", encoding="utf-8")
    os.link(outside, configured / "alias.txt")
    (configured / "plain.txt").write_text("plain\n", encoding="utf-8")

    with pytest.raises(ValueError, match="multiple hard links"):
        ExecutionRoot().read_file("alias.txt")
    with pytest.raises(ValueError, match="multiple hard links"):
        engine.read_file("alias.txt")
    assert ExecutionRoot().read_file("plain.txt") == "plain\n"


# --- live runtime overlap and the production fallback --------------------------------


def _project_root() -> Path:
    from ari_core.core import paths

    return paths.PROJECT_ROOT.resolve()


@pytest.mark.unset_execution_root
def test_unset_execution_root_fails_closed_instead_of_using_the_live_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ari_core.modules.execution import engine

    _, ExecutionRoot = _modules()
    monkeypatch.setattr(engine, "ensure_not_paused", lambda: None)
    assert "ARI_EXECUTION_ROOT" not in os.environ

    with pytest.raises(ValueError, match="ARI_EXECUTION_ROOT is not set"):
        ExecutionRoot()
    with pytest.raises(ValueError, match="ARI_EXECUTION_ROOT is not set"):
        engine.write_file("anything.txt", "x\n", db_path=Path(os.devnull))
    with pytest.raises(ValueError, match="ARI_EXECUTION_ROOT is not set"):
        engine.execute_command("pytest -q")


@pytest.mark.unset_execution_root
def test_read_only_task_inspection_works_without_an_execution_root(tmp_path: Path) -> None:
    from ari_core.modules.execution.gateway import RecoveredActionGateway

    gateway = RecoveredActionGateway(tmp_path / "ari.db")  # does not resolve a root

    with pytest.raises(ValueError, match="does not exist"):
        gateway.inspect_task("missing-task")
    with pytest.raises(ValueError, match="ARI_EXECUTION_ROOT is not set"):
        _ = gateway.execution_root


@pytest.mark.unset_execution_root
@pytest.mark.parametrize("value", ["true", "yes", "0", " 1", ""])
def test_only_the_exact_operator_override_enables_self_modification(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _, ExecutionRoot = _modules()
    monkeypatch.setenv("ARI_ALLOW_SELF_MODIFICATION", value)

    with pytest.raises(ValueError, match="ARI_EXECUTION_ROOT is not set"):
        ExecutionRoot()


@pytest.mark.unset_execution_root
def test_operator_override_allows_self_development_but_keeps_runtime_paths_protected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fs_authority, ExecutionRoot = _modules()
    monkeypatch.setenv("ARI_ALLOW_SELF_MODIFICATION", "1")
    project = _project_root()
    root = ExecutionRoot()
    venv_target = Path(sys.prefix).resolve() / "lib" / "evil.pth"

    assert root.root == project
    assert root.resolve_write_path("services/ari-core/src/ari_core/new_module.py")
    for protected in (
        "config/migrations/0099_x.sql",
        "config/schema.sql",
        ".git/config",
        str(venv_target),
    ):
        if Path(protected).is_absolute() and project not in Path(protected).parents:
            continue
        with pytest.raises(ValueError, match="may not modify"):
            root.resolve_write_path(protected)
    assert fs_authority.protected_write_reason(project, venv_target) is not None


@pytest.mark.parametrize(
    "configured",
    [
        "{project}",
        "{project}/services",
        "{project}/services/ari-core/src/ari_core",
        "{project_parent}",
    ],
)
def test_configured_roots_overlapping_the_live_checkout_are_rejected(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    _, ExecutionRoot = _modules()
    project = _project_root()
    monkeypatch.setenv(
        "ARI_EXECUTION_ROOT",
        configured.format(project=project, project_parent=project.parent),
    )

    with pytest.raises(ValueError, match="live runtime"):
        ExecutionRoot()


def test_roots_overlapping_the_python_environment_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs_authority, ExecutionRoot = _modules()
    # Move the checkout elsewhere so only the Python environment can trigger the rule.
    monkeypatch.setattr(fs_authority.core_paths, "PROJECT_ROOT", tmp_path / "elsewhere")
    prefix = Path(sys.prefix).resolve()
    for configured in (prefix, prefix / "lib", prefix.parent):
        monkeypatch.setenv("ARI_EXECUTION_ROOT", str(configured))
        with pytest.raises(ValueError, match=re.escape(f"live runtime ({prefix})")):
            ExecutionRoot()


def test_external_and_child_workspaces_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ExecutionRoot = _modules()
    workspace = _configure(monkeypatch, tmp_path / "external-workspace")
    (workspace / "child").mkdir()

    assert ExecutionRoot().root == workspace
    assert ExecutionRoot("child").root == workspace / "child"


@pytest.mark.unset_execution_root
def test_api_requests_cannot_select_or_enable_the_live_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    _purge_modules()
    from ari_api import create_app

    project = str(_project_root())
    with TestClient(create_app()) as client:
        responses = [
            client.get("/execution/context"),
            client.get(
                "/execution/context",
                params={"executionRoot": project, "ARI_ALLOW_SELF_MODIFICATION": "1"},
            ),
            client.post(
                "/execution/coding-loop",
                json={
                    "goal": "write a file",
                    "executionRoot": project,
                    "allowSelfModification": True,
                    "ARI_ALLOW_SELF_MODIFICATION": "1",
                },
            ),
            client.post("/execution/files/read", json={"path": "README.md"}),
            client.post(
                "/execution/command",
                json={"command": "pytest -q", "cwd": ".", "timeoutSeconds": 5},
            ),
        ]

    for response in responses:
        assert response.status_code in {400, 422}, response.text
        if response.status_code == 400:
            assert "ARI_EXECUTION_ROOT is not set" in response.json()["detail"]
    assert "ARI_ALLOW_SELF_MODIFICATION" not in os.environ
