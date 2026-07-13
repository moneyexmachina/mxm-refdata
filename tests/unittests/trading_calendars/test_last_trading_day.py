"""Unit tests for last-trading-day calculation."""

from __future__ import annotations

from datetime import date

import pytest

from mxm.refdata.factories.period_factory import PeriodFactory
from mxm.refdata.models.products.futures_product_spec import LastTradingRule
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.trading_calendars.last_trading_day import (
    calculate_last_trading_day,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


@pytest.fixture
def trading_calendar() -> TradingCalendar:
    """Return a CME trading calendar."""

    return TradingCalendar("CME")


@pytest.mark.parametrize(
    (
        "product_id",
        "period_id",
        "rule",
        "expected",
    ),
    [
        pytest.param(
            "comex_gold_futures",
            "Jun-2025",
            LastTradingRule(
                period_offset=0,
                reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
                n_reference=-3,
                business_day_offset=0,
            ),
            date(2025, 6, 26),
            id="third-last-business-day",
        ),
        pytest.param(
            "nymex_natural_gas_futures",
            "Jun-2025",
            LastTradingRule(
                period_offset=-1,
                reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
                n_reference=-3,
                business_day_offset=0,
            ),
            date(2025, 5, 28),
            id="third-last-business-day-of-previous-month",
        ),
        pytest.param(
            "cbot_corn_futures",
            "Jun-2025",
            LastTradingRule(
                period_offset=0,
                reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
                n_reference=15,
                business_day_offset=-1,
            ),
            date(2025, 6, 13),
            id="business-day-before-fifteenth-calendar-day",
        ),
        pytest.param(
            "cme_gbp_futures",
            "Jun-2025",
            LastTradingRule(
                period_offset=0,
                reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
                n_reference=3,
                business_day_offset=-2,
                weekday=Weekday.from_str("Wednesday"),
            ),
            date(2025, 6, 16),
            id="two-business-days-before-third-wednesday",
        ),
        pytest.param(
            "cme_emini_snp500_futures",
            "Jun-2025",
            LastTradingRule(
                period_offset=0,
                reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
                n_reference=3,
                business_day_offset=0,
                weekday=Weekday.from_str("Friday"),
            ),
            date(2025, 6, 20),
            id="third-friday",
        ),
    ],
)
def test_calculate_last_trading_day(
    product_id: str,
    period_id: str,
    rule: LastTradingRule,
    expected: date,
    trading_calendar: TradingCalendar,
) -> None:
    """Calculate last trading days for supported rule forms."""

    period = PeriodFactory.get_period(
        period_id=period_id,
    )

    result = calculate_last_trading_day(
        product_id=product_id,
        period=period,
        trading_calendar=trading_calendar,
        rule=rule,
    )

    assert result == expected


def test_business_day_offset_moves_from_reference_date(
    trading_calendar: TradingCalendar,
) -> None:
    """Apply the business-day offset after resolving the reference date."""

    period = PeriodFactory.get_period(
        period_id="Jun-2025",
    )
    rule = LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
        n_reference=15,
        business_day_offset=2,
    )

    result = calculate_last_trading_day(
        product_id="test_product",
        period=period,
        trading_calendar=trading_calendar,
        rule=rule,
    )

    assert result == date(2025, 6, 17)


def test_period_offset_is_applied_before_reference_date_resolution(
    trading_calendar: TradingCalendar,
) -> None:
    """Shift the contract period before resolving the reference event."""

    period = PeriodFactory.get_period(
        period_id="Jun-2025",
    )
    rule = LastTradingRule(
        period_offset=-1,
        reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
        n_reference=15,
        business_day_offset=0,
    )

    result = calculate_last_trading_day(
        product_id="test_product",
        period=period,
        trading_calendar=trading_calendar,
        rule=rule,
    )

    assert result == date(2025, 5, 15)
