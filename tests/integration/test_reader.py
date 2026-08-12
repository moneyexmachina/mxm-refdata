"""Integration tests for the materialised reference-data reader capability.

These tests exercise ``RefDataReader`` against a complete synthetic
reference-data state materialised through the real application path into a
disposable PostgreSQL schema.

They prove that the Reader composes the real persistence adapters into the
consumer-facing capabilities promised by its public API: complete domain
reads and ordering, period-cycle semantics, and active-contract selection.

Pure Reader policies such as missing-value behaviour, input-order
reconstruction, argument validation, and period-type parsing are tested
separately by the Reader unit tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest

from mxm.config import MXMConfig
from mxm.refdata.materialisation import build_refdata
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sources.futures_product import load_futures_products
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres

_FIXTURE_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "futures_products"
)

_PRODUCT_ID = "test_quarterly_futures"

_EXPECTED_PERIOD_IDS = [
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
]

_EXPECTED_CONTRACT_PERIOD_IDS = [
    "Mar-2024",
    "Jun-2024",
    "Sep-2024",
    "Dec-2024",
]


def _config() -> MXMConfig:
    """Return the controlled configuration for Reader integration."""

    return cast(
        MXMConfig,
        {
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(_FIXTURE_SOURCE_ROOT),
            "REFDATA_CONTRACT_START_DATE": "2024-01-01",
            "REFDATA_CONTRACT_END_DATE": "2024-12-31",
        },
    )


def _materialise_reader(
    database: PostgresDatabase,
) -> RefDataReader:
    """Materialise the synthetic universe and return its real Reader."""

    build_refdata(
        config=_config(),
        database=database,
    )

    return RefDataReader(
        database=database,
    )


def test_reader_exposes_complete_materialised_reference_data(
    postgres_database: PostgresDatabase,
) -> None:
    """Reader exposes complete domain values in consumer-facing order."""

    source_records = load_futures_products(_FIXTURE_SOURCE_ROOT)

    assert len(source_records) == 1

    expected_product = source_records[0].product

    reader = _materialise_reader(postgres_database)

    products = reader.get_products()

    assert products == [
        expected_product,
    ]

    assert reader.get_product_by_id(_PRODUCT_ID) == expected_product

    periods = reader.get_periods()

    assert [period.period_id for period in periods] == _EXPECTED_PERIOD_IDS

    march = reader.get_period_by_id("Mar-2024")

    assert march is not None
    assert march.period_id == "Mar-2024"
    assert march.first_date == date(
        2024,
        3,
        1,
    )
    assert march.last_date == date(
        2024,
        3,
        31,
    )

    cycles = reader.get_cycles()

    assert [cycle.cycle_id for cycle in cycles] == [
        "CALENDAR_MONTHS",
        "CALENDAR_QUARTERS",
    ]

    month_cycle = reader.get_cycle_by_id("CALENDAR_MONTHS")

    assert month_cycle is not None
    assert month_cycle.cycle_size == 12

    contracts = reader.get_contracts_for_product(_PRODUCT_ID)

    assert [
        contract.period_id for contract in contracts
    ] == _EXPECTED_CONTRACT_PERIOD_IDS

    assert [contract.contract_id for contract in contracts] == [
        f"{_PRODUCT_ID}.Mar-2024",
        f"{_PRODUCT_ID}.Jun-2024",
        f"{_PRODUCT_ID}.Sep-2024",
        f"{_PRODUCT_ID}.Dec-2024",
    ]

    june_contract = reader.get_contract_by_id(f"{_PRODUCT_ID}.Jun-2024")

    assert june_contract == contracts[1]


def test_reader_exposes_period_cycle_semantics(
    postgres_database: PostgresDatabase,
) -> None:
    """Reader exposes ordered memberships and cycle-element projections."""

    reader = _materialise_reader(postgres_database)

    month_memberships = reader.get_cycle_memberships("CALENDAR_MONTHS")

    assert [
        (
            membership.period_id,
            membership.cycle_instance,
            membership.cycle_element,
        )
        for membership in month_memberships
    ] == [
        (
            "Jan-2024",
            2024,
            1,
        ),
        (
            "Feb-2024",
            2024,
            2,
        ),
        (
            "Mar-2024",
            2024,
            3,
        ),
        (
            "Apr-2024",
            2024,
            4,
        ),
        (
            "May-2024",
            2024,
            5,
        ),
        (
            "Jun-2024",
            2024,
            6,
        ),
        (
            "Jul-2024",
            2024,
            7,
        ),
        (
            "Aug-2024",
            2024,
            8,
        ),
        (
            "Sep-2024",
            2024,
            9,
        ),
        (
            "Oct-2024",
            2024,
            10,
        ),
        (
            "Nov-2024",
            2024,
            11,
        ),
        (
            "Dec-2024",
            2024,
            12,
        ),
    ]

    quarter_memberships = reader.get_cycle_memberships("CALENDAR_QUARTERS")

    assert [
        (
            membership.period_id,
            membership.cycle_instance,
            membership.cycle_element,
        )
        for membership in quarter_memberships
    ] == [
        (
            "2024-Q1",
            2024,
            1,
        ),
        (
            "2024-Q2",
            2024,
            2,
        ),
        (
            "2024-Q3",
            2024,
            3,
        ),
        (
            "2024-Q4",
            2024,
            4,
        ),
    ]

    month_elements = reader.get_cycle_elements(
        [
            "Sep-2024",
            "2024-Q3",
            "MISSING",
            "Mar-2024",
        ],
        cycle_id="CALENDAR_MONTHS",
    )

    assert month_elements == {
        "Mar-2024": 3,
        "Sep-2024": 9,
    }

    assert (
        reader.get_cycle_element(
            "Sep-2024",
            cycle_id="CALENDAR_MONTHS",
        )
        == 9
    )


def test_reader_selects_active_contracts_from_materialised_state(
    postgres_database: PostgresDatabase,
) -> None:
    """Reader selects and orders contracts active on a materialised date."""

    reader = _materialise_reader(postgres_database)

    contracts = reader.get_contracts_for_product(_PRODUCT_ID)

    assert [
        contract.period_id for contract in contracts
    ] == _EXPECTED_CONTRACT_PERIOD_IDS

    june_contract = reader.get_contract_by_id(f"{_PRODUCT_ID}.Jun-2024")

    as_of_date = june_contract.first_day_of_interest

    expected_active_contracts = [
        contract
        for contract in contracts
        if (contract.first_day_of_interest <= as_of_date <= contract.last_trading_day)
    ]

    assert expected_active_contracts

    active_contracts = reader.get_active_contracts(as_of_date)

    assert active_contracts == expected_active_contracts
