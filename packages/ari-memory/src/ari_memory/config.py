import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_url() -> str:
    """ARI's local state store: one SQLite file under ARI_HOME, so ARI needs no server."""
    ari_home = Path(os.environ.get("ARI_HOME", str(Path.home() / "ARI"))).expanduser()
    return f"sqlite+pysqlite:///{ari_home / 'state' / 'ari.db'}"


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DATABASE_URL still selects another database, such as Postgres.
    database_url: str = Field(default_factory=default_database_url, alias="DATABASE_URL")
