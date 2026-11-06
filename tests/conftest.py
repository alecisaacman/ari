from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sqlite3.dbapi2
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


# Live ARI's databases. Live ARI writes these while tests run (the iMessage poller,
# the signal engine, the builder), so comparing them before and after a run can't tell
# a test's write from ARI's own. Instead, the test process may not open them at all:
# sqlite3.connect refuses, which also covers SQLAlchemy. Tests reach their own copies
# through ARI_HOME, set above; subprocesses inherit that too.
LIVE_DATABASE_DIRS = tuple(
    path.resolve(strict=False)
    for path in (_OPERATOR_HOME / "ARI" / "state", _OPERATOR_HOME / "ARI" / "modules")
)


class LiveStateAccessError(RuntimeError):
    """A test tried to open one of live ARI's databases."""


def _sqlite_target(database: object) -> Path | None:
    if isinstance(database, bytes):
        database = database.decode()
    if not isinstance(database, (str, os.PathLike)):
        return None
    text = os.fspath(database)
    if text.startswith("file:"):
        text = text.removeprefix("file:").split("?", 1)[0].removeprefix("//")
    if not text or text == ":memory:":
        return None
    return Path(text).expanduser().resolve(strict=False)


def _is_live_database(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in LIVE_DATABASE_DIRS)


_REAL_SQLITE_CONNECT = sqlite3.connect


def _guarded_sqlite_connect(database, *args, **kwargs):  # type: ignore[no-untyped-def]
    target = _sqlite_target(database)
    if target is not None and _is_live_database(target):
        raise LiveStateAccessError(f"A test tried to open live ARI state: {target}")
    return _REAL_SQLITE_CONNECT(database, *args, **kwargs)


sqlite3.connect = _guarded_sqlite_connect
sqlite3.dbapi2.connect = _guarded_sqlite_connect


def _protected_state_roots() -> tuple[Path, ...]:
    """Files nothing else writes during a run, so any change means a test wrote them."""
    configured = os.environ.get("ARI_TEST_PROTECTED_STATE_PATHS", "")
    extra_paths = [Path(value).expanduser() for value in configured.split(os.pathsep) if value]
    candidates = [
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
