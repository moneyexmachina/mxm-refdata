"""Tests for mxm-refdata configuration data helpers."""

from __future__ import annotations

import pytest

from mxm.refdata.config import normalise_refdata_config_data


def test_normalise_refdata_config_data_fills_defaults() -> None:
    """Normalisation should fill optional refdata config fields."""
    cfg = normalise_refdata_config_data(
        {
            "SQL_DB_URL": "sqlite:////tmp/refdata.db",
        }
    )

    assert cfg["SQL_DB_URL"] == "sqlite:////tmp/refdata.db"
    assert cfg["REFDATA_DB_MODE"] == "buildable"
    assert cfg["REFDATA_CONTRACT_START_DATE"] == "1980-01-02"
    assert cfg["REFDATA_CONTRACT_END_DATE"] == "2046-12-31"
    assert cfg["REFDATA_FUTURES_PRODUCTS_CSV_PATH"].endswith(
        "data/futures_products.csv"
    )


def test_normalise_refdata_config_data_preserves_explicit_values() -> None:
    """Normalisation should preserve explicitly supplied values."""
    cfg = normalise_refdata_config_data(
        {
            "SQL_DB_URL": "postgresql://user:password@localhost/refdata",
            "REFDATA_DB_MODE": "managed",
            "REFDATA_FUTURES_PRODUCTS_CSV_PATH": "/tmp/products.csv",
            "REFDATA_CONTRACT_START_DATE": "2000-01-01",
            "REFDATA_CONTRACT_END_DATE": "2050-12-31",
        }
    )

    assert cfg == {
        "SQL_DB_URL": "postgresql://user:password@localhost/refdata",
        "REFDATA_DB_MODE": "managed",
        "REFDATA_FUTURES_PRODUCTS_CSV_PATH": "/tmp/products.csv",
        "REFDATA_CONTRACT_START_DATE": "2000-01-01",
        "REFDATA_CONTRACT_END_DATE": "2050-12-31",
    }


def test_normalise_refdata_config_data_rejects_invalid_db_mode() -> None:
    """Normalisation should reject unknown refdata DB modes."""
    with pytest.raises(ValueError, match="REFDATA_DB_MODE"):
        normalise_refdata_config_data(
            {
                "SQL_DB_URL": "sqlite:////tmp/refdata.db",
                "REFDATA_DB_MODE": "invalid",
            }
        )
