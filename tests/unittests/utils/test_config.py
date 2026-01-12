import os
from pathlib import Path

from mxm_refdata.utils.config import load_config


def _clear_env(var: str):
    """Helper to temporarily clear an environment variable."""
    original = os.getenv(var)
    if original is not None:
        del os.environ[var]
    return original


def _restore_env(var: str, value: str | None):
    if value is not None:
        os.environ[var] = value


def test_load_config_default():
    """Default config uses a stable, user-writable SQLite location."""
    original = _clear_env("SQL_DB_URL")

    try:
        cfg = load_config()

        # Must be SQLite
        assert cfg.SQL_DB_URL.startswith("sqlite:///")

        # Must not be process-relative (old fragile default)
        assert cfg.SQL_DB_URL != "sqlite:///data/refdata.db"

        # Extract filesystem path
        db_path = Path(cfg.SQL_DB_URL.removeprefix("sqlite:///"))

        # Path should be absolute and deterministic
        assert db_path.is_absolute()
        assert db_path.name == "refdata.db"

    finally:
        _restore_env("SQL_DB_URL", original)


def test_load_config_env_variable():
    """Environment variable overrides the default."""
    original = _clear_env("SQL_DB_URL")

    try:
        os.environ["SQL_DB_URL"] = (
            "postgresql://test_user:test_password@localhost/test_db"
        )

        cfg = load_config()

        assert (
            cfg.SQL_DB_URL == "postgresql://test_user:test_password@localhost/test_db"
        )

    finally:
        _restore_env("SQL_DB_URL", original)
