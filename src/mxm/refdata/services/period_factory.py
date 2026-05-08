"""Module to manage the creation of Period objects with flyweight pattern."""

import threading
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from enum import Enum
from types import MappingProxyType
from typing import ClassVar

from mxm.refdata.models.months import Month
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.utils.regex_patterns import PERIOD_TYPE_PARSING_MAP


class HandleCurrentPeriod(Enum):
    """Options for handling the current period when generating a list of periods."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


class HandlePartialEndPeriod(Enum):
    """Options for handling a partial end period when generating a list of periods."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


class PeriodFactory:
    """Factory class to manage the creation of Period objects with flyweight pattern."""

    _instance = None  # Singleton instance
    _period_cache: ClassVar[dict] = {}  # Dictionary to store unique Period objects
    _lock = threading.Lock()  # Lock for thread safety

    date_to_period_id_map: Mapping[PeriodType, Callable[[date], str]] = (
        MappingProxyType(
            {
                PeriodType.YEAR: lambda d: f"{d.year}",
                PeriodType.MONTH: lambda d: d.strftime("%b-%Y"),
                PeriodType.QUARTER: lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}",
                PeriodType.WEEK: lambda d: f"{d.year}-W{d.isocalendar()[1]}",
            },
        )
    )

    def __new__(cls) -> "PeriodFactory":
        """Ensures that only one instance of PeriodFactory is created (thread-safe singleton)."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_period(
        cls,
        period_id: str | None = None,
        date_obj: date | None = None,
        period_type: PeriodType | None = None,
    ) -> Period:
        """Get a Period object either by period_id or by date and period_type."""
        if period_id:
            if period_id not in cls._period_cache:
                period_type = cls._period_type_from_period_id(period_id)
                first_day, last_day = cls.calculate_period_dates(period_id, period_type)
                period = Period(
                    period_id=period_id,
                    period_type=period_type,
                    first_date=first_day,
                    last_date=last_day,
                )
                cls._period_cache[period_id] = period

        elif date_obj and period_type:
            if not isinstance(date_obj, date):
                message = "date_obj must be a date object (not a datetime object)"
                raise ValueError(message)

            period = cls._create_from_date(date_obj, period_type)
            period_id = period.period_id
            if period_id not in cls._period_cache:
                cls._period_cache[period_id] = period

        else:
            message = "Must provide either period_id or date_obj with period_type"
            raise ValueError(message)

        return cls._period_cache[period_id]

    @classmethod
    def _period_type_from_period_id(cls, period_id: str) -> PeriodType:
        """Parse a period_id string and return the corresponding PeriodType."""
        for period_type, pattern in PERIOD_TYPE_PARSING_MAP.items():
            if pattern.match(period_id):
                return period_type
        raise ValueError(f"Unrecognized period_id format: {period_id}")

    @classmethod
    def _create_from_date(cls, date_obj: date, period_type: PeriodType) -> Period:
        """Create a Period from a specific date and period type."""
        if period_type not in cls.date_to_period_id_map:
            message = f"Unsupported period_type: {period_type}"
            raise ValueError(message)

        period_id = cls.date_to_period_id_map[period_type](date_obj)
        first_day, last_day = cls.calculate_period_dates(period_id, period_type)
        return Period(
            period_id=period_id,
            period_type=period_type,
            first_date=first_day,
            last_date=last_day,
        )

    @classmethod
    def calculate_period_dates(
        cls, period_id: str, period_type: PeriodType
    ) -> tuple[date, date]:
        """Calculate the first and last date for the given period based on its type."""
        if period_type == PeriodType.YEAR:
            return cls._calculate_year_dates(period_id)
        elif period_type == PeriodType.MONTH:
            return cls._calculate_month_dates(period_id)
        elif period_type == PeriodType.QUARTER:
            return cls._calculate_quarter_dates(period_id)
        elif period_type == PeriodType.WEEK:
            return cls._calculate_week_dates(period_id)
        else:
            raise ValueError(f"Unsupported period type: {period_type}")

    @staticmethod
    def _calculate_year_dates(period_id: str) -> tuple[date, date]:
        """Calculate the first and last date for a year."""
        year = int(period_id)
        return date(year, 1, 1), date(year, 12, 31)

    @staticmethod
    def _calculate_month_dates(period_id: str) -> tuple[date, date]:
        """Calculate the first and last date for a month."""
        month_str, year = period_id.split("-")
        month = Month.from_str(month_str)
        first_date = date(int(year), month.as_int, 1)
        last_date = PeriodFactory._last_day_of_month(first_date)
        return first_date, last_date

    @staticmethod
    def _calculate_quarter_dates(period_id: str) -> tuple[date, date]:
        """Calculate the first and last date for a quarter."""
        year, quarter = period_id.split("-Q")
        start_month = (int(quarter) - 1) * 3 + 1
        first_date = date(int(year), start_month, 1)
        last_date = PeriodFactory._last_day_of_month(
            date(int(year), start_month + 2, 1)  # Third month of the quarter
        )
        return first_date, last_date

    @staticmethod
    def _calculate_week_dates(period_id: str) -> tuple[date, date]:
        """Calculate the first and last date for a week."""
        year, week = period_id.split("-W")
        first_date = date.fromisocalendar(int(year), int(week), 1)
        last_date = first_date + timedelta(days=6)
        return first_date, last_date

    @staticmethod
    def _last_day_of_month(first_date: date) -> date:
        """Calculate the last day of the month."""
        next_month = first_date.replace(day=28) + timedelta(
            days=4
        )  # Move to next month
        return next_month - timedelta(days=next_month.day)

    @classmethod
    def get_next_n_periods(
        cls,
        start_date: date,
        period_type: PeriodType,
        n: int,
        handle_current_period: HandleCurrentPeriod = HandleCurrentPeriod.INCLUDE,
    ) -> list[Period]:
        """Generate the next n Period objects from a given start_date.

        Args:
            start_date (date): The date to start from.
            period_type (PeriodType): The type of period (e.g., month, quarter).
            n (int): Number of periods to generate.
            handle_current_period (HandleCurrentPeriod): Whether to include the period containing start_date.

        Returns:
            list[Period]: A list of Period objects representing the next n periods.
        """
        periods = []

        # Handle the current period
        if handle_current_period == HandleCurrentPeriod.INCLUDE:
            period = cls.get_period(date_obj=start_date, period_type=period_type)
            periods.append(period)

        current_date = cls.shift_date_by_n_periods(start_date, period_type, 1)

        # Generate the remaining n - 1 periods
        while len(periods) < n:
            period = cls.get_period(date_obj=current_date, period_type=period_type)
            periods.append(period)
            current_date = cls.shift_date_by_n_periods(current_date, period_type, 1)

        return periods

    @classmethod
    def shift_date_by_n_periods(
        cls, start_date: date, period_type: "PeriodType", steps: int
    ) -> date:
        """Shift a date by a given number of periods in the specified PeriodType."""
        if period_type == PeriodType.YEAR:
            return cls._shift_years(start_date, steps)
        elif period_type == PeriodType.MONTH:
            return cls._shift_months(start_date, steps)
        elif period_type == PeriodType.QUARTER:
            return cls._shift_quarters(start_date, steps)
        elif period_type == PeriodType.WEEK:
            return cls._shift_weeks(start_date, steps)
        else:
            raise ValueError(f"Unsupported period type: {period_type}")

    @staticmethod
    def _shift_years(start_date: date, steps: int) -> date:
        """Shift a date by a given number of years."""
        return date(start_date.year + steps, start_date.month, start_date.day)

    @staticmethod
    def _shift_months(start_date: date, steps: int) -> date:
        """Shift a date by a given number of months, preserving the day when possible."""
        new_month = (start_date.month - 1 + steps) % 12 + 1
        new_year = start_date.year + ((start_date.month - 1 + steps) // 12)
        return date(new_year, new_month, 1)

    @staticmethod
    def _shift_quarters(start_date: date, steps: int) -> date:
        """Shift a date by a given number of quarters."""
        start_month = (start_date.month - 1) // 3 * 3 + 1
        new_quarter_start_month = (start_month - 1 + steps * 3) % 12 + 1
        new_year = start_date.year + ((start_month - 1 + steps * 3) // 12)
        return date(new_year, new_quarter_start_month, 1)

    @staticmethod
    def _shift_weeks(start_date: date, steps: int) -> date:
        """Shift a date by a given number of weeks."""
        return start_date + timedelta(weeks=steps)

    @classmethod
    def shift_period_by_n(cls, period: Period, n: int) -> Period:
        """
        Shifts a given period by `n` instances of its period type.

        Supports:
          - **Months** (e.g., "Jun-2025" → "Jul-2025" for `n=1`).
          - **Quarters** (e.g., "2025-Q2" → "2025-Q3" for `n=1`).
          - **Years** (e.g., "2025" → "2026" for `n=1`).
          - **Weeks** (e.g., "2025-W10" → "2025-W11" for `n=1`).

        Args:
            period (Period): The period instance to shift.
            n (int): The number of periods to shift (can be negative for backward shifts).

        Returns:
            Period: The new shifted period instance.
        """
        # Shift the first date by `n` periods using the existing method
        new_start_date = cls.shift_date_by_n_periods(
            period.first_date, period.period_type, n
        )

        # Retrieve the new period instance based on the shifted date
        return cls.get_period(date_obj=new_start_date, period_type=period.period_type)

    @classmethod
    def get_periods_in_range(
        cls,
        start_date: date,
        end_date: date,
        period_type: PeriodType,
        handle_partial_end_period: HandlePartialEndPeriod = HandlePartialEndPeriod.EXCLUDE,
    ) -> list[Period]:
        """Generate a list of Period objects within a specified date range."""
        if start_date > end_date:
            message = "start_date must be earlier than end_date"
            raise ValueError(message)

        periods = []
        current_date = start_date

        while current_date <= end_date:
            period = cls.get_period(date_obj=current_date, period_type=period_type)
            if (
                period.last_date > end_date
                and handle_partial_end_period == HandlePartialEndPeriod.EXCLUDE
            ):
                break
            periods.append(period)
            current_date = cls.shift_date_by_n_periods(
                period.first_date, period_type, 1
            )

        return periods
