import datetime

import pytest

from mxm.refdata.services.period_factory import PeriodFactory
from mxm.refdata.trading_calendars.last_trading_day import calculate_last_trading_day
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


@pytest.fixture
def trading_calendar():
    """Fixture for initializing a trading calendar (CME example)."""
    return TradingCalendar("CME")


@pytest.mark.parametrize(
    "product_id, period_id, expected",
    [
        # ---- Test cases for business day-based termination ----
        (
            "comex_gold_futures",
            "Jun-2025",
            datetime.date(2025, 6, 26),
        ),  # 3rd last business day
        (
            "nymex_natural_gas_futures",
            "Jun-2025",
            datetime.date(2025, 5, 28),
        ),  # 3rd last business day of previous month
        # ---- Test cases for calendar day-based termination ----
        (
            "cbot_corn_futures",
            "Jun-2025",
            datetime.date(2025, 6, 13),
        ),  # 1 business day before 15th
        # ---- Test cases for weekday-based termination ----
        (
            "cme_gbp_futures",
            "Jun-2025",
            datetime.date(2025, 6, 16),
        ),  # 2 business days before 3rd Wednesday
        (
            "cme_emini_snp500_futures",
            "Jun-2025",
            datetime.date(2025, 6, 20),
        ),  # 3rd Friday (if not business day, move back)
    ],
)
def test_calculate_last_trading_day(product_id, period_id, expected, trading_calendar):
    """Test calculating the last trading day based on different rule types."""
    period = PeriodFactory.get_period(period_id=period_id)
    assert calculate_last_trading_day(product_id, period, trading_calendar) == expected


def test_missing_trading_rule(trading_calendar):
    """Test error handling when product_id is missing from trading rules."""
    period = PeriodFactory.get_period(period_id="Jun-2025")
    with pytest.raises(KeyError):
        calculate_last_trading_day("unknown_futures", period, trading_calendar)
