"""Utility functions for working with calendars."""

import datetime

import pandas as pd

from mxm.refdata.models.periods import Period
from mxm.refdata.models.weekdays import Weekday


def get_nth_weekday_of_period(
    period: Period, weekday: int | str, n: int
) -> datetime.date:
    """
    Returns the N-th occurrence of a given weekday in the specified period.

    Supports:
      - `weekday` as an **integer** (0=Monday, 6=Sunday).
      - `weekday` as a **full name** ("Tuesday", "Friday").
      - `weekday` as an **abbreviation** ("Tue", "Fri").

    Args:
        period (Period): The period (e.g., contract month, quarter).
        weekday (int | str): The weekday (0=Monday, 6=Sunday or "Tuesday", "Tue", etc.).
        n (int): The N-th occurrence (1-based index for forward search, -1-based for reverse search).

    Returns:
        datetime.date: The date of the N-th occurrence of the given weekday.

    Raises:
        ValueError: If the N-th occurrence does not exist in the period.
    """
    # Convert weekday string to integer if needed
    if isinstance(weekday, str):
        weekday = Weekday.from_str(weekday).as_int
    period_range = period.to_daterange()
    # Get all dates in the period and filter for matching weekdays
    dates: list[pd.Timestamp] = [
        date for date in period_range if date.weekday() == weekday
    ]

    # Handle both forward (n > 0) and reverse (n < 0) indexing
    try:
        return (
            dates[n - 1].date() if n > 0 else dates[n].date()
        )  # Python negative index works naturally
    except IndexError as err:
        raise ValueError(
            f"The {n}-th occurrence of weekday {weekday} does not exist in {period.period_id}."
        ) from err
