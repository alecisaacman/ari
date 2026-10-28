from pathlib import Path

from sqlalchemy import Engine, MetaData, inspect, make_url, text
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
    _add_missing_nullable_columns(engine, Base.metadata)


def _add_missing_nullable_columns(engine: Engine, metadata: MetaData) -> None:
    """Give an existing SQLite table the nullable columns added to it since it was made.

    create_all only makes missing tables. SQLite can add a nullable column in place,
    so a new optional field reaches a live store without rebuilding it.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or not column.nullable:
                    continue
                kind = column.type.compile(dialect=engine.dialect)
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}'))
