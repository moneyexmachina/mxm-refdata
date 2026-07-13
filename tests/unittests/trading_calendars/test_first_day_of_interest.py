"""Tests for first-day-of-interest calculation."""

from __future__ import annotations

from datetime import date

import pytest

from mxm.refdata.factories import PeriodFactory
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product_spec import (
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.trading_calendars.first_day_of_interest import (
    calculate_first_day_of_interest,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


@pytest.fixture
def trading_calendar() -> TradingCalendar:
    """Provide a CME trading calendar."""

    return TradingCalendar("CME")


def _first_day_rule(
    *,
    n_shift: dict[str, int],
    reference_rule: str = "next_b_day_after_period",
) -> FirstDayOfInterestRule:
    """Construct a first-day-of-interest rule for a test case."""

    return FirstDayOfInterestRule(
        shift_rule=FirstDayOfInterestShiftRule(
            shift_period_type=PeriodType.MONTH,
            n_shift=n_shift,
        ),
        reference_rule=reference_rule,
    )


def _unused_last_trading_rule() -> LastTradingRule:
    """Return a valid rule for cases that do not use last trading day."""

    return LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
        n_reference=-1,
        business_day_offset=0,
    )


@pytest.mark.parametrize(
    (
        "product_id",
        "period_id",
        "rule",
        "last_trading_rule",
        "expected",
    ),
    [
        pytest.param(
            "comex_gold_futures",
            "Jun-2027",
            _first_day_rule(
                n_shift={"Jun": 72},
            ),
            _unused_last_trading_rule(),
            date(2021, 7, 1),
            id="gold-june-72-month-shift",
        ),
        pytest.param(
            "comex_gold_futures",
            "Feb-2027",
            _first_day_rule(
                n_shift={"Feb": 24},
            ),
            _unused_last_trading_rule(),
            date(2025, 3, 3),
            id="gold-february-24-month-shift",
        ),
        pytest.param(
            "cbot_corn_futures",
            "Mar-2029",
            _first_day_rule(
                n_shift={"Mar": 27},
                reference_rule=("next_b_day_after_last_trading_day_of_december"),
            ),
            LastTradingRule(
                period_offset=0,
                reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
                n_reference=15,
                business_day_offset=-1,
            ),
            date(2026, 12, 15),
            id="corn-march-annual-listing",
        ),
        pytest.param(
            "cbot_corn_futures",
            "Jul-2028",
            _first_day_rule(
                n_shift={"Jul": 43},
                reference_rule=("next_b_day_after_last_trading_day_of_december"),
            ),
            LastTradingRule(
                period_offset=0,
                reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
                n_reference=15,
                business_day_offset=-1,
            ),
            date(2024, 12, 16),
            id="corn-july-annual-listing",
        ),
        pytest.param(
            "cme_gbp_futures",
            "Mar-2030",
            _first_day_rule(
                n_shift={"Mar": 60},
            ),
            _unused_last_trading_rule(),
            date(2025, 4, 1),
            id="gbp-quarterly-contract",
        ),
        pytest.param(
            "cme_gbp_futures",
            "Aug-2029",
            _first_day_rule(
                n_shift={"Aug": 3},
            ),
            _unused_last_trading_rule(),
            date(2029, 6, 1),
            id="gbp-serial-contract",
        ),
        pytest.param(
            "cme_emini_snp500_futures",
            "Dec-2030",
            _first_day_rule(
                n_shift={"Dec": 63},
            ),
            _unused_last_trading_rule(),
            date(2025, 10, 1),
            id="emini-sp500-21-quarter-shift",
        ),
        pytest.param(
            "nymex_natural_gas_futures",
            "Sep-2035",
            _first_day_rule(
                n_shift={"Sep": 142},
                reference_rule=("next_b_day_after_last_trading_day_of_december"),
            ),
            LastTradingRule(
                period_offset=-1,
                reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
                n_reference=-3,
                business_day_offset=0,
            ),
            date(2023, 11, 29),
            id="natural-gas-long-listing-horizon",
        ),
    ],
)
def test_calculate_first_day_of_interest(
    product_id: str,
    period_id: str,
    rule: FirstDayOfInterestRule,
    last_trading_rule: LastTradingRule,
    expected: date,
    trading_calendar: TradingCalendar,
) -> None:
    """Calculate first days of interest for supported rule forms."""

    period = PeriodFactory.get_period(
        period_id=period_id,
    )

    result = calculate_first_day_of_interest(
        product_id=product_id,
        period=period,
        trading_calendar=trading_calendar,
        rule=rule,
        last_trading_rule=last_trading_rule,
    )

    assert result == expected


def test_invalid_period_type(
    trading_calendar: TradingCalendar,
) -> None:
    """Reject contract periods other than months."""

    period = PeriodFactory.get_period(
        period_id="2027-Q2",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported period_type",
    ):
        calculate_first_day_of_interest(
            product_id="test_product",
            period=period,
            trading_calendar=trading_calendar,
            rule=_first_day_rule(
                n_shift={"Jun": 24},
            ),
            last_trading_rule=_unused_last_trading_rule(),
        )


def test_missing_month_in_rule(
    trading_calendar: TradingCalendar,
) -> None:
    """Raise when the rule has no shift for the contract month."""

    period = PeriodFactory.get_period(
        period_id="Apr-2027",
    )
    rule = _first_day_rule(
        n_shift={"Mar": 36},
    )

    with pytest.raises(
        KeyError,
        match=(
            "No first-day-of-interest shift found "
            "for month 'Apr' and product_id 'cbot_corn_futures'"
        ),
    ):
        calculate_first_day_of_interest(
            product_id="cbot_corn_futures",
            period=period,
            trading_calendar=trading_calendar,
            rule=rule,
            last_trading_rule=_unused_last_trading_rule(),
        )


def test_unsupported_reference_rule(
    trading_calendar: TradingCalendar,
) -> None:
    """Reject an unsupported first-day reference rule."""

    period = PeriodFactory.get_period(
        period_id="Jun-2027",
    )
    rule = _first_day_rule(
        n_shift={"Jun": 24},
        reference_rule="unsupported_reference",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported first-day-of-interest reference_rule",
    ):
        calculate_first_day_of_interest(
            product_id="test_product",
            period=period,
            trading_calendar=trading_calendar,
            rule=rule,
            last_trading_rule=_unused_last_trading_rule(),
        )
