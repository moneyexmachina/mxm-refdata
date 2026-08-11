"""Calculate the first day of interest for a futures contract."""

from __future__ import annotations

from datetime import date

from mxm.refdata.generation.periods import period_containing, shift_period_by_n
from mxm.refdata.models import Period, PeriodType
from mxm.refdata.models.products.futures_product import (
    FirstDayOfInterestRule,
    LastTradingRule,
)
from mxm.refdata.trading_calendars.last_trading_day import (
    calculate_last_trading_day,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


def calculate_first_day_of_interest(
    *,
    product_id: str,
    period: Period,
    trading_calendar: TradingCalendar,
    rule: FirstDayOfInterestRule,
    last_trading_rule: LastTradingRule,
) -> date:
    """Calculate the first day of interest for a futures contract.

    The caller supplies the product-specific rules explicitly. This module
    performs no source-data loading and contains no product-rule registry.

    Args:
        product_id:
            Product identifier used for diagnostic error messages.
        period:
            Contract expiration or delivery period.
        trading_calendar:
            Trading calendar used for business-day calculations.
        rule:
            Structured first-day-of-interest rule.
        last_trading_rule:
            Structured last-trading-day rule. This is required when the
            first-day-of-interest reference is based on the last trading day
            of December.

    Returns:
        The first business day on which the contract is of interest.

    Raises:
        ValueError:
            If the period type or reference rule is unsupported.
        KeyError:
            If no shift is defined for the contract month.
    """

    if period.period_type is not PeriodType.MONTH:
        raise ValueError(
            f"Unsupported period_type for product_id {product_id!r}: "
            f"{period.period_type!r}"
        )

    month = period.first_date.strftime("%b")

    try:
        shift_n = rule.shift_rule.n_shift[month]
    except KeyError as exc:
        raise KeyError(
            "No first-day-of-interest shift found for "
            f"month {month!r} and product_id {product_id!r}"
        ) from exc

    shifted_period = shift_period_by_n(period, n=-shift_n)

    match rule.reference_rule:
        case "next_b_day_after_last_trading_day_of_december":
            december_period = period_containing(
                value=date(shifted_period.last_date.year, 12, 1),
                period_type=rule.shift_rule.shift_period_type,
            )

            reference_date = calculate_last_trading_day(
                product_id=product_id,
                period=december_period,
                trading_calendar=trading_calendar,
                rule=last_trading_rule,
            )
        case "next_b_day_after_last_trading_day_of_november":
            november_period = period_containing(
                value=date(shifted_period.last_date.year, 11, 1),
                period_type=rule.shift_rule.shift_period_type,
            )

            reference_date = calculate_last_trading_day(
                product_id=product_id,
                period=november_period,
                trading_calendar=trading_calendar,
                rule=last_trading_rule,
            )

        case "next_b_day_after_period":
            reference_date = shifted_period.last_date

        case _:
            raise ValueError(
                "Unsupported first-day-of-interest reference_rule "
                f"for product_id {product_id!r}: "
                f"{rule.reference_rule!r}"
            )

    return trading_calendar.get_nth_business_day_relative_to_date(
        reference_date,
        n=1,
    )
