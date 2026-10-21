from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(
    script: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args],
        cwd=REPO_ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def test_ari_status_resolves_the_source_bearing_worktree(tmp_path: Path) -> None:
    launch_agents = tmp_path / "LaunchAgents"
    launch_agents.mkdir()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = _run_script(
        REPO_ROOT / "tools" / "ari-status",
        env={
            "ARI_CANONICAL_PYTHON": sys.executable,
            "ARI_LAUNCH_AGENT_DIR": str(launch_agents),
        },
    )

    assert result.returncode == 0, result.stderr
    assert f"ARI source checkout: {REPO_ROOT}" in result.stdout
    assert f"Branch: {branch}" in result.stdout
    assert f"Python runtime: {sys.executable}" in result.stdout


def test_launch_agent_status_reports_a_missing_target(tmp_path: Path) -> None:
    launch_agents = tmp_path / "LaunchAgents"
    launch_agents.mkdir()
    plist_path = launch_agents / "com.alecisaacman.ari-test.plist"
    with plist_path.open("wb") as handle:
        plistlib.dump(
            {
                "Label": "com.alecisaacman.ari-test",
                "ProgramArguments": [str(tmp_path / "missing-executable")],
                "WorkingDirectory": str(tmp_path),
            },
            handle,
        )

    result = _run_script(
        REPO_ROOT / "scripts" / "launch_agents" / "status.sh",
        env={"ARI_LAUNCH_AGENT_DIR": str(launch_agents)},
    )

    assert result.returncode == 1
    assert "target status: INVALID (missing or not executable)" in result.stdout
    assert str(tmp_path / "missing-executable") in result.stdout


def test_launch_agent_installer_check_is_read_only(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = _run_script(
        REPO_ROOT / "scripts" / "telegram_gateway" / "install_launch_agent.sh",
        "--check",
        env={
            "HOME": str(home),
            "ARI_CANONICAL_PYTHON": sys.executable,
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Preflight passed; no files were written." in result.stdout
    assert not (home / "Library" / "LaunchAgents").exists()


def test_launch_agent_installer_refuses_to_overwrite_existing_plist(tmp_path: Path) -> None:
    home = tmp_path / "home"
    launch_agents = home / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True)
    plist_path = launch_agents / "com.alecisaacman.ari.telegram-gateway.plist"
    original = b"existing operator configuration\n"
    plist_path.write_bytes(original)

    result = _run_script(
        REPO_ROOT / "scripts" / "telegram_gateway" / "install_launch_agent.sh",
        env={
            "HOME": str(home),
            "ARI_CANONICAL_PYTHON": sys.executable,
        },
    )

    assert result.returncode == 2
    assert "Refusing to overwrite existing LaunchAgent" in result.stderr
    assert plist_path.read_bytes() == original
