from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from ari_core.modules.execution import command_capabilities as capabilities
from ari_core.modules.execution import engine
from ari_core.modules.execution.command_capabilities import (
    CommandCapabilityError,
    CommandClass,
    PreparedCommand,
    prepare_command,
    run_prepared_command,
)
from ari_core.modules.execution.contracts import EffectTerminality
from ari_core.modules.execution.dispatch import (
    DispatchLandingUnproven,
    classify_effect_terminality,
)
from ari_core.modules.execution.sandbox import ExecutionRoot
from ari_core.modules.execution.tools import get_execution_tool_registry
from test_dispatch_safety import _command_task, _fences, _rule_out
from test_recovered_action_gateway import _recovered_task

PASSING_TEST = "def test_ok():\n    assert True\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An execution root (a child of the per-test configured root)."""
    path = (tmp_path / "repo").resolve()
    (path / "sub").mkdir(parents=True)
    (path / "a.txt").write_text("alpha\n", encoding="utf-8")
    (path / "sub" / "b.txt").write_text("beta\n", encoding="utf-8")
    (path / "test_ok.py").write_text(PASSING_TEST, encoding="utf-8")
    return path


def _wait_until_gone(pid: int, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


# --- read-only inspection ---------------------------------------------------------------


def test_ls_and_cat_run_legitimately(root: Path) -> None:
    sandbox = ExecutionRoot(root)

    listing = sandbox.run_command(["ls"])
    long_listing = sandbox.run_command(["ls", "-la", "sub"])
    content = sandbox.run_command(["cat", "a.txt", "sub/b.txt"])

    assert listing.success and "a.txt" in listing.stdout and "sub" in listing.stdout
    assert long_listing.success and "b.txt" in long_listing.stdout
    assert content.success and content.stdout == "alpha\nbeta\n"


def test_read_only_capabilities_use_trusted_binaries_not_the_callers_path(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evil_bin = tmp_path / "evil-bin"
    evil_bin.mkdir()
    marker = tmp_path / "evil-ran"
    for name in ("ls", "cat"):
        script = evil_bin / name
        script.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{evil_bin}{os.pathsep}{os.environ['PATH']}")

    prepared = prepare_command(["ls", "-l", "sub"], root=root)
    result = ExecutionRoot(root).run_command(["cat", "a.txt"])

    assert prepared.argv[0] in {"/bin/ls", "/usr/bin/ls"}
    assert prepared.argv[-2:] == ("--", "sub")
    assert prepared.command_class is CommandClass.READ_ONLY_INSPECTION
    assert result.stdout == "alpha\n"
    assert not marker.exists()


@pytest.mark.parametrize(
    "command",
    [
        ["cat", "../outside.txt"],
        ["cat", "/etc/passwd"],
        ["cat", "escape-link"],
        ["cat"],
        ["cat", "-n", "a.txt"],
        ["cat", "-"],
        ["ls", "/"],
        ["ls", "../"],
        ["ls", "--color=always"],
        ["ls", "-R"],
        ["rm", "-rf", "."],
        ["sh", "-c", "ls"],
        ["/bin/ls"],
    ],
)
def test_read_only_commands_outside_their_shape_are_rejected(
    root: Path, tmp_path: Path, command: list[str]
) -> None:
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")
    (root / "escape-link").symlink_to(tmp_path / "outside.txt")

    with pytest.raises(CommandCapabilityError):
        prepare_command(command, root=root)
    with pytest.raises(ValueError):
        ExecutionRoot(root).run_command(command)


def test_registry_reports_run_command_as_mutating_with_explicit_capabilities() -> None:
    registry = get_execution_tool_registry()
    tools = {tool["action_type"]: tool for tool in registry.list_tools()}
    payload = registry.prompt_payload()
    classes = {item["name"]: item["classification"] for item in payload["command_capabilities"]}

    assert tools["run_command"]["mutates_files"] is True
    assert classes == {
        "ls": "read_only_inspection",
        "cat": "read_only_inspection",
        "pytest": "code_execution",
        "node": "code_execution",
    }
    assert "npm" not in payload["allowed_commands"]


# --- gateway restrictions -----------------------------------------------------------------


@pytest.mark.parametrize("restriction", ["read only", "read-only", "no mutations", "no_file_writes"])
def test_read_only_task_allows_constrained_cat_but_rejects_pytest(
    tmp_path: Path, restriction: str
) -> None:
    allowed = _recovered_task(
        tmp_path / "allowed",
        restrictions=(restriction,),
        step_two_action=("run_command", {"command": ["cat", "step-one.txt"]}),
        permitted_side_effects=("run_command",),
    )
    rejected = _recovered_task(
        tmp_path / "rejected",
        restrictions=(restriction,),
        step_two_action=("run_command", {"command": ["pytest", "-q"]}),
        permitted_side_effects=("run_command",),
    )

    allowed_result = allowed.resume()
    rejected_result = rejected.resume()

    assert allowed_result.executed is True
    assert allowed_result.result is not None
    assert allowed_result.result["stdout"] == "step one complete\n"
    assert rejected_result.executed is False
    assert "only read-only inspection commands" in rejected_result.reason


# --- pytest -------------------------------------------------------------------------------


DISALLOWED_PYTEST_ARGS = [
    ["--junitxml=report.xml"],
    ["--junitxml", "report.xml"],
    ["--junit-xml=report.xml"],
    ["--basetemp=/tmp/elsewhere"],
    ["--basetemp", "/tmp/elsewhere"],
    ["-o", "addopts=-p evil"],
    ["-oaddopts=-p evil"],
    ["--override-ini=addopts=-p evil"],
    ["--rootdir=/"],
    ["--rootdir", "/"],
    ["-c", "/tmp/evil.ini"],
    ["-c/tmp/evil.ini"],
    ["--config-file=/tmp/evil.ini"],
    ["-p", "evil_plugin"],
    ["-pevil_plugin"],
    ["-p", "no:cacheprovider"],
    ["--debug"],
    ["--debug=trace.log"],
    ["--log-file=out.log"],
    ["--log-file", "out.log"],
    ["--confcutdir=/"],
    ["--pdb"],
    ["-W", "error::evil.Warning"],
    ["--import-mode=importlib"],
    ["--cache-clear"],
    ["-qq"],
    ["@args.txt"],
    ["--tb=evil"],
    ["--maxfail=0"],
    ["-k"],
    ["-k", "--rootdir=/"],
    ["-k=expr"],
    ["../outside_test.py"],
    ["/etc/test_x.py"],
    ["escape::test_x"],
]


@pytest.mark.parametrize("args", DISALLOWED_PYTEST_ARGS)
def test_every_disallowed_pytest_option_or_path_is_rejected(
    root: Path, tmp_path: Path, args: list[str]
) -> None:
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)

    for spelling in (["pytest"], ["python", "-m", "pytest"]):
        with pytest.raises(CommandCapabilityError):
            prepare_command([*spelling, *args], root=root)


def test_legitimate_pytest_invocations_run_with_aris_interpreter(root: Path) -> None:
    sandbox = ExecutionRoot(root)
    plain = sandbox.run_command(["pytest", "-q", "test_ok.py"])
    shaped = sandbox.run_command(
        ["python3", "-m", "pytest", "test_ok.py::test_ok", "-k", "ok", "-m", "not slow",
         "--tb=short", "--maxfail", "1", "-x", "--no-header"]
    )
    prepared = prepare_command(["pytest", "test_ok.py"], root=root)

    assert plain.success and "1 passed" in plain.stdout
    assert shaped.success and "1 passed" in shaped.stdout
    assert prepared.argv[:4] == (sys.executable, "-P", "-m", "pytest")
    assert prepared.argv[4:10] == (
        "-c", os.devnull, "--rootdir", str(root), "--confcutdir", str(root)
    )
    assert prepared.argv[10:20] == capabilities.PYTEST_INTERNAL_OPTIONS
    assert prepared.argv[20:] == ("test_ok.py",)
    assert prepared.command_class is CommandClass.CODE_EXECUTION


def test_pytest_config_and_conftest_above_the_root_cannot_inject(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    root = parent / "root"
    root.mkdir(parents=True)
    marker = tmp_path / "parent-conftest-ran"
    (parent / "pytest.ini").write_text("[pytest]\naddopts = --co\n", encoding="utf-8")
    (parent / "conftest.py").write_text(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n", encoding="utf-8"
    )
    (root / "test_ok.py").write_text(PASSING_TEST, encoding="utf-8")

    result = ExecutionRoot(root).run_command(["pytest", "-q", "test_ok.py"])

    assert result.success and "1 passed" in result.stdout
    assert not marker.exists()


def test_root_local_pytest_config_is_pinned(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers = ["slow"]\n', encoding="utf-8"
    )

    prepared = prepare_command(["pytest"], root=root)

    assert prepared.argv[4:6] == ("-c", str(root / "pyproject.toml"))


def test_inherited_hostile_environment_does_not_affect_pytest(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    marker = tmp_path / "hostile-ran"
    payload = f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n"
    (hostile / "sitecustomize.py").write_text(payload, encoding="utf-8")
    (hostile / "evil_plugin.py").write_text(payload, encoding="utf-8")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--co")
    monkeypatch.setenv("PYTEST_PLUGINS", "evil_plugin")
    monkeypatch.setenv("PYTHONPATH", str(hostile))
    monkeypatch.setenv("NODE_OPTIONS", "--require /tmp/evil.js")

    prepared = prepare_command(["pytest", "-q", "test_ok.py"], root=root)
    env = capabilities.command_environment(prepared)
    result = ExecutionRoot(root).run_command(["pytest", "-q", "test_ok.py"])

    assert result.success and "1 passed" in result.stdout
    assert not marker.exists()
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH", "NODE_OPTIONS"):
        assert name not in env
    assert env["HOME"] == str(root / ".ari-exec" / "home")
    assert env["TMPDIR"] == str(root / ".ari-exec" / "tmp")
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert set(env) <= {
        "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTHONNOUSERSITE",
    }


def test_read_only_commands_get_no_scratch_home(root: Path) -> None:
    env = capabilities.command_environment(prepare_command(["ls"], root=root))

    assert "HOME" not in env and "TMPDIR" not in env
    assert not (root / ".ari-exec").exists()


# --- python executable identity -------------------------------------------------------------


@pytest.mark.parametrize(
    "executable",
    ["python-evil", "pythonevil", "python3-evil", "/tmp/python-evil", "evil/python3.evil", "py"],
)
def test_python_prefixed_lookalikes_are_rejected(root: Path, executable: str) -> None:
    with pytest.raises(CommandCapabilityError):
        prepare_command([executable, "-m", "pytest", "test_ok.py"], root=root)


def test_requested_interpreter_path_is_never_executed(root: Path, tmp_path: Path) -> None:
    fake_bin = root / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-python-ran"
    fake_python = fake_bin / "python"
    fake_python.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    fake_python.chmod(0o755)

    result = ExecutionRoot(root).run_command([str(fake_python), "-m", "pytest", "-q", "test_ok.py"])

    assert result.success and "1 passed" in result.stdout
    assert not marker.exists()


def test_engine_maps_python_spellings_to_the_trusted_interpreter(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine, "ensure_not_paused", lambda: None)
    monkeypatch.setenv("ARI_EXECUTION_ROOT", str(root))

    ok = engine.execute_command("python -m pytest test_ok.py -q")
    venv_spelling = engine.execute_command(".venv312/bin/python -m pytest test_ok.py -q")

    assert ok["success"] is True and "1 passed" in ok["stdout"]
    assert venv_spelling["success"] is True
    for command in (
        "python-evil -m pytest test_ok.py",
        "python -c 'import os'",
        "python -m pip install evil",
        "python -m pytest --rootdir=/ test_ok.py",
        "npm test",
        "npm run build",
        "npx evil",
        "node -e 'process.exit(0)'",
    ):
        with pytest.raises(ValueError, match="not allowed"):
            engine.execute_command(command)


# --- node / npm -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "test"],
        ["npm", "run", "lint"],
        ["npx", "jest"],
        ["node"],
        ["node", "script.js"],
        ["node", "-e", "require('fs')"],
        ["node", "--eval", "1"],
        ["node", "--require", "evil.js", "--test", "a.test.js"],
        ["node", "--test"],
        ["node", "--check"],
        ["node", "--check", "../outside.js"],
        ["node", "--test", "/etc/x.test.js"],
        ["node", "--check", "a.js", "b.js"],
    ],
)
def test_npm_and_node_extra_authority_is_rejected(root: Path, command: list[str]) -> None:
    with pytest.raises(CommandCapabilityError):
        prepare_command(command, root=root)


@pytest.mark.skipif(
    shutil.which("node", path=capabilities.NODE_SEARCH_PATH) is None,
    reason="node is not installed in a trusted system location",
)
def test_node_check_is_a_code_execution_capability(root: Path) -> None:
    (root / "ok.js").write_text("const x = 1;\n", encoding="utf-8")

    prepared = prepare_command(["node", "--check", "ok.js"], root=root)
    result = ExecutionRoot(root).run_command(["node", "--check", "ok.js"])

    assert prepared.command_class is CommandClass.CODE_EXECUTION
    assert result.success


# --- process lifecycle ----------------------------------------------------------------------


def _python_command(root: Path, code: str) -> PreparedCommand:
    return PreparedCommand(
        capability="test-python",
        command_class=CommandClass.CODE_EXECUTION,
        argv=(sys.executable, "-c", textwrap.dedent(code)),
        cwd=root,
        root=root,
    )


def test_timeout_kills_the_child_and_its_process_group(root: Path) -> None:
    pid_file = root / "grandchild.pid"
    prepared = _python_command(
        root,
        f"""
        import pathlib, subprocess, sys, time
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))
        time.sleep(60)
        """,
    )

    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_prepared_command(prepared, timeout_seconds=1.5)

    assert time.monotonic() - started < 15
    assert _wait_until_gone(int(pid_file.read_text()))


def test_group_members_left_after_return_are_cleaned_up(root: Path) -> None:
    pid_file = root / "lingering.pid"
    prepared = _python_command(
        root,
        f"""
        import pathlib, subprocess, sys
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))
        """,
    )

    completed = run_prepared_command(prepared, timeout_seconds=30)

    assert completed.returncode == 0
    assert _wait_until_gone(int(pid_file.read_text()))


def test_group_member_holding_output_open_does_not_turn_return_into_timeout(root: Path) -> None:
    pid_file = root / "holder.pid"
    prepared = _python_command(
        root,
        f"""
        import pathlib, subprocess, sys
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))
        print("direct child done")
        """,
    )

    completed = run_prepared_command(prepared, timeout_seconds=2)

    assert completed.returncode == 0
    assert "direct child done" in completed.stdout
    assert _wait_until_gone(int(pid_file.read_text()))


def test_children_inherit_requested_descriptors(root: Path) -> None:
    read_fd, write_fd = os.pipe()
    try:
        prepared = _python_command(root, f"import os; os.write({write_fd}, b'inherited')")
        completed = run_prepared_command(prepared, timeout_seconds=30, pass_fds=(write_fd,))
        assert completed.returncode == 0
        assert os.read(read_fd, 64) == b"inherited"
    finally:
        os.close(read_fd)
        os.close(write_fd)


# --- redispatch terminality is untouched ------------------------------------------------------


@pytest.mark.parametrize(
    "command", [["ls"], ["cat", "a.txt"], ["pytest", "-q"], ["node", "--check", "a.js"]]
)
def test_run_command_terminality_stays_unbounded(command: list[str]) -> None:
    assert (
        classify_effect_terminality({"type": "run_command", "command": command})
        is EffectTerminality.UNBOUNDED
    )
    assert (
        classify_effect_terminality({"type": "write_file", "path": "a", "content": "b"})
        is EffectTerminality.IN_PROCESS
    )


def test_process_cleanup_never_yields_a_landing_token(tmp_path: Path) -> None:
    recovered = _command_task(tmp_path, ["cat", "step-one.txt"])

    result = recovered.resume()
    [fence] = _fences(recovered)

    assert result.executed is True
    assert fence["state"] == "returned"
    assert fence["effect_terminality"] == "unbounded"
    assert fence["landing_token"] is None
    with pytest.raises(DispatchLandingUnproven, match="unbounded"):
        _rule_out(recovered)
    assert _fences(recovered)[0]["landing_token"] is None


# --- pytest module identity and root configuration ----------------------------------------


@pytest.mark.parametrize("shadow", ["pytest.py", "pytest/__init__.py"])
def test_root_local_module_cannot_shadow_pytest(root: Path, tmp_path: Path, shadow: str) -> None:
    marker = tmp_path / "shadow-ran"
    target = root / shadow
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n", encoding="utf-8"
    )

    result = ExecutionRoot(root).run_command(["pytest", "-q", "test_ok.py"])

    assert result.success and "1 passed" in result.stdout
    assert not marker.exists()


def test_root_config_cannot_add_options_paths_or_output_locations(
    root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "above_root_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pytest.ini").write_text(
        "[pytest]\n"
        f"addopts = --junitxml={outside}/junit.xml --basetemp={outside}/basetemp --co\n"
        "pythonpath = ..\n"
        f"log_file = {outside}/pytest.log\n"
        f"cache_dir = {outside}/cache\n"
        "testpaths = ..\n",
        encoding="utf-8",
    )
    (root / "test_imports.py").write_text(
        "import importlib.util\n\n"
        "def test_above_root_is_not_importable():\n"
        "    assert importlib.util.find_spec('above_root_module') is None\n",
        encoding="utf-8",
    )

    result = ExecutionRoot(root).run_command(["pytest", "-q", "test_imports.py", "test_ok.py"])

    assert result.success and "2 passed" in result.stdout, result.stdout + result.stderr
    assert list(outside.iterdir()) == []


def test_plugin_autoload_and_ambient_plugin_variables_are_disabled(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.metadata

    installed = {entry.name for entry in importlib.metadata.entry_points(group="pytest11")}
    monkeypatch.setenv("PYTEST_PLUGINS", "pytest_cov")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p pytest_cov")
    (root / "test_plugins.py").write_text(
        "def test_no_autoloaded_plugins(pytestconfig):\n"
        "    names = {name for name, _ in pytestconfig.pluginmanager.list_name_plugin()}\n"
        f"    assert not names & set({sorted(installed)!r}), names\n",
        encoding="utf-8",
    )

    result = ExecutionRoot(root).run_command(["pytest", "-q", "test_plugins.py"])

    assert installed, "the environment should have at least one entry-point plugin"
    assert result.success and "1 passed" in result.stdout, result.stdout + result.stderr


# --- scratch directory creation -------------------------------------------------------------


@pytest.mark.parametrize("planted", [".ari-exec", ".ari-exec/.gitignore", ".ari-exec/home", ".ari-exec/tmp"])
def test_scratch_creation_refuses_symlinks_and_never_writes_outside(
    root: Path, tmp_path: Path, planted: str
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    dangling = outside / "created-by-ari"
    link = root / planted
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(dangling if planted.endswith(".gitignore") else outside)

    with pytest.raises(CommandCapabilityError, match="scratch"):
        ExecutionRoot(root).run_command(["pytest", "-q", "test_ok.py"])

    assert not dangling.exists()
    assert list(outside.iterdir()) == []


def test_scratch_creation_reuses_real_directories(root: Path) -> None:
    sandbox = ExecutionRoot(root)
    sandbox.run_command(["pytest", "-q", "test_ok.py"])
    second = sandbox.run_command(["pytest", "-q", "test_ok.py"])

    assert second.success
    assert (root / ".ari-exec" / ".gitignore").read_text(encoding="utf-8") == "*\n"


# --- cat aliases ---------------------------------------------------------------------------


def test_cat_refuses_symlinks_and_hardlinked_aliases(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    os.link(outside, root / "hardlink.txt")
    (root / "inside-link.txt").symlink_to(root / "a.txt")

    for path, reason in (("hardlink.txt", "hard links"), ("inside-link.txt", "symlink")):
        with pytest.raises(CommandCapabilityError, match=reason):
            prepare_command(["cat", path], root=root)


# --- process-group ownership ---------------------------------------------------------------


@pytest.fixture
def signal_log(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int, bool]]:
    """Record every killpg with whether the group leader still existed (unreaped)."""
    calls: list[tuple[int, int, bool]] = []
    real_killpg = os.killpg

    def recording_killpg(pgid: int, sig: int) -> None:
        try:
            os.kill(pgid, 0)  # succeeds for a running or zombie (unreaped) leader
            leader_present = True
        except ProcessLookupError:
            leader_present = False
        calls.append((pgid, sig, leader_present))
        real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", recording_killpg)
    return calls


def _lingering_child(root: Path, pid_file: Path, *, then_sleep: bool = False) -> PreparedCommand:
    return _python_command(
        root,
        f"""
        import pathlib, subprocess, sys, time
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))
        {"time.sleep(60)" if then_sleep else ""}
        """,
    )


def test_post_return_cleanup_only_signals_while_the_leader_is_unreaped(
    root: Path, signal_log: list[tuple[int, int, bool]]
) -> None:
    pid_file = root / "member.pid"

    completed = run_prepared_command(_lingering_child(root, pid_file), timeout_seconds=30)

    assert completed.returncode == 0
    assert signal_log, "the lingering group member should have been signalled"
    assert all(present for _pgid, _sig, present in signal_log)
    assert _wait_until_gone(int(pid_file.read_text()))


def test_timeout_signals_term_then_kill_while_the_leader_is_unreaped(
    root: Path, signal_log: list[tuple[int, int, bool]]
) -> None:
    import signal

    pid_file = root / "member.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        run_prepared_command(_lingering_child(root, pid_file, then_sleep=True), timeout_seconds=1.5)

    assert [sig for _pgid, sig, _present in signal_log][:2] == [signal.SIGTERM, signal.SIGKILL]
    assert all(present for _pgid, _sig, present in signal_log)
    assert _wait_until_gone(int(pid_file.read_text()))


def test_without_a_non_reaping_wait_post_return_cleanup_is_skipped(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    signal_log: list[tuple[int, int, bool]],
) -> None:
    pid_file = root / "member.pid"
    monkeypatch.setattr(
        capabilities,
        "_wait_for_exit_unreaped",
        lambda _pid, _timeout: capabilities._LeaderState.UNKNOWN,
    )

    try:
        completed = run_prepared_command(_lingering_child(root, pid_file), timeout_seconds=30)
        assert completed.returncode == 0
        assert signal_log == []  # never signals a group after reaping its leader
    finally:
        os.kill(int(pid_file.read_text()), 9)


def test_signalling_a_reaped_leaders_group_is_refused(root: Path) -> None:
    import signal

    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    process.wait()

    with pytest.raises(RuntimeError, match="already-reaped"):
        capabilities._signal_group(process, signal.SIGKILL)
