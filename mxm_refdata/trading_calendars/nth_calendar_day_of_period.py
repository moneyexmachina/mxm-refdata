import datetime

from mxm_refdata.models.periods import Period


def get_nth_calendar_day_of_period(period: Period, n: int) -> datetime.date:
    """
    Returns the N-th calendar day of the given period.

    Supports:
      - **Positive `n` values** (e.g., `n=1` → First day of the period).
      - **Negative `n` values** (e.g., `n=-1` → Last day of the period).

    Args:
        period (Period): The period (e.g., contract month, quarter).
        n (int): The N-th calendar day (1-based index for forward search, -1-based for reverse search).

    Returns:
        datetime.date: The date of the N-th calendar day.

    Raises:
        ValueError: If the N-th calendar day does not exist in the period.

    Examples:
        - **Contract Month (June 2025)**:
            - `get_nth_calendar_day_of_period(Period(2025, 6), 1)` → June 1, 2025.
            - `get_nth_calendar_day_of_period(Period(2025, 6), -1)` → June 30, 2025.

        - **Quarter (Q3 2025)**:
            - `get_nth_calendar_day_of_period(Period(2025, 7, 9), 5)` → July 5, 2025.
            - `get_nth_calendar_day_of_period(Period(2025, 7, 9), -5)` → September 26, 2025.
    """
    all_days = period.to_daterange()

    # Ensure valid index and return the correct day
    try:
        return (
            all_days[n - 1].date() if n > 0 else all_days[n].date()
        )  # Adjust for 1-based indexing
    except IndexError:
        raise ValueError(
            f"The {n}-th calendar day does not exist in {period.period_id}."
        )
