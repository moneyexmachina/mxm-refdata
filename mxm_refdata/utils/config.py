"""Configuration details for the refData application."""

from __future__ import annotations

from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


def _default_sqlite_db_url() -> str:
    # Stable, user-writable default (avoid process-relative paths)
    db_path = Path.home() / ".mxm" / "refdata" / "refdata.db"
    return f"sqlite:///{db_path}"


class Config(BaseSettings):
    # Overrideable via env; default is safe when imported as a dependency
    SQL_DB_URL: str = _default_sqlite_db_url()

    # None means "use packaged CSV resource"
    REFDATA_FUTURES_PRODUCTS_CSV_PATH: str | None = None

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


def load_config() -> Config:
    return Config()
