"""Tests for the get_nth_business_day_of_period function."""

import datetime

import pytest

from mxm.refdata.services.period_factory import PeriodFactory
from mxm.refdata.trading_calendars.nth_business_day import (
    get_nth_business_day_of_period,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


@pytest.fixture
def trading_calendar():
    """Fixture for initializing a trading calendar (CME example)."""
    return TradingCalendar("CME")


@pytest.mark.parametrize(
    "period_id, n, expected",
    [
        # ---- Test cases for contract months (June 2025) ----
        ("Jun-2025", 1, datetime.date(2025, 6, 2)),  # First business day
        ("Jun-2025", 5, datetime.date(2025, 6, 6)),  # Fifth business day
        ("Jun-2025", -1, datetime.date(2025, 6, 30)),  # Last business day
        ("Jun-2025", -5, datetime.date(2025, 6, 24)),  # Fifth-last business day
        # ---- Test cases for quarter periods (Q3 2025) ----
        ("2025-Q3", 1, datetime.date(2025, 7, 1)),  # First business day of Q3 2025
        ("2025-Q3", 10, datetime.date(2025, 7, 14)),  # Tenth business day
        ("2025-Q3", -1, datetime.date(2025, 9, 30)),  # Last business day of Q3 2025
        ("2025-Q3", -10, datetime.date(2025, 9, 17)),  # Tenth-last business day
    ],
)
def test_get_nth_business_day_of_period(period_id, n, expected, trading_calendar):
    """Test retrieving the N-th business day of a period."""
    period = PeriodFactory.get_period(period_id=period_id)
    assert get_nth_business_day_of_period(period, n, trading_calendar) == expected


def test_invalid_n(trading_calendar):
    """Test that out-of-range N values raise a ValueError."""
    period = PeriodFactory.get_period(period_id="Jun-2025")
    with pytest.raises(ValueError):
        get_nth_business_day_of_period(
            period, 25, trading_calendar
        )  # More business days than exist
    with pytest.raises(ValueError):
        get_nth_business_day_of_period(
            period, -25, trading_calendar
        )  # More negative indexing than possible
