"""Reference periods for futures contracts."""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from functools import total_ordering

import pandas as pd


class PeriodType(Enum):
    """Period types for futures contracts."""

    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"


PERIOD_PRIORITY = {
    PeriodType.YEAR: 1,
    PeriodType.QUARTER: 2,
    PeriodType.MONTH: 3,
    PeriodType.WEEK: 4,
    PeriodType.DAY: 5,
}


@total_ordering
@dataclass(frozen=True)
class Period:
    """Represents a specific calendar period."""

    period_id: (
        str  # A unique identifier, like "2024", "Jan-2024", "2024-Q1", or "2024-W24"
    )
    period_type: PeriodType  # The type of the period (year, month, quarter, week)
    first_date: date  # The first day of the period
    last_date: date  # The last day of the period

    def __post_init__(self):
        if self.first_date > self.last_date:
            raise ValueError("first_date must not be after last_date")

    def __str__(self):
        return f"{self.period_type.name} Period: {self.period_id} ({self.first_date} to {self.last_date})"

    def __repr__(self):
        return f"Period(period_id='{self.period_id}', period_type={self.period_type}, first_date={self.first_date}, last_date={self.last_date})"

    def __lt__(self, other: "Period") -> bool:
        """Define sorting: higher-level periods (Year > Month) first, then by start date."""

        if PERIOD_PRIORITY[self.period_type] != PERIOD_PRIORITY[other.period_type]:
            return (
                PERIOD_PRIORITY[self.period_type] < PERIOD_PRIORITY[other.period_type]
            )

        return self.first_date < other.first_date

    def to_daterange(self) -> pd.DatetimeIndex:
        """Return a pandas date_range from first_date to last_date, with daily frequency."""
        return pd.date_range(self.first_date, self.last_date, freq="D")
