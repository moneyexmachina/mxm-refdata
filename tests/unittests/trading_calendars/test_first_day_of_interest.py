"""Tests for the first_day_of_interest module."""

from datetime import date

import pytest

from mxm.refdata.services.period_factory import PeriodFactory
from mxm.refdata.trading_calendars.first_day_of_interest import (
    calculate_first_day_of_interest,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


@pytest.fixture
def trading_calendar():
    """Fixture to provide a TradingCalendar instance."""
    return TradingCalendar("CME", start=date(2010, 1, 1), end=date(2039, 12, 31))


@pytest.mark.parametrize(
    "product_id, period_id, expected_first_day",
    [
        # Gold Futures (COMEX) - Monthly listing rule
        ("comex_gold_futures", "Jun-2027", date(2021, 7, 1)),  # 72-month shift for Jun
        ("comex_gold_futures", "Feb-2027", date(2025, 3, 3)),  # 24-month shift for Feb
        # Corn Futures (CBOT) - Annual batch listing rule
        (
            "cbot_corn_futures",
            "Mar-2029",
            date(2026, 12, 15),
        ),  # 3-year shift to Dec 2026
        (
            "cbot_corn_futures",
            "Jul-2028",
            date(2024, 12, 16),
        ),  # 4-year shift to Dec 2024
        # British Pound Futures (CME) - Quarterly & serial contracts
        ("cme_gbp_futures", "Mar-2030", date(2025, 4, 1)),  # 20 quarters = 5 years
        ("cme_gbp_futures", "Aug-2029", date(2029, 6, 1)),  # 3-month serial shift
        # E-mini S&P 500 Futures (CME) - 21-quarter shift
        ("cme_emini_snp500_futures", "Dec-2030", date(2025, 10, 1)),  # 21-quarter shift
        # Natural Gas Futures (NYMEX) - 12-year shift
        (
            "nymex_natural_gas_futures",
            "Sep-2035",
            date(2023, 11, 29),
        ),
    ],
)
def test_calculate_first_day_of_interest(
    product_id, period_id, expected_first_day, trading_calendar
):
    """Test first_day_of_interest calculations for all test products."""
    period = PeriodFactory.get_period(period_id)
    first_day = calculate_first_day_of_interest(product_id, period, trading_calendar)
    assert first_day == expected_first_day, (
        f"Expected {expected_first_day}, got {first_day}"
    )


def test_invalid_product_id(trading_calendar):
    """Test that ValueError is raised if the product_id is not found in the JSON file."""
    invalid_product_id = "non_existent_product"
    period = PeriodFactory.get_period(period_id="Jun-2027")

    with pytest.raises(
        ValueError,
        match="No first_day_of_interest rule found for product_id: non_existent_product",
    ):
        calculate_first_day_of_interest(invalid_product_id, period, trading_calendar)


def test_invalid_period_type(trading_calendar):
    """Test that ValueError is raised if period_type is not MONTH."""
    valid_product_id = "comex_gold_futures"

    # Quarterly period (should raise ValueError)
    invalid_period = PeriodFactory.get_period(period_id="2027-Q2")

    with pytest.raises(ValueError, match="Unsupported period_type: PeriodType.QUARTER"):
        calculate_first_day_of_interest(
            valid_product_id, invalid_period, trading_calendar
        )


def test_missing_month_in_rules(trading_calendar):
    """Test that KeyError is raised if a contract month is missing from the JSON rules."""
    product_id = "cbot_corn_futures"

    # Assume "Apr" is missing in our test JSON file
    period = PeriodFactory.get_period(period_id="Apr-2027")

    with pytest.raises(
        KeyError,
        match="No shift value found for month 'Apr' in product_id: cbot_corn_futures",
    ):
        calculate_first_day_of_interest(product_id, period, trading_calendar)
