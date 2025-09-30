import os

from mxm_refdata.utils.config import load_config


def test_load_config_default():
    """Test loading config with default values."""
    # Clear the DATABASE_URL environment variable if set
    original_value = os.getenv("SQL_DB_URL")
    if original_value is not None:
        del os.environ["SQL_DB_URL"]

    # Load config
    config = load_config()

    # Assert the default value
    assert config.SQL_DB_URL == "sqlite:///data/refdata.db"

    # Restore the original value
    if original_value:
        os.environ["SQL_DB_URL"] = original_value


def test_load_config_env_variable():
    """Test loading config with DATABASE_URL set in environment."""
    # Set a custom DATABASE_URL environment variable
    os.environ["SQL_DB_URL"] = "postgresql://test_user:test_password@localhost/test_db"

    # Load config
    config = load_config()

    # Assert the value from the environment variable
    assert config.SQL_DB_URL == "postgresql://test_user:test_password@localhost/test_db"

    # Clean up the environment variable
    del os.environ["SQL_DB_URL"]
