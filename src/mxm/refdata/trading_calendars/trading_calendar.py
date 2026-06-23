import datetime
from typing import cast

import exchange_calendars as xcals
import pandas as pd

DEFAULT_XCALS_START_DATE = datetime.date(1980, 1, 2)
DEFAULT_XCALS_END_DATE = datetime.date(2050, 12, 31)


class TradingCalendarCoverageError(ValueError):
    """Raised when a date falls outside the available trading-calendar coverage."""


class TradingCalendar:
    """
    TradingCalendar manages exchange trading sessions and provides session-based utilities.
    Sessions are represented by UTC Timestamps, following `exchange_calendars` conventions.
    """

    def __init__(
        self,
        calendar_name: str,
    ):
        """
        Initializes a TradingCalendar based on an exchange calendar.

        Args:
            calendar_name (str): The name of the exchange calendar (e.g., "CMES", "NYSE").
            extend_to (datetime.date, optional): Extend the calendar to this date if needed.

        Raises:
            ValueError: If the calendar name is not recognized by `exchange_calendars`.
        """
        self.calendar = xcals.get_calendar(
            calendar_name,
            start=DEFAULT_XCALS_START_DATE,
            end=DEFAULT_XCALS_END_DATE,
        )

        self.calendar_name = calendar_name
        self.first_session = self.calendar.first_session.date()
        self.last_session = self.calendar.last_session.date()

    def get_sessions_in_range(
        self, start: datetime.date, end: datetime.date
    ) -> pd.DatetimeIndex:
        """
        Returns trading sessions in a given range as a DatetimeIndex in UTC.

        Args:
            start (datetime.date): The start of the range.
            end (datetime.date): The end of the range.

        Returns:
            pd.DatetimeIndex: A list of session timestamps in UTC.
        """
        self._ensure_date_in_coverage(start)
        self._ensure_date_in_coverage(end)
        return self.calendar.sessions_in_range(start, end)

    def shift_sessions(self, session: pd.Timestamp, offset: int) -> pd.Timestamp:
        """
        Moves a given session forward or backward by a specified number of sessions.

        Args:
            session (pd.Timestamp): The session timestamp in UTC.
            offset (int): Number of sessions to shift (+ for forward, - for backward).

        Returns:
            pd.Timestamp: The shifted session timestamp in UTC.
        """
        return self.calendar.session_offset(session, offset)

    def get_session_dates_in_range(
        self, start: datetime.date, end: datetime.date
    ) -> list[datetime.date]:
        """
        Returns trading session dates in a given range.

        Args:
            start (datetime.date): The start date.
            end (datetime.date): The end date.

        Returns:
            List[datetime.date]: A list of session dates.
        """
        self._ensure_date_in_coverage(start)
        self._ensure_date_in_coverage(end)

        return [ts.date() for ts in self.get_sessions_in_range(start, end)]

    def shift_session_date(self, date: datetime.date, offset: int) -> datetime.date:
        """
        Moves a given date forward or backward by a specified number of trading sessions.

        Args:
            date (datetime.date): The reference date.
            offset (int): Number of sessions to shift (+ for forward, - for backward).

        Returns:
            datetime.date: The shifted session's date.
        """
        return self.shift_sessions(pd.Timestamp(date), offset).date()

    def get_session_open(self, session: pd.Timestamp) -> pd.Timestamp:
        """
        Returns the opening time of a given session.

        Args:
            session (pd.Timestamp): The session timestamp in UTC.

        Returns:
            pd.Timestamp: The market open time for the session (UTC).
        """
        return cast(pd.Timestamp, self.calendar.schedule.loc[session, "open"])

    def get_session_close(self, session: pd.Timestamp) -> pd.Timestamp:
        """
        Returns the closing time of a given session.

        Args:
            session (pd.Timestamp): The session timestamp in UTC.

        Returns:
            pd.Timestamp: The market close time for the session (UTC).
        """
        return cast(pd.Timestamp, self.calendar.schedule.loc[session, "close"])

    def is_trading_day(self, date: datetime.date) -> bool:
        """
        Checks if a given date is a valid trading day.

        Args:
            date (datetime.date): The date to check.

        Returns:
            bool: True if the date is a trading day, False otherwise.
        """
        self._ensure_date_in_coverage(date)

        return self.calendar.is_session(date)

    def get_last_prior_session_date(self, date: datetime.date) -> datetime.date:
        """
        Finds the last valid session date prior to or on the given date.

        Args:
            date (datetime.date): The date to check.

        Returns:
            datetime.date: The last valid trading session date.

        Raises:
            ValueError: If the date is before the first available session in the trading calendar.
        """
        # If it's already a trading day, return it as is
        if self.is_trading_day(date):
            return date

        # Start from the given date and move backward until we find a valid session
        while not self.is_trading_day(date):
            date -= datetime.timedelta(days=1)
            if date < self.calendar.first_session.date():
                raise ValueError(f"No prior session found for date {date}")

        return date

    def get_nth_business_day_relative_to_date(
        self, date: datetime.date, n: int
    ) -> datetime.date:
        """
        Finds the N-th business day relative to a given date, even if the date is not a business day.

        If the date is not a business day:
        - When `n < 0` (backward shift), we already moved back once, so shift by `n + 1`.
        - When `n > 0` (forward shift), shift by `n` as usual.

        Args:
            date (datetime.date): The starting date (can be a business or non-business day).
            n (int): The number of business days to move (+ for forward, - for backward).

        Returns:
            datetime.date: The computed business day.

        """
        # If the date is not a business day, find the last valid business day before it
        if not self.is_trading_day(date):
            date = self.get_last_prior_session_date(date)
            if n < 0:
                n += 1  # If moving backward, adjust by 1 because we already moved back

        # Now shift by `n` business days from a valid business day
        return self.shift_session_date(date, n)

    def _ensure_date_in_coverage(self, date: datetime.date) -> None:
        checked_date = _to_date(date)
        if checked_date < self.first_session:
            raise TradingCalendarCoverageError(
                f"Date {date} is before available coverage for calendar "
                f"{self.calendar_name!r}: first_session={self.first_session}."
            )

        if checked_date > self.last_session:
            raise TradingCalendarCoverageError(
                f"Date {date} is after available coverage for calendar "
                f"{self.calendar_name!r}: last_session={self.last_session}."
            )

    def ensure_range_in_coverage(
        self,
        start: datetime.date,
        end: datetime.date,
    ) -> None:
        self._ensure_date_in_coverage(start)
        self._ensure_date_in_coverage(end)


def _to_date(value: datetime.date | pd.Timestamp) -> datetime.date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    return value
