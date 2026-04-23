from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.paths import PROJECT_ROOT


PLAYGROUND_DIRNAME = ".ari-playground"


@dataclass(frozen=True, slots=True)
class PlaygroundWorkspace:
    root: str
    db_path: str
    runs_dir: str
    worker_script: str
    worker_command_prefix: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def prepare_playground_workspace(
    workspace: Path | str | None = None,
    *,
    reset: bool = False,
) -> PlaygroundWorkspace:
    root = Path(workspace or (PROJECT_ROOT / "tmp" / "ari-playground")).expanduser().resolve()
    metadata_dir = root / PLAYGROUND_DIRNAME
    runs_dir = metadata_dir / "runs"
    state_dir = metadata_dir / "state"

    if reset and root.exists():
        _reset_workspace(root)

    runs_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    _ensure_git_repo(root)
    _ensure_seed_files(root)
    _ensure_seed_commit(root)
    worker_script = _write_safe_worker_script(metadata_dir)

    return PlaygroundWorkspace(
        root=str(root),
        db_path=str(state_dir / "networking.db"),
        runs_dir=str(runs_dir),
        worker_script=str(worker_script),
        worker_command_prefix=[sys.executable, str(worker_script)],
    )


def persist_playground_summary(workspace: PlaygroundWorkspace, name: str, payload: dict[str, object]) -> str:
    runs_dir = Path(workspace.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / f"{name}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(output_path)


def _reset_workspace(root: Path) -> None:
    if not root.exists():
        return
    for child in root.iterdir():
        if child.name == ".git":
            _remove_path(child)
            continue
        if child.name == PLAYGROUND_DIRNAME:
            _remove_path(child)
            continue
        _remove_path(child)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        for child in path.iterdir():
            _remove_path(child)
        path.rmdir()
        return
    path.unlink()


def _ensure_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git_dir = root / ".git"
    if git_dir.exists():
        return
    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, text=True, check=True)


def _ensure_seed_files(root: Path) -> None:
    seed_files = {
        ".gitignore": f"{PLAYGROUND_DIRNAME}/\n",
        "README.md": "# ARI Playground\n\nDisposable workspace for ARI runtime validation.\n",
        "playground_module.py": "PLAYGROUND_READY = False\n",
        "notes.txt": "playground notes\n",
    }
    for relative_path, content in seed_files.items():
        file_path = root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")


def _ensure_seed_commit(root: Path) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if head.returncode == 0:
        return

    subprocess.run(["git", "config", "user.name", "ARI Playground"], cwd=str(root), capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "ari-playground@local.invalid"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "add", ".gitignore", "README.md", "playground_module.py", "notes.txt"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initialize ARI playground"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )


def _write_safe_worker_script(metadata_dir: Path) -> Path:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    script_path = metadata_dir / "safe_codex_worker.py"
    script_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import sys",
                "from pathlib import Path",
                "",
                "prompt = sys.argv[1] if len(sys.argv) > 1 else ''",
                "root = Path.cwd()",
                "lowered = prompt.lower()",
                "changed = []",
                "",
                "if 'playground_module.py' in prompt or 'playground_ready' in lowered:",
                "    target = root / 'playground_module.py'",
                "    target.write_text('PLAYGROUND_READY = True\\n', encoding='utf-8')",
                "    changed.append('playground_module.py')",
                "",
                "if 'worker-note.txt' in lowered or 'codex loop' in lowered or 'bounded coding worker change' in lowered:",
                "    target = root / 'worker-note.txt'",
                "    target.write_text('worker completed bounded task\\n', encoding='utf-8')",
                "    changed.append('worker-note.txt')",
                "",
                "if 'note_capture.txt' in lowered or 'capture' in lowered:",
                "    target = root / 'note_capture.txt'",
                "    target.write_text('captured note context\\n', encoding='utf-8')",
                "    changed.append('note_capture.txt')",
                "",
                "if not changed:",
                "    target = root / 'playground-output.txt'",
                "    target.write_text('playground worker ran\\n', encoding='utf-8')",
                "    changed.append('playground-output.txt')",
                "",
                "print('safe worker changed: ' + ', '.join(changed))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return script_path
