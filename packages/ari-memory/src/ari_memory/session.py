from pathlib import Path

from sqlalchemy import Engine, make_url
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine(database_url: str) -> Engine:
    engine = sqlalchemy_create_engine(database_url, future=True)
    _initialize_sqlite_file(engine)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _initialize_sqlite_file(engine: Engine) -> None:
    """Create a file-based SQLite store's directory and any missing tables.

    The Alembic history targets Postgres and alters constraints in place, which
    SQLite cannot do, so a SQLite store is built from the current table metadata.
    In-memory databases are left to their callers.
    """
    url = make_url(str(engine.url))
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return
    Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    from ari_memory.tables import Base

    Base.metadata.create_all(engine)
