import datetime

import pandas as pd
import pytest
from exchange_calendars.errors import DateOutOfBounds

from mxm_refdata.trading_calendars.trading_calendar import TradingCalendar


@pytest.fixture
def cme_calendar():
    """Fixture for initializing the CME trading calendar."""
    return TradingCalendar("CME")


def test_get_sessions_in_range(cme_calendar):
    """Test retrieving trading sessions in a given range."""
    start = datetime.date(2025, 6, 16)
    end = datetime.date(2025, 6, 20)
    sessions = cme_calendar.get_sessions_in_range(start, end)
    assert isinstance(sessions, pd.DatetimeIndex)
    assert len(sessions) > 0


def test_shift_sessions_forward(cme_calendar):
    """Test shifting a session forward by a given number of sessions."""
    session = pd.Timestamp("2025-06-18")  # No timezone
    new_session = cme_calendar.shift_sessions(session, 2)
    assert new_session > session
    assert new_session.tz is None  # Ensuring it's still naive


def test_shift_sessions_backward(cme_calendar):
    """Test shifting a session backward by a given number of sessions."""
    session = pd.Timestamp("2025-06-18")  # No timezone
    new_session = cme_calendar.shift_sessions(session, -2)
    assert new_session < session
    assert new_session.tz is None  # Ensuring it's still naive


def test_get_session_dates_in_range(cme_calendar):
    """Test retrieving session dates within a given range."""
    start = datetime.date(2025, 6, 16)
    end = datetime.date(2025, 6, 20)
    session_dates = cme_calendar.get_session_dates_in_range(start, end)
    assert isinstance(session_dates, list)
    assert all(isinstance(date, datetime.date) for date in session_dates)


def test_shift_session_date_forward(cme_calendar):
    """Test shifting a session date forward."""
    date = datetime.date(2025, 6, 18)
    new_date = cme_calendar.shift_session_date(date, 2)
    assert new_date > date


def test_shift_session_date_backward(cme_calendar):
    """Test shifting a session date backward."""
    date = datetime.date(2025, 6, 18)
    new_date = cme_calendar.shift_session_date(date, -2)
    assert new_date < date


def test_get_session_open(cme_calendar):
    """Test retrieving the session open time."""
    session = pd.Timestamp("2025-06-18")  # No timezone
    open_time = cme_calendar.get_session_open(session)
    assert isinstance(open_time, pd.Timestamp)


def test_get_session_close(cme_calendar):
    """Test retrieving the session close time."""
    session = pd.Timestamp("2025-06-18")  # No timezone
    close_time = cme_calendar.get_session_close(session)
    assert isinstance(close_time, pd.Timestamp)


def test_is_trading_day(cme_calendar):
    """Test checking whether a date is a trading day."""
    assert cme_calendar.is_trading_day(
        datetime.date(2025, 6, 16)
    )  # Example weekday (should be True)
    assert not cme_calendar.is_trading_day(
        datetime.date(2025, 6, 21)
    )  # Saturday (should be False)


def test_get_last_prior_session_date(cme_calendar):
    """Test finding the last valid trading session before or on a given date."""

    # ---- Test cases for valid trading days (should return same date) ----
    assert cme_calendar.get_last_prior_session_date(
        datetime.date(2025, 6, 18)
    ) == datetime.date(2025, 6, 18)  # Wednesday
    assert cme_calendar.get_last_prior_session_date(
        datetime.date(2025, 6, 20)
    ) == datetime.date(2025, 6, 20)  # Friday

    # ---- Test cases for weekends (should return last Friday) ----
    assert cme_calendar.get_last_prior_session_date(
        datetime.date(2025, 6, 21)
    ) == datetime.date(2025, 6, 20)  # Saturday → Previous Friday
    assert cme_calendar.get_last_prior_session_date(
        datetime.date(2025, 6, 22)
    ) == datetime.date(2025, 6, 20)  # Sunday → Previous Friday

    # ---- Test cases for holidays (should return last trading day before holiday) ----
    # Good Friday (April 18, 2025) → Previous session should be April 17
    assert cme_calendar.get_last_prior_session_date(
        datetime.date(2025, 4, 18)
    ) == datetime.date(2025, 4, 17)

    # ---- Edge case: Date before first available session (should raise DateOutOfBounds) ----
    first_session_date = cme_calendar.calendar.first_session
    with pytest.raises(DateOutOfBounds):
        cme_calendar.get_last_prior_session_date(
            first_session_date - datetime.timedelta(days=1)
        )


def test_get_nth_business_day_relative_to_date(cme_calendar):
    """Test shifting business days relative to any given date."""

    # ---- Case 1: Business day input (should shift normally) ----
    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 6, 18), -3
    ) == datetime.date(2025, 6, 13)  # Shift back 3 business days

    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 6, 18), 2
    ) == datetime.date(2025, 6, 20)  # Shift forward 2 business days

    # ---- Case 2: Weekend input (should move to last business day before shifting) ----
    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 6, 22), -3
    ) == datetime.date(2025, 6, 18)  # Sunday → Back to Friday → Then -2

    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 6, 22), 2
    ) == datetime.date(2025, 6, 24)  # Sunday → Back to Friday → Then +2

    # ---- Case 3: Holiday input (e.g., Good Friday, April 18, 2025) ----
    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 4, 18), -3
    ) == datetime.date(2025, 4, 15)  # Good Friday → Back to Thursday → Then -2

    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 4, 18), 2
    ) == datetime.date(2025, 4, 22)  # Good Friday → Back to Thursday → Then +2

    # ---- Case 4: `n=0` tests ----
    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 6, 18), 0
    ) == datetime.date(2025, 6, 18)  # Business day → Should return same day

    assert cme_calendar.get_nth_business_day_relative_to_date(
        datetime.date(2025, 6, 22), 0
    ) == datetime.date(2025, 6, 20)  # Sunday → Should return last business day (Friday)
