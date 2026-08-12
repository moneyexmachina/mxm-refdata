"""PostgreSQL integration test for complete refdata materialisation.

This test exercises the real materialisation capability against a disposable
PostgreSQL schema using a small synthetic futures-product source universe.

It proves that the normal source adapter, source revision resolution, period
generation, period-cycle construction, trading-calendar validation, futures
contract generation, packaged migrations, and plain-SQL persistence compose
into one coherent materialised reference-data state.

Lifecycle behaviour such as repeated build, conflict rollback, and destructive
rebuild is tested separately.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from mxm.config import MXMConfig
from mxm.refdata.materialisation import build_refdata
from mxm.refdata.sources.futures_product import (
    load_futures_products,
    resolve_futures_product_source_revision,
)
from mxm.refdata.sql.futures_contracts import fetch_futures_contracts
from mxm.refdata.sql.futures_products import (
    fetch_futures_product_sources,
    fetch_futures_products,
)
from mxm.refdata.sql.period_cycles import (
    fetch_period_cycle_memberships,
    fetch_period_cycles,
)
from mxm.refdata.sql.periods import fetch_periods
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres

_FIXTURE_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "futures_products"
)

_PRODUCT_ID = "test_quarterly_futures"

_EXPECTED_PERIOD_IDS = {
    "2024",
    "2024-Q1",
    "2024-Q2",
    "2024-Q3",
    "2024-Q4",
    "Jan-2024",
    "Feb-2024",
    "Mar-2024",
    "Apr-2024",
    "May-2024",
    "Jun-2024",
    "Jul-2024",
    "Aug-2024",
    "Sep-2024",
    "Oct-2024",
    "Nov-2024",
    "Dec-2024",
}

_EXPECTED_CONTRACT_IDS = {
    f"{_PRODUCT_ID}.Mar-2024",
    f"{_PRODUCT_ID}.Jun-2024",
    f"{_PRODUCT_ID}.Sep-2024",
    f"{_PRODUCT_ID}.Dec-2024",
}


def _config() -> MXMConfig:
    """Return the controlled configuration for materialisation integration."""

    return cast(
        MXMConfig,
        {
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(_FIXTURE_SOURCE_ROOT),
            "REFDATA_CONTRACT_START_DATE": "2024-01-01",
            "REFDATA_CONTRACT_END_DATE": "2024-12-31",
        },
    )


def test_build_refdata_materialises_complete_synthetic_state(
    postgres_database: PostgresDatabase,
) -> None:
    """A synthetic source universe materialises coherently into PostgreSQL."""

    database = postgres_database

    source_records = load_futures_products(_FIXTURE_SOURCE_ROOT)

    assert len(source_records) == 1

    source_record = source_records[0]

    assert source_record.product.product_id == _PRODUCT_ID

    expected_source_revision = resolve_futures_product_source_revision(
        _FIXTURE_SOURCE_ROOT
    )

    build_refdata(
        config=_config(),
        database=database,
    )

    with database.transaction() as connection:
        periods = fetch_periods(
            connection,
            schema=database.schema,
        )

        cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )

        memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

        products = fetch_futures_products(
            connection,
            schema=database.schema,
        )

        product_sources = fetch_futures_product_sources(
            connection,
            schema=database.schema,
        )

        contracts = fetch_futures_contracts(
            connection,
            schema=database.schema,
        )

    # ------------------------------------------------------------------
    # Complete generated calendar state
    # ------------------------------------------------------------------

    assert set(periods) == _EXPECTED_PERIOD_IDS
    assert len(periods) == 17

    assert set(cycles) == {
        "CALENDAR_MONTHS",
        "CALENDAR_QUARTERS",
    }

    assert cycles["CALENDAR_MONTHS"].cycle_size == 12
    assert cycles["CALENDAR_QUARTERS"].cycle_size == 4

    assert len(memberships) == 16

    month_memberships = {
        period_id: membership
        for (
            cycle_id,
            period_id,
        ), membership in memberships.items()
        if cycle_id == "CALENDAR_MONTHS"
    }

    quarter_memberships = {
        period_id: membership
        for (
            cycle_id,
            period_id,
        ), membership in memberships.items()
        if cycle_id == "CALENDAR_QUARTERS"
    }

    assert set(month_memberships) == {
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
        "Apr-2024",
        "May-2024",
        "Jun-2024",
        "Jul-2024",
        "Aug-2024",
        "Sep-2024",
        "Oct-2024",
        "Nov-2024",
        "Dec-2024",
    }

    assert set(quarter_memberships) == {
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
    }

    # ------------------------------------------------------------------
    # Operational product and source provenance
    # ------------------------------------------------------------------

    assert products == {
        _PRODUCT_ID: source_record.product,
    }

    assert set(product_sources) == {
        _PRODUCT_ID,
    }

    persisted_metadata, persisted_revision = product_sources[_PRODUCT_ID]

    assert persisted_metadata == source_record.metadata
    assert persisted_metadata.source_relative_path == ("test_quarterly_futures.json")
    assert persisted_revision == expected_source_revision

    # ------------------------------------------------------------------
    # Generated futures contracts
    # ------------------------------------------------------------------

    assert set(contracts) == _EXPECTED_CONTRACT_IDS
    assert len(contracts) == 4

    expected_contract_periods = {
        "Mar-2024",
        "Jun-2024",
        "Sep-2024",
        "Dec-2024",
    }

    assert {
        contract.period_id for contract in contracts.values()
    } == expected_contract_periods

    for contract in contracts.values():
        assert contract.product_id == _PRODUCT_ID
        assert contract.contract_id == (f"{contract.product_id}.{contract.period_id}")
        assert contract.contract_size == (source_record.product.contract_size)
        assert contract.currency == source_record.product.currency
        assert contract.unit == source_record.product.unit
        assert contract.trading_calendar == (source_record.product.trading_calendar)
        assert contract.first_day_of_interest <= (contract.last_trading_day)
