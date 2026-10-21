from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

UNSET_EXECUTION_ROOT_MARKER = "unset_execution_root"


@dataclass(frozen=True, slots=True)
class _FileFingerprint:
    exists: bool
    sha256: str | None
    mtime_ns: int | None
    size: int | None


_OPERATOR_HOME = Path.home()
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="ari-pytest-runtime-"))
_TEST_ARI_HOME = _TEST_RUNTIME_ROOT / "ari-home"
_TEST_SURFACE_STATUS_DIR = _TEST_RUNTIME_ROOT / "surface-status"

# These must be set before pytest imports test modules. ari_core.core.paths resolves
# DB_PATH at import time, so an autouse fixture alone is too late to protect the
# operator's live ARI database during collection and in-process default arguments.
os.environ["ARI_HOME"] = str(_TEST_ARI_HOME)
os.environ["ARI_CANONICAL_HOME"] = str(_TEST_ARI_HOME)
os.environ["ARI_SURFACE_STATUS_DIR"] = str(_TEST_SURFACE_STATUS_DIR)


def _canonical_checkout_root() -> Path:
    configured = os.environ.get("ARI_LIVE_SOURCE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--git-common-dir"],
        check=True,
        capture_output=True,
        text=True,
    )
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = _REPO_ROOT / common_dir
    return common_dir.resolve(strict=False).parent


def _protected_state_roots() -> tuple[Path, ...]:
    configured = os.environ.get("ARI_TEST_PROTECTED_STATE_PATHS", "")
    extra_paths = [Path(value).expanduser() for value in configured.split(os.pathsep) if value]
    candidates = [
        _OPERATOR_HOME / "ARI" / "modules" / "networking-crm" / "state" / "networking.db",
        _canonical_checkout_root() / "data" / "surface" / "status",
        *extra_paths,
    ]
    return tuple(dict.fromkeys(path.resolve(strict=False) for path in candidates))


def _fingerprint(path: Path) -> _FileFingerprint:
    if not path.is_file():
        return _FileFingerprint(exists=False, sha256=None, mtime_ns=None, size=None)
    stat_result = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return _FileFingerprint(
        exists=True,
        sha256=digest,
        mtime_ns=stat_result.st_mtime_ns,
        size=stat_result.st_size,
    )


def _protected_state_snapshot() -> dict[Path, _FileFingerprint]:
    snapshot: dict[Path, _FileFingerprint] = {}
    for root in _protected_state_roots():
        if root.is_dir():
            for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
                snapshot[path] = _fingerprint(path)
        else:
            snapshot[root] = _fingerprint(root)
    return snapshot


_PROTECTED_STATE_BEFORE = _protected_state_snapshot()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{UNSET_EXECUTION_ROOT_MARKER}: run with ARI_EXECUTION_ROOT removed, exercising the "
        "production fallback instead of the per-test configured root",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    protected_state_after = _protected_state_snapshot()
    changed = {
        path: (
            _PROTECTED_STATE_BEFORE.get(path, _FileFingerprint(False, None, None, None)),
            protected_state_after.get(path, _FileFingerprint(False, None, None, None)),
        )
        for path in _PROTECTED_STATE_BEFORE.keys() | protected_state_after.keys()
        if _PROTECTED_STATE_BEFORE.get(path) != protected_state_after.get(path)
    }
    if changed:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep("=", "protected ARI state changed during tests", red=True)
            for path, (before, after) in changed.items():
                reporter.write_line(f"{path}: before={before!r} after={after!r}", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    shutil.rmtree(_TEST_RUNTIME_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def configured_execution_root(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Path]:
    """Configure each test's server-side execution root as its own tmp directory.

    Execution roots may only be the configured root or a descendant of it, as in a
    deployment that sets ARI_EXECUTION_ROOT. Tests that need a different configured
    root set the variable themselves, which overrides this default. Tests marked
    `unset_execution_root` get no configured root at all, so the production fallback
    stays tested. An ambient ARI_ALLOW_SELF_MODIFICATION is always removed. A separate
    MonkeyPatch keeps a test's own `monkeypatch.undo()` from removing these settings.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("ARI_ALLOW_SELF_MODIFICATION", raising=False)
        patch.setenv("ARI_HOME", str(_TEST_ARI_HOME))
        patch.setenv("ARI_CANONICAL_HOME", str(_TEST_ARI_HOME))
        patch.setenv("ARI_SURFACE_STATUS_DIR", str(tmp_path / "surface-status"))
        if request.node.get_closest_marker(UNSET_EXECUTION_ROOT_MARKER):
            patch.delenv("ARI_EXECUTION_ROOT", raising=False)
        else:
            patch.setenv("ARI_EXECUTION_ROOT", str(tmp_path))
        yield tmp_path


@pytest.fixture(scope="session")
def isolated_test_runtime_root() -> Path:
    return _TEST_RUNTIME_ROOT
