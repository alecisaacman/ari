from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from ari_core.core.paths import ARI_ROOT, DB_PATH
from ari_core.surface_status import SurfaceStatusStore, build_surface_status

REPO_ROOT = Path(__file__).resolve().parents[2]


def _canonical_checkout_root() -> Path:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--git-common-dir"],
        check=True,
        capture_output=True,
        text=True,
    )
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = REPO_ROOT / common_dir
    return common_dir.resolve().parent


def _tree_fingerprints(root: Path) -> dict[Path, tuple[str, int]]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_default_python_state_is_under_isolated_suite_root(
    isolated_test_runtime_root: Path,
) -> None:
    assert ARI_ROOT == isolated_test_runtime_root / "ari-home"
    assert DB_PATH.is_relative_to(isolated_test_runtime_root)
    assert Path(os.environ["ARI_HOME"]).is_relative_to(isolated_test_runtime_root)


def test_each_test_gets_an_isolated_surface_status_directory(
    tmp_path: Path,
) -> None:
    status_dir = Path(os.environ["ARI_SURFACE_STATUS_DIR"])
    assert status_dir == tmp_path / "surface-status"
    assert not status_dir.is_relative_to(Path.home() / "ARI")
    assert not status_dir.is_relative_to(REPO_ROOT / "data" / "surface" / "status")


def _file_fingerprint(path: Path) -> tuple[str, int] | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_isolated_writes_preserve_live_database_and_status_hashes_and_mtimes() -> None:
    live_database = Path.home() / "ARI" / "modules" / "networking-crm" / "state" / "networking.db"
    live_status_dir = _canonical_checkout_root() / "data" / "surface" / "status"
    database_before = _file_fingerprint(live_database)
    status_before = _tree_fingerprints(live_status_dir)

    status = build_surface_status(state="success", summary="Isolated regression check")
    SurfaceStatusStore().write(status)

    assert _file_fingerprint(live_database) == database_before
    assert _tree_fingerprints(live_status_dir) == status_before
