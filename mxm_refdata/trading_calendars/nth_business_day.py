"""Calculate n-th business day of a period."""

import datetime

from mxm_refdata.models.periods import Period
from mxm_refdata.trading_calendars.trading_calendar import TradingCalendar


def get_nth_business_day_of_period(
    period: Period, n: int, trading_calendar: TradingCalendar
) -> datetime.date:
    """
    Returns the N-th business day of the given period.

    Supports:
      - **Positive `n` values** (e.g., `n=1` → First business day).
      - **Negative `n` values** (e.g., `n=-1` → Last business day).

    Args:
        period (Period): The period (e.g., contract month, quarter).
        n (int): The N-th business day (1-based index for forward search, -1-based for reverse search).
        trading_calendar (TradingCalendar): The trading calendar to determine business days.

    Returns:
        datetime.date: The date of the N-th business day.

    Raises:
        ValueError: If the N-th business day does not exist in the period.

    Examples:
        - **Contract Month (June 2025)**:
            - `get_nth_business_day_of_period(Period(2025, 6), 1, trading_calendar)` → First business day of June 2025.
            - `get_nth_business_day_of_period(Period(2025, 6), -1, trading_calendar)` → Last business day of June 2025.

        - **Quarter (Q3 2025)**:
            - `get_nth_business_day_of_period(Period(2025, 7, 9), 5, trading_calendar)` → Fifth business day of Q3 2025.
    """
    all_dates = period.to_daterange()

    # Get valid business days within the period
    business_days = [
        date
        for date in trading_calendar.get_sessions_in_range(all_dates[0], all_dates[-1])
    ]

    # Ensure we return a date object, not a timestamp
    try:
        return business_days[n - 1].date() if n > 0 else business_days[n].date()
    except IndexError:
        raise ValueError(
            f"The {n}-th business day does not exist in {period.period_id}."
        )
