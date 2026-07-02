import datetime

import pytest

from mxm.refdata.factories import PeriodFactory
from mxm.refdata.trading_calendars.nth_calendar_day_of_period import (
    get_nth_calendar_day_of_period,
)


@pytest.mark.parametrize(
    "period_id, n, expected",
    [
        # ---- Test cases for contract months (June 2025) ----
        ("Jun-2025", 1, datetime.date(2025, 6, 1)),  # First day of June 2025
        ("Jun-2025", 15, datetime.date(2025, 6, 15)),  # 15th day of June
        ("Jun-2025", -1, datetime.date(2025, 6, 30)),  # Last day of June 2025
        ("Jun-2025", -5, datetime.date(2025, 6, 26)),  # Fifth-last day of June 2025
        # ---- Test cases for quarter periods (Q3 2025) ----
        ("2025-Q3", 1, datetime.date(2025, 7, 1)),  # First day of Q3 2025
        ("2025-Q3", 10, datetime.date(2025, 7, 10)),  # 10th day of Q3
        ("2025-Q3", -1, datetime.date(2025, 9, 30)),  # Last day of Q3 2025
        ("2025-Q3", -10, datetime.date(2025, 9, 21)),  # 10th-last day of Q3
    ],
)
def test_get_nth_calendar_day_of_period(
    period_id: str, n: int, expected: datetime.date
):
    """Test retrieving the N-th calendar day of a period."""
    period = PeriodFactory.get_period(period_id=period_id)
    assert get_nth_calendar_day_of_period(period, n) == expected


def test_invalid_n():
    """Test that out-of-range N values raise a ValueError."""
    period = PeriodFactory.get_period(period_id="Jun-2025")
    with pytest.raises(ValueError):
        get_nth_calendar_day_of_period(period, 40)  # More than 30 days in June
    with pytest.raises(ValueError):
        get_nth_calendar_day_of_period(
            period, -40
        )  # More negative indexing than possible
