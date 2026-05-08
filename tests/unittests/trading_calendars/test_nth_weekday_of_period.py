import datetime

import pytest

from mxm.refdata.services.period_factory import PeriodFactory
from mxm.refdata.trading_calendars.nth_weekday_of_period import (
    get_nth_weekday_of_period,
)


@pytest.mark.parametrize(
    "period_id, weekday, n, expected",
    [
        # ---- Test cases for contract months (June 2025) ----
        ("Jun-2025", 1, 1, datetime.date(2025, 6, 3)),  # First Tuesday: June 3
        (
            "Jun-2025",
            "Wednesday",
            2,
            datetime.date(2025, 6, 11),
        ),  # Second Wednesday: June 11
        ("Jun-2025", "Thu", 3, datetime.date(2025, 6, 19)),  # Third Thursday: June 19
        ("Jun-2025", "Monday", 4, datetime.date(2025, 6, 23)),  # Fourth Monday: June 23
        ("Feb-2025", "Friday", 4, datetime.date(2025, 2, 28)),  # Fourth Friday: Feb 28
        # ---- Test cases for reverse N (counting backwards) ----
        (
            "Jun-2025",
            "Tuesday",
            -1,
            datetime.date(2025, 6, 24),
        ),  # Last Tuesday: June 24
        (
            "Jun-2025",
            "Wed",
            -2,
            datetime.date(2025, 6, 18),
        ),  # Second-last Wednesday: June 18
        (
            "Jun-2025",
            "Thursday",
            -3,
            datetime.date(2025, 6, 12),
        ),  # Third-last Thursday: June 12
        (
            "Jun-2025",
            "Monday",
            -4,
            datetime.date(2025, 6, 9),
        ),  # Fourth-last Monday: June 9
        # ---- Test cases for quarter periods (Q3 2025) ----
        (
            "2025-Q3",
            "Tuesday",
            1,
            datetime.date(2025, 7, 1),
        ),  # First Tuesday of Q3: July 1
        ("2025-Q3", "Wed", 2, datetime.date(2025, 7, 9)),  # Second Wednesday: July 9th
        (
            "2025-Q3",
            "Friday",
            -1,
            datetime.date(2025, 9, 26),
        ),  # Last Friday of Q3: Sep 26
    ],
)
def test_get_nth_weekday_of_period(period_id, weekday, n, expected):
    """Test retrieving the N-th occurrence of a given weekday in a period."""
    period = PeriodFactory.get_period(period_id=period_id)
    assert get_nth_weekday_of_period(period, weekday, n) == expected


def test_invalid_n():
    """Test case where N-th weekday does not exist (e.g., 6th Friday in a month)."""
    period = PeriodFactory.get_period(period_id="Jun-2025")
    with pytest.raises(ValueError):
        get_nth_weekday_of_period(period, weekday="Thursday", n=6)  # No 6th Thursday
    with pytest.raises(ValueError):
        get_nth_weekday_of_period(
            period, weekday="Wednesday", n=-6
        )  # No 6th last Wednesday
