import datetime
import json
from importlib.resources import files

from mxm.refdata.models.periods import Period
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.services.period_factory import PeriodFactory
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

# Load trading rules from packaged JSON file
TRADING_RULES = json.loads(
    files("mxm_refdata")
    .joinpath("data/last_trading_rule.json")
    .read_text(encoding="utf-8")
)


def calculate_last_trading_day(
    product_id: str, period: Period, trading_calendar: TradingCalendar
) -> datetime.date:
    """
    Calculates the last trading day for a given futures contract based on the product's trading rule
    and the specified contract period.

    Args:
        product (str): The product identifier for the futures contract.
        period (Period): The contract period containing year and month information.
        trading_calendar (TradingCalendar): The trading calendar to determine business days.

    Returns:
        datetime.date: The computed last trading day for the contract.

    Raises:
        ValueError: If the trading rule for the product cannot be parsed.
        KeyError: If the product is not found in the last_trading_rule data.
    """
    # Retrieve the trading rule for the given product
    if product_id not in TRADING_RULES:
        raise KeyError(f"No trading rule found for product: {product_id}")

    rule = TRADING_RULES[product_id]

    # Step 1: Apply period_offset
    adjusted_period = PeriodFactory.shift_period_by_n(period, rule["period_offset"])

    # Step 2: Determine reference event

    reference_event = ReferenceEvent(rule["reference_event"])
    n_reference = rule["n_reference"]

    if reference_event == ReferenceEvent.BUSINESS_DAY_OF_PERIOD:
        reference_date = get_nth_business_day_of_period(
            adjusted_period, n_reference, trading_calendar
        )
    elif reference_event == ReferenceEvent.CALENDAR_DAY_OF_PERIOD:
        reference_date = get_nth_calendar_day_of_period(adjusted_period, n_reference)
    elif reference_event == ReferenceEvent.WEEKDAY_OF_PERIOD:
        weekday = rule.get("weekday")
        if not weekday:
            raise ValueError(f"Missing 'weekday' key in trading rule for {product_id}")
        reference_date = get_nth_weekday_of_period(
            adjusted_period, Weekday.from_str(weekday).as_int, n_reference
        )

    # Step 3: Apply business_day_offset
    business_day_offset = rule.get("business_day_offset", 0)
    last_trading_day = trading_calendar.get_nth_business_day_relative_to_date(
        reference_date, business_day_offset
    )

    return last_trading_day
