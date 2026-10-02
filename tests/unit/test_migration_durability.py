"""Durability of the SQLite migration runner.

Each versioned migration must land as one unit with its `ari_schema_migrations` row,
and concurrent initializers must not race on a pending migration. Process-level tests
use real OS processes against scratch databases only.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from ari_core.core.paths import MIGRATIONS_DIR
from ari_core.modules.networking.db import MigrationLockTimeout, initialize_database

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = REPO_ROOT / "services" / "ari-core" / "src"
VERSIONS = sorted(path.stem for path in MIGRATIONS_DIR.glob("*.sql"))
NON_REPEATABLE = (
    "0002_execution_sessions",
    "0004_effect_reconciliation",
    "0005_dispatch_fences",
    "0006_redispatch_safety",
)
PROCESSES = 8
CRASH_EXIT = 77

# Trial counts stay small by default; raise them to stress the runner.
RACE_TRIALS = int(os.environ.get("ARI_MIGRATION_RACE_TRIALS", "3"))
PENDING_TRIALS = int(os.environ.get("ARI_MIGRATION_PENDING_TRIALS", "1"))

WORKER = textwrap.dedent(
    """
    import json, os, sqlite3, sys, time
    from pathlib import Path

    from ari_core.modules.networking import db

    args = json.loads(sys.argv[1])
    crash = args.get("crash")
    if crash:
        real_connect = sqlite3.connect
        seen = {"match": False}

        def trace(statement):
            if seen["match"]:
                os._exit(%(crash_exit)d)
            if crash["match"] in statement:
                if crash["when"] == "before":
                    os._exit(%(crash_exit)d)
                seen["match"] = True

        def connect(*connect_args, **connect_kwargs):
            connection = real_connect(*connect_args, **connect_kwargs)
            connection.set_trace_callback(trace)
            return connection

        sqlite3.connect = connect

    pause = args.get("pause")
    if pause:
        real_connect_for_pause = sqlite3.connect
        paused = {"done": False}

        def pause_trace(statement):
            if not paused["done"] and pause["match"] in statement:
                paused["done"] = True
                Path(pause["paused"]).touch()
                while not Path(pause["resume"]).exists():
                    time.sleep(0.005)

        def pausing_connect(*connect_args, **connect_kwargs):
            connection = real_connect_for_pause(*connect_args, **connect_kwargs)
            connection.set_trace_callback(pause_trace)
            return connection

        sqlite3.connect = pausing_connect

    if args.get("ready"):
        Path(args["ready"]).touch()
        while not Path(args["go"]).exists():
            time.sleep(0.0005)

    kwargs = {"db_path": Path(args["db"])}
    if args.get("migrations"):
        kwargs["migrations_dir"] = Path(args["migrations"])
    try:
        db.initialize_database(**kwargs)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
    """
) % {"crash_exit": CRASH_EXIT}


@pytest.fixture
def scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    (tmp_path / "worker.py").write_text(WORKER, encoding="utf-8")
    return tmp_path


def _env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(CORE_SRC), *filter(None, [env.get("PYTHONPATH")])])
    env.update(extra)
    return env


def _spawn(scratch: Path, args: dict[str, Any], **env: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(scratch / "worker.py"), json.dumps(args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(**env),
    )


def _run(scratch: Path, args: dict[str, Any], **env: str) -> subprocess.CompletedProcess[str]:
    process = _spawn(scratch, args, **env)
    stdout, stderr = process.communicate(timeout=120)
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _contend(scratch: Path, tag: str, base_args: dict[str, Any]) -> list[tuple[int, str]]:
    """Start PROCESSES initializers that all begin at the same instant."""
    gate = scratch / f"gate-{tag}"
    gate.mkdir()
    go = gate / "go"
    workers = [
        _spawn(scratch, {**base_args, "ready": str(gate / f"ready-{index}"), "go": str(go)})
        for index in range(PROCESSES)
    ]
    deadline = time.monotonic() + 60
    while len(list(gate.glob("ready-*"))) < PROCESSES:
        assert time.monotonic() < deadline, "workers never became ready"
        time.sleep(0.005)
    go.touch()
    results = []
    for worker in workers:
        _, stderr = worker.communicate(timeout=120)
        results.append((worker.returncode, stderr.strip()))
    return results


def _migrations_upto(scratch: Path, count: int) -> Path:
    directory = scratch / f"migrations-{count}"
    if not directory.exists():
        directory.mkdir()
        for version in VERSIONS[:count]:
            shutil.copy(MIGRATIONS_DIR / f"{version}.sql", directory / f"{version}.sql")
    return directory


def _schema(db_path: Path) -> dict[str, Any]:
    with closing(sqlite3.connect(db_path)) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table' "
                "and name not like 'sqlite_%' order by name"
            )
        ]
        tables = {
            name: [tuple(row) for row in connection.execute(f"pragma table_info('{name}')")]
            for name in names
        }
        indexes = sorted(
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'index' and sql is not null"
            )
        )
    return {"tables": tables, "indexes": indexes}


def _versions(db_path: Path) -> list[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        exists = connection.execute(
            "select 1 from sqlite_master where name = 'ari_schema_migrations'"
        ).fetchone()
        if exists is None:
            return []
        return [
            row[0]
            for row in connection.execute(
                "select version from ari_schema_migrations order by version"
            )
        ]


def _health(db_path: Path) -> tuple[str, int]:
    with closing(sqlite3.connect(db_path)) as connection:
        integrity = connection.execute("pragma integrity_check").fetchone()[0]
        violations = len(connection.execute("pragma foreign_key_check").fetchall())
    return integrity, violations


def _reference(scratch: Path, count: int) -> dict[str, Any]:
    db_path = scratch / "reference" / f"upto-{count}.db"
    if not db_path.exists():
        initialize_database(db_path=db_path, migrations_dir=_migrations_upto(scratch, count))
    return _schema(db_path)


def _assert_fully_migrated(scratch: Path, db_path: Path) -> None:
    assert _versions(db_path) == VERSIONS
    assert _schema(db_path) == _reference(scratch, len(VERSIONS))
    assert _health(db_path) == ("ok", 0)


def _assert_whole_migration_state(scratch: Path, db_path: Path) -> None:
    """Every recorded version is fully applied and nothing beyond it is."""
    count = len(_versions(db_path))
    assert _versions(db_path) == VERSIONS[:count]
    assert _schema(db_path) == _reference(scratch, count)


# --- atomic rollback --------------------------------------------------------------


def test_failed_migration_rolls_back_every_statement_and_records_nothing(
    scratch: Path,
) -> None:
    migrations = scratch / "with-broken"
    shutil.copytree(MIGRATIONS_DIR, migrations)
    (migrations / "0007_broken.sql").write_text(
        "create table probe_created(x text);\n"
        "alter table ari_execution_tasks add column probe_column text;\n"
        "alter table ari_execution_dispatch_fences rename column lock_path to probe_path;\n"
        "insert into table_that_does_not_exist values (1);\n",
        encoding="utf-8",
    )
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path)
    before = _schema(db_path)

    with pytest.raises(sqlite3.OperationalError, match="table_that_does_not_exist"):
        initialize_database(db_path=db_path, migrations_dir=migrations)

    assert _schema(db_path) == before
    assert _versions(db_path) == VERSIONS

    # An unrecorded migration may be corrected and then applies cleanly.
    (migrations / "0007_broken.sql").write_text(
        "create table probe_created(x text);\n", encoding="utf-8"
    )
    initialize_database(db_path=db_path, migrations_dir=migrations)
    assert _versions(db_path) == [*VERSIONS, "0007_broken"]


def test_statement_splitting_respects_literals_and_comments(scratch: Path) -> None:
    migrations = _migrations_upto(scratch, len(VERSIONS))
    (migrations / "0007_literals.sql").write_text(
        "-- a comment; with a semicolon\n"
        "create table probe_literals(value text);\n"
        "/* block; comment */ insert into probe_literals values ('a;b');\n"
        "insert into probe_literals values ('-- not a comment');\n",
        encoding="utf-8",
    )
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=migrations)
    with closing(sqlite3.connect(db_path)) as connection:
        values = [row[0] for row in connection.execute("select value from probe_literals")]
    assert values == ["a;b", "-- not a comment"]


def test_migration_may_not_control_its_own_transaction(scratch: Path) -> None:
    migrations = _migrations_upto(scratch, len(VERSIONS))
    (migrations / "0007_commits.sql").write_text(
        "create table probe_commit(x text);\ncommit;\n", encoding="utf-8"
    )
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path)
    before = _schema(db_path)

    with pytest.raises(ValueError, match="transaction"):
        initialize_database(db_path=db_path, migrations_dir=migrations)
    assert _schema(db_path) == before
    assert _versions(db_path) == VERSIONS


# --- crash and restart ------------------------------------------------------------


def _version_insert(version: str) -> str:
    return f"'{version}'"


CRASH_POINTS = [
    # (case, statement substring, crash before/after that statement)
    *[
        (f"after-ddl-before-version-{version}", _version_insert(version), "before")
        for version in VERSIONS
    ],
    *[
        (f"after-version-before-commit-{version}", _version_insert(version), "after")
        for version in VERSIONS
    ],
    ("mid-0002", "add column pause_reason", "before"),
    ("mid-0004", "add column reconciliation_id", "before"),
    ("mid-0005", "add column dispatch_fence_state", "before"),
    ("mid-0006-after-renames", "set redispatch_safe = 0", "before"),
    ("mid-0006-before-landing-index", "idx_execution_dispatch_fences_landing_token", "before"),
]


@pytest.mark.parametrize(
    ("match", "when"),
    [(match, when) for _, match, when in CRASH_POINTS],
    ids=[case for case, _, _ in CRASH_POINTS],
)
def test_crash_leaves_whole_migrations_and_restart_completes(
    scratch: Path,
    match: str,
    when: str,
) -> None:
    db_path = scratch / "a.db"
    crashed = _run(scratch, {"db": str(db_path), "crash": {"match": match, "when": when}})
    assert crashed.returncode == CRASH_EXIT, crashed.stderr

    _assert_whole_migration_state(scratch, db_path)

    restarted = _run(scratch, {"db": str(db_path)})
    assert restarted.returncode == 0, restarted.stderr
    _assert_fully_migrated(scratch, db_path)


def test_crash_inside_0006_never_leaves_legacy_retry_eligibility_behind(
    scratch: Path,
) -> None:
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=_migrations_upto(scratch, 5))
    _seed_execution_chain(db_path)

    crashed = _run(
        scratch,
        {"db": str(db_path), "crash": {"match": "set redispatch_safe = 0", "when": "before"}},
    )
    assert crashed.returncode == CRASH_EXIT, crashed.stderr
    with closing(sqlite3.connect(db_path)) as connection:
        columns = {
            row[1]
            for row in connection.execute("pragma table_info(ari_execution_effect_reconciliations)")
        }
    assert "retry_eligible" in columns and "redispatch_safe" not in columns

    assert _run(scratch, {"db": str(db_path)}).returncode == 0
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute(
            "select redispatch_safe from ari_execution_effect_reconciliations"
        ).fetchall() == [(0,)]


# --- concurrency ------------------------------------------------------------------


@pytest.mark.parametrize("trial", range(RACE_TRIALS))
def test_concurrent_first_initialization_serializes(scratch: Path, trial: int) -> None:
    db_path = scratch / "a.db"

    results = _contend(scratch, f"fresh-{trial}", {"db": str(db_path)})

    assert [code for code, _ in results] == [0] * PROCESSES, results
    _assert_fully_migrated(scratch, db_path)


@pytest.mark.parametrize("trial", range(PENDING_TRIALS))
@pytest.mark.parametrize("pending", NON_REPEATABLE)
def test_concurrent_discovery_of_one_pending_migration(
    scratch: Path,
    pending: str,
    trial: int,
) -> None:
    db_path = scratch / "a.db"
    initialize_database(
        db_path=db_path, migrations_dir=_migrations_upto(scratch, VERSIONS.index(pending))
    )
    _seed_execution_chain(db_path)

    results = _contend(scratch, f"pending-{pending}-{trial}", {"db": str(db_path)})

    assert [code for code, _ in results] == [0] * PROCESSES, results
    _assert_fully_migrated(scratch, db_path)


def test_pending_migrations_are_decided_while_holding_the_write_lock(
    scratch: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=_migrations_upto(scratch, 5))
    paused, resume = scratch / "paused", scratch / "resume"
    worker = _spawn(
        scratch,
        {
            "db": str(db_path),
            "pause": {
                "match": "select version, checksum from ari_schema_migrations",
                "paused": str(paused),
                "resume": str(resume),
            },
        },
    )
    deadline = time.monotonic() + 60
    while not paused.exists():
        assert worker.poll() is None, worker.communicate()
        assert time.monotonic() < deadline
        time.sleep(0.005)

    # While the worker is deciding what is pending, nobody else may commit a migration.
    monkeypatch.setenv("ARI_SQLITE_LOCK_TIMEOUT_SECONDS", "0.5")
    try:
        with pytest.raises(MigrationLockTimeout):
            initialize_database(db_path=db_path)
    finally:
        resume.touch()
        _, stderr = worker.communicate(timeout=120)

    assert worker.returncode == 0, stderr
    _assert_fully_migrated(scratch, db_path)


# --- lock contention --------------------------------------------------------------


def _hold_write_lock(db_path: Path, seconds: float) -> threading.Thread:
    holding = threading.Event()

    def hold() -> None:
        with closing(sqlite3.connect(db_path, isolation_level=None)) as connection:
            connection.execute("begin immediate")
            holding.set()
            time.sleep(seconds)
            connection.execute("rollback")

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(10)
    return holder


def test_lock_held_past_timeout_fails_clearly_without_partial_schema(scratch: Path) -> None:
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=_migrations_upto(scratch, 1))
    before = _schema(db_path)

    holder = _hold_write_lock(db_path, 4)
    started = time.monotonic()
    blocked = _run(scratch, {"db": str(db_path)}, ARI_SQLITE_LOCK_TIMEOUT_SECONDS="1")
    elapsed = time.monotonic() - started
    holder.join()

    assert blocked.returncode == 1
    assert "MigrationLockTimeout" in blocked.stderr
    assert elapsed < 4
    assert _schema(db_path) == before
    assert _versions(db_path) == VERSIONS[:1]


def test_initializer_waits_out_a_lock_held_beyond_five_seconds(scratch: Path) -> None:
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=_migrations_upto(scratch, 1))

    holder = _hold_write_lock(db_path, 6)
    waited = _run(scratch, {"db": str(db_path)})
    holder.join()

    assert waited.returncode == 0, waited.stderr
    _assert_fully_migrated(scratch, db_path)


def test_lock_timeout_setting_must_be_a_positive_number(
    scratch: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARI_SQLITE_LOCK_TIMEOUT_SECONDS", "never")
    with pytest.raises(ValueError, match="ARI_SQLITE_LOCK_TIMEOUT_SECONDS"):
        initialize_database(db_path=scratch / "a.db")


# --- upgrades and checksums -------------------------------------------------------


def _seed_execution_chain(db_path: Path) -> None:
    """Insert one linked row per execution table so upgrades carry real data."""
    order = [
        "ari_execution_tasks",
        "ari_execution_attempts",
        "ari_execution_checkpoints",
        "ari_execution_events",
        "ari_execution_results",
        "ari_execution_action_approvals",
        "ari_execution_resume_decisions",
        "ari_execution_action_executions",
        "ari_execution_effect_reconciliations",
        "ari_execution_dispatch_fences",
    ]
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("pragma foreign_keys = on")
        present = {row[0] for row in connection.execute("select name from sqlite_master")}
        for table in [name for name in order if name in present]:
            values: dict[str, object] = {}
            for _, name, column_type, *_ in connection.execute(f"pragma table_info({table})"):
                if table == "ari_execution_action_executions" and name == "reconciliation_id":
                    continue
                values[name] = 1 if "int" in (column_type or "").lower() else "x"
            if table == "ari_execution_dispatch_fences":
                values["state"] = "quiesced"
            if "retry_eligible" in values:
                values["retry_eligible"] = 1
            connection.execute(
                f"insert into {table} ({', '.join(values)}) "
                f"values ({', '.join('?' for _ in values)})",
                list(values.values()),
            )
        connection.commit()


@pytest.mark.parametrize("applied", range(1, len(VERSIONS)))
def test_upgrade_from_each_legacy_state(scratch: Path, applied: int) -> None:
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=_migrations_upto(scratch, applied))
    _seed_execution_chain(db_path)

    initialize_database(db_path=db_path)

    _assert_fully_migrated(scratch, db_path)
    if applied == 5:
        with closing(sqlite3.connect(db_path)) as connection:
            assert connection.execute(
                "select state, effect_terminality, landing_token from ari_execution_dispatch_fences"
            ).fetchall() == [("lock_released", None, None)]
            assert connection.execute(
                "select redispatch_safe from ari_execution_effect_reconciliations"
            ).fetchall() == [(0,)]


def test_repeated_initialization_is_a_no_op(scratch: Path) -> None:
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path)
    first = (_schema(db_path), _versions(db_path))
    initialize_database(db_path=db_path)
    initialize_database(db_path=db_path)
    assert (_schema(db_path), _versions(db_path)) == first


def test_changed_applied_migration_is_rejected_before_anything_new_applies(
    scratch: Path,
) -> None:
    migrations = scratch / "edited"
    shutil.copytree(MIGRATIONS_DIR, migrations)
    db_path = scratch / "a.db"
    initialize_database(db_path=db_path, migrations_dir=migrations)
    with closing(sqlite3.connect(db_path)) as connection:
        original_checksums = connection.execute(
            "select version, checksum from ari_schema_migrations order by version"
        ).fetchall()

    edited = migrations / "0003_recovered_action_gateway.sql"
    edited.write_text(edited.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    (migrations / "0007_new.sql").write_text("create table probe_new(x text);\n")

    with pytest.raises(RuntimeError, match="0003_recovered_action_gateway has changed"):
        initialize_database(db_path=db_path, migrations_dir=migrations)
    assert _versions(db_path) == VERSIONS
    assert "probe_new" not in _schema(db_path)["tables"]
    with closing(sqlite3.connect(db_path)) as connection:
        assert (
            connection.execute(
                "select version, checksum from ari_schema_migrations order by version"
            ).fetchall()
            == original_checksums
        )


def test_checksums_match_the_unchanged_file_bytes(scratch: Path) -> None:
    import hashlib

    db_path = scratch / "a.db"
    initialize_database(db_path=db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        recorded = dict(connection.execute("select version, checksum from ari_schema_migrations"))
    assert recorded == {
        version: hashlib.sha256(
            (MIGRATIONS_DIR / f"{version}.sql").read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        for version in VERSIONS
    }
