from __future__ import annotations

from pathlib import Path

from ari_core.runtime.playground import PLAYGROUND_DIRNAME, prepare_playground_workspace


def test_prepare_playground_workspace_creates_seed_files_and_safe_worker(tmp_path: Path) -> None:
    workspace_root = tmp_path / "playground"

    workspace = prepare_playground_workspace(workspace_root, reset=True)

    root = Path(workspace.root)
    assert root == workspace_root.resolve()
    assert (root / "README.md").exists()
    assert (root / "playground_module.py").read_text(encoding="utf-8") == "PLAYGROUND_READY = False\n"
    assert (root / "notes.txt").exists()
    assert (root / ".git").exists()
    assert (root / PLAYGROUND_DIRNAME / "runs").exists()
    assert (root / PLAYGROUND_DIRNAME / "state").exists()
    worker_script = Path(workspace.worker_script)
    assert worker_script.exists()
    assert workspace.worker_command_prefix[0]
    assert workspace.worker_command_prefix[-1] == str(worker_script)
