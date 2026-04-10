from sqlalchemy import Engine, create_engine as sqlalchemy_create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine(database_url: str) -> Engine:
    return sqlalchemy_create_engine(database_url, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
