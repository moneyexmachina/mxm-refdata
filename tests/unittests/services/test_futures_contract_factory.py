"""Unit tests for FuturesContractFactory's create_contracts_for_product method."""

from datetime import date
from unittest.mock import patch

import pytest

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.services.futures_contract_factory import FuturesContractFactory


@pytest.fixture
def contract_factory():
    """Fixture to create a FuturesContractFactory instance."""
    return FuturesContractFactory()


@pytest.fixture
def mock_periods():
    """Fixture to generate a dictionary of periods (id -> Period object) for a given year."""
    periods = {
        f"{date(2024, month, 1).strftime('%b-%Y')}": Period(
            period_id=f"{date(2024, month, 1).strftime('%b-%Y')}",
            period_type=PeriodType.MONTH,
            first_date=date(2024, month, 1),
            last_date=date(2024, month, 28),  # Simplified last date
        )
        for month in range(1, 13)
    }
    return periods


@pytest.fixture
def all_months_product():
    """Fixture for a product where contracts are listed for all months."""
    return FuturesProduct(
        product_id="ALL_MONTHS",
        venue="CME",
        description="All Monthly Contracts Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        listing_rule="All monthly contracts listed",
        period_types=PeriodType.MONTH,
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="FGHJKMNQUVXZ",  # All months allowed
    )


@pytest.fixture
def partial_months_product():
    """Fixture for a product that only has contracts for Feb, Apr, Jul, Dec."""
    return FuturesProduct(
        product_id="PARTIAL_MONTHS",
        venue="CME",
        description="Partial Monthly Contracts Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        listing_rule="Limited monthly contracts listed",
        period_types=PeriodType.MONTH,
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="GJNV",  # Feb, Apr, Jul, Oct
    )


@pytest.fixture
def quarterly_product():
    """Fixture for a product with contracts only in March, June, Sep, Dec."""
    return FuturesProduct(
        product_id="QUARTERLY",
        venue="CME",
        description="Quarterly Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        listing_rule="Quarterly contracts listed",
        period_types=PeriodType.MONTH,
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="HMUZ",  # March, June, Sep, Dec
    )


@pytest.fixture
def mock_trading_rules():
    """Mock trading rules for test products."""
    return {
        "ALL_MONTHS": {
            "period_offset": 0,
            "reference_event": "business_day_of_period",
            "n_reference": -3,
            "business_day_offset": 0,
        },
        "PARTIAL_MONTHS": {
            "period_offset": 0,
            "reference_event": "calendar_day_of_period",
            "n_reference": 15,
            "business_day_offset": -1,
        },
        "QUARTERLY": {
            "period_offset": 0,
            "reference_event": "weekday_of_period",
            "n_reference": 3,
            "weekday": "Friday",
            "business_day_offset": 0,
        },
    }


@pytest.fixture
def mock_first_day_of_interest_rules():
    """Mock first_day_of_interest rules for test products."""
    return {
        "ALL_MONTHS": {
            "shift_rule": {
                "shift_period_type": "MONTH",
                "n_shift": {
                    "Jan": 0,
                    "Feb": 0,
                    "Mar": 0,
                    "Apr": 0,
                    "May": 0,
                    "Jun": 0,
                    "Jul": 0,
                    "Aug": 0,
                    "Sep": 0,
                    "Oct": 0,
                    "Nov": 0,
                    "Dec": 0,
                },
            },
            "reference_rule": "next_b_day_after_period",
        },
        "PARTIAL_MONTHS": {
            "shift_rule": {
                "shift_period_type": "MONTH",
                "n_shift": {
                    "Jan": 0,
                    "Feb": 0,
                    "Mar": 0,
                    "Apr": 0,
                    "May": 0,
                    "Jun": 0,
                    "Jul": 0,
                    "Aug": 0,
                    "Sep": 0,
                    "Oct": 0,
                    "Nov": 0,
                    "Dec": 0,
                },
            },
            "reference_rule": "next_b_day_after_last_trading_day_of_december",
        },
        "QUARTERLY": {
            "shift_rule": {
                "shift_period_type": "MONTH",
                "n_shift": {
                    "Mar": 21 * 3,  # 21 quarters = 63 months
                    "Jun": 21 * 3,
                    "Sep": 21 * 3,
                    "Dec": 21 * 3,
                    "default": 0,  # Other months should not exist in a QUARTERLY product
                },
            },
            "reference_rule": "next_b_day_after_period",
        },
    }


@pytest.fixture
def patched_trading_rules(mock_trading_rules):
    """Patch TRADING_RULES so test products have valid trading rules."""
    with patch(
        "mxm_refdata.trading_calendars.last_trading_day.TRADING_RULES",
        mock_trading_rules,
    ):
        yield


@pytest.fixture
def patched_first_day_of_interest_rules(mock_first_day_of_interest_rules):
    """Patch TRADING_RULES so test products have valid trading rules."""
    with patch(
        "mxm_refdata.trading_calendars.first_day_of_interest.FIRST_DAY_OF_INTEREST_RULES",
        mock_first_day_of_interest_rules,
    ):
        yield


def test_create_contracts_for_product_all_months(
    contract_factory,
    all_months_product,
    mock_periods,
    patched_trading_rules,
    patched_first_day_of_interest_rules,
):
    """Test contract creation for a product allowing all months."""
    contracts = contract_factory.create_contracts_for_product(
        all_months_product, mock_periods
    )

    assert len(contracts) == 12, "Expected 12 contracts (one per month)."
    expected_ids = [
        f"{all_months_product.product_id}.{date(2024, month, 1).strftime('%b-%Y')}"
        for month in range(1, 13)
    ]
    generated_ids = [contract.contract_id for contract in contracts]

    assert set(generated_ids) == set(expected_ids), "Mismatch in contract IDs."


def test_create_contracts_for_product_partial_months(
    contract_factory,
    partial_months_product,
    mock_periods,
    patched_trading_rules,
    patched_first_day_of_interest_rules,
):
    """Test contract creation for a product with only selected months."""
    contracts = contract_factory.create_contracts_for_product(
        partial_months_product, mock_periods
    )

    assert len(contracts) == 4, "Expected 4 contracts (Feb, Apr, Jul, Nov)."
    expected_ids = [
        f"{partial_months_product.product_id}.{date(2024, month, 1).strftime('%b-%Y')}"
        for month in [2, 4, 7, 10]
    ]
    generated_ids = [contract.contract_id for contract in contracts]

    assert set(generated_ids) == set(expected_ids), "Mismatch in contract IDs."


def test_create_contracts_for_product_quarterly(
    contract_factory,
    quarterly_product,
    mock_periods,
    patched_trading_rules,
    patched_first_day_of_interest_rules,
):
    """Test contract creation for a product with only Mar, Jun, Sep, Dec months."""
    contracts = contract_factory.create_contracts_for_product(
        quarterly_product, mock_periods
    )

    assert len(contracts) == 4, "Expected 4 contracts (March, June, Sep, Dec)."
    expected_ids = [
        f"{quarterly_product.product_id}.{date(2024, month, 1).strftime('%b-%Y')}"
        for month in [3, 6, 9, 12]
    ]
    generated_ids = [contract.contract_id for contract in contracts]

    assert set(generated_ids) == set(expected_ids), "Mismatch in contract IDs."
