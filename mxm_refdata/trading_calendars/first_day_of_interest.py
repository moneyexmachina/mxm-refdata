"""Calculate the first day we are interested in a given FuturesContract."""

import json
from datetime import date
from importlib.resources import files

from mxm_refdata.models import Period, PeriodType
from mxm_refdata.services.period_factory import PeriodFactory
from mxm_refdata.trading_calendars.last_trading_day import calculate_last_trading_day
from mxm_refdata.trading_calendars.trading_calendar import TradingCalendar

# Load first_day_of_interest rules from JSON file
FIRST_DAY_OF_INTEREST_RULES = json.loads(
    files("mxm_refdata")
    .joinpath("data/first_day_of_interest_rule.json")
    .read_text(encoding="utf-8")
)


def calculate_first_day_of_interest(
    product_id: str, period: Period, trading_calendar: TradingCalendar
) -> date:
    """
    Calculate the first_day_of_interest for a given futures contract.

    Parameters:
    - product_id (str): The product identifier for the futures contract.
    - period (Period): The period representing the contract's expiration/delivery period.
    - trading_calendar (TradingCalendar): The trading calendar to use for business day calculations.

    Returns:
    - date: The first business day we are interested in a given FuturesContract.

    Raises:
    - ValueError: If the product_id is not found in the JSON rules.
    - ValueError: If period_type is not MONTH.
    """
    if product_id not in FIRST_DAY_OF_INTEREST_RULES:
        raise ValueError(
            f"No first_day_of_interest rule found for product_id: {product_id}"
        )

    if period.period_type != PeriodType.MONTH:
        raise ValueError(f"Unsupported period_type: {period.period_type}")

    product_rules = FIRST_DAY_OF_INTEREST_RULES[product_id]
    month_str = period.first_date.strftime("%b")
    try:
        shift_n = product_rules["shift_rule"]["n_shift"][month_str]
    except KeyError as e:
        raise KeyError(
            f"No shift value found for month '{month_str}' in product_id: {product_id}"
        ) from e

    shifted_period = PeriodFactory().shift_period_by_n(period, n=-shift_n)

    # Determine reference date based on reference rule
    reference_rule = product_rules["reference_rule"]

    if reference_rule == "next_b_day_after_last_trading_day_of_december":
        december_period = PeriodFactory.get_period(
            date_obj=date(shifted_period.last_date.year, 12, 1),
            period_type=PeriodType.MONTH,
        )

        reference_date = calculate_last_trading_day(
            product_id, december_period, trading_calendar
        )
    elif reference_rule == "next_b_day_after_period":
        reference_date = shifted_period.last_date
    else:
        raise ValueError(f"Unsupported reference_rule: {reference_rule}")

    return trading_calendar.get_nth_business_day_relative_to_date(reference_date, n=1)
