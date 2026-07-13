"""Calculate the last trading day for a futures contract."""

from __future__ import annotations

from datetime import date

from mxm.refdata.factories.period_factory import PeriodFactory
from mxm.refdata.models.periods import Period
from mxm.refdata.models.products.futures_product_spec import LastTradingRule
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.trading_calendars.nth_business_day import (
    get_nth_business_day_of_period,
)
from mxm.refdata.trading_calendars.nth_calendar_day_of_period import (
    get_nth_calendar_day_of_period,
)
from mxm.refdata.trading_calendars.nth_weekday_of_period import (
    get_nth_weekday_of_period,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


def get_reference_date(
    *,
    product_id: str,
    adjusted_period: Period,
    rule: LastTradingRule,
    trading_calendar: TradingCalendar,
) -> date:
    """Resolve the reference date defined by a last-trading-day rule."""

    match rule.reference_event:
        case ReferenceEvent.BUSINESS_DAY_OF_PERIOD:
            return get_nth_business_day_of_period(
                adjusted_period,
                rule.n_reference,
                trading_calendar,
            )

        case ReferenceEvent.CALENDAR_DAY_OF_PERIOD:
            return get_nth_calendar_day_of_period(
                adjusted_period,
                rule.n_reference,
            )

        case ReferenceEvent.WEEKDAY_OF_PERIOD:
            if rule.weekday is None:
                raise ValueError(
                    "Missing weekday in last-trading-day rule for "
                    f"product_id {product_id!r}"
                )

            return get_nth_weekday_of_period(
                adjusted_period,
                rule.weekday.as_int,
                rule.n_reference,
            )

        case _:
            raise ValueError(
                "Unsupported reference_event in last-trading-day rule "
                f"for product_id {product_id!r}: "
                f"{rule.reference_event!r}"
            )


def calculate_last_trading_day(
    *,
    product_id: str,
    period: Period,
    trading_calendar: TradingCalendar,
    rule: LastTradingRule,
) -> date:
    """Calculate the last trading day for a futures contract.

    The caller supplies the product-specific rule explicitly. This module
    performs no source-data loading and contains no product-rule registry.

    Args:
        product_id:
            Product identifier used for diagnostic error messages.
        period:
            Contract expiration or delivery period.
        trading_calendar:
            Trading calendar used for business-day calculations.
        rule:
            Structured product-specific last-trading-day rule.

    Returns:
        The calculated last trading day.
    """

    adjusted_period = PeriodFactory.shift_period_by_n(
        period,
        rule.period_offset,
    )

    reference_date = get_reference_date(
        product_id=product_id,
        adjusted_period=adjusted_period,
        rule=rule,
        trading_calendar=trading_calendar,
    )

    return trading_calendar.get_nth_business_day_relative_to_date(
        reference_date,
        rule.business_day_offset,
    )
