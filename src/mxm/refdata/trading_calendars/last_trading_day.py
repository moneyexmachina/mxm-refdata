import datetime
import json
from importlib.resources import files
from typing import NotRequired, TypedDict, cast

from mxm.refdata.factories.period_factory import PeriodFactory
from mxm.refdata.models.periods import Period
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.weekdays import Weekday
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


class LastTradingRule(TypedDict):
    period_offset: int
    reference_event: str
    n_reference: int
    business_day_offset: int
    weekday: NotRequired[str]


type LastTradingRules = dict[str, LastTradingRule]

TRADING_RULES: LastTradingRules = cast(
    LastTradingRules,
    json.loads(
        files("mxm.refdata")
        .joinpath("data/last_trading_rule.json")
        .read_text(encoding="utf-8")
    ),
)


def get_reference_date(
    *,
    product_id: str,
    adjusted_period: Period,
    rule: LastTradingRule,
    trading_calendar: TradingCalendar,
) -> datetime.date:
    """Resolve the reference date specified by a product last-trading-day rule."""
    reference_event = ReferenceEvent(rule["reference_event"])
    n_reference = int(rule["n_reference"])

    match reference_event:
        case ReferenceEvent.BUSINESS_DAY_OF_PERIOD:
            return get_nth_business_day_of_period(
                adjusted_period,
                n_reference,
                trading_calendar,
            )

        case ReferenceEvent.CALENDAR_DAY_OF_PERIOD:
            return get_nth_calendar_day_of_period(
                adjusted_period,
                n_reference,
            )

        case ReferenceEvent.WEEKDAY_OF_PERIOD:
            weekday_raw = rule.get("weekday")
            if not isinstance(weekday_raw, str):
                raise ValueError(
                    f"Missing or invalid 'weekday' key in trading rule for {product_id}"
                )

            return get_nth_weekday_of_period(
                adjusted_period,
                Weekday.from_str(weekday_raw).as_int,
                n_reference,
            )

        case _:
            raise ValueError(f"Unsupported reference_event: {reference_event!r}")


def calculate_last_trading_day(
    product_id: str,
    period: Period,
    trading_calendar: TradingCalendar,
) -> datetime.date:
    """
    Calculate the last trading day for a futures contract.

    The calculation is based on the product-specific last-trading-day rule,
    the contract period, and the relevant trading calendar.
    """
    if product_id not in TRADING_RULES:
        raise KeyError(f"No trading rule found for product: {product_id}")

    rule = TRADING_RULES[product_id]

    adjusted_period = PeriodFactory.shift_period_by_n(
        period,
        int(rule["period_offset"]),
    )

    reference_date = get_reference_date(
        product_id=product_id,
        adjusted_period=adjusted_period,
        rule=rule,
        trading_calendar=trading_calendar,
    )

    business_day_offset = int(rule.get("business_day_offset", 0))

    return trading_calendar.get_nth_business_day_relative_to_date(
        reference_date,
        business_day_offset,
    )
