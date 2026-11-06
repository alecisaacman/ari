"""The test suite can't open live ARI's databases, whatever live ARI does meanwhile."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import LIVE_DATABASE_DIRS, LiveStateAccessError
from sqlalchemy import create_engine, text

LIVE_DB = Path.home() / "ARI" / "modules" / "networking-crm" / "state" / "networking.db"


def test_live_ari_databases_are_off_limits_to_tests() -> None:
    assert any(LIVE_DB.resolve(strict=False).is_relative_to(root) for root in LIVE_DATABASE_DIRS)
    with pytest.raises(LiveStateAccessError):
        sqlite3.connect(LIVE_DB)
    with pytest.raises(LiveStateAccessError):
        sqlite3.connect(f"file:{Path.home() / 'ARI' / 'state' / 'ari.db'}?mode=ro", uri=True)


def test_sqlalchemy_is_guarded_too() -> None:
    engine = create_engine(f"sqlite+pysqlite:///{LIVE_DB}")
    with pytest.raises(Exception) as caught, engine.connect() as connection:
        connection.execute(text("select 1"))
    assert "live ARI state" in str(caught.value)


def test_tests_own_databases_still_open(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "mine.db") as connection:
        assert connection.execute("select 1").fetchone() == (1,)
    with sqlite3.connect(":memory:") as connection:
        assert connection.execute("select 2").fetchone() == (2,)
