"""Unit tests for the Period dataclass."""

from datetime import date

import pytest
from pandas import DatetimeIndex

from mxm_refdata.models.periods import Period, PeriodType


def test_period_initialization():
    """Test initialization of a Period instance."""
    period = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    assert period.period_id == "2024-Q1"
    assert period.period_type == PeriodType.QUARTER
    assert period.first_date == date(2024, 1, 1)
    assert period.last_date == date(2024, 3, 31)


def test_to_daterange():
    """Test the to_daterange method."""
    period = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 3),
    )
    date_range = period.to_daterange()
    assert isinstance(date_range, DatetimeIndex)
    assert list(date_range) == list(
        DatetimeIndex(
            [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 3),
            ]
        )
    )


def test_immutability():
    """Test that a Period instance is immutable."""
    period = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    with pytest.raises(AttributeError, match="cannot assign to field"):
        period.first_date = date(2024, 2, 1)  # Attempt to modify a frozen field


def test_single_day_period():
    """Test behavior when the first_date and last_date are the same."""
    period = Period(
        period_id="2024-01-01",
        period_type=PeriodType.DAY,  # If a daily type exists, otherwise use a placeholder
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 1),
    )
    date_range = period.to_daterange()
    assert list(date_range) == list(DatetimeIndex([date(2024, 1, 1)]))


def test_invalid_date_order():
    """Test behavior when first_date is after last_date."""
    with pytest.raises(ValueError, match="first_date must not be after last_date"):
        Period(
            period_id="2024-Q1",
            period_type=PeriodType.QUARTER,
            first_date=date(2024, 4, 1),
            last_date=date(2024, 3, 31),
        )


def test_period_equality():
    """Test equality of two identical Period instances."""
    period1 = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    period2 = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    assert period1 == period2


def test_period_inequality():
    """Test inequality of two different Period instances."""
    period1 = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    period2 = Period(
        period_id="2024-Q2",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 4, 1),
        last_date=date(2024, 6, 30),
    )
    assert period1 != period2


def test_period_hashability():
    """Test that Period objects are hashable."""
    period1 = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    period2 = Period(
        period_id="2024-Q2",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 4, 1),
        last_date=date(2024, 6, 30),
    )
    period_dict = {period1: "First Quarter", period2: "Second Quarter"}
    assert period_dict[period1] == "First Quarter"
    assert period_dict[period2] == "Second Quarter"


def test_period_str_representation():
    """Test the string representation of a Period instance."""
    period = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    assert str(period) == "QUARTER Period: 2024-Q1 (2024-01-01 to 2024-03-31)"


def test_period_repr_representation():
    """Test the repr representation of a Period instance."""
    period = Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    assert repr(period) == (
        "Period(period_id='2024-Q1', period_type=PeriodType.QUARTER, "
        "first_date=2024-01-01, last_date=2024-03-31)"
    )


def test_period_sorting():
    """Test that periods are sorted correctly by type and start date."""

    periods = [
        Period("2023-Q1", PeriodType.QUARTER, date(2023, 1, 1), date(2023, 3, 31)),
        Period("2023-02", PeriodType.MONTH, date(2023, 2, 1), date(2023, 2, 28)),
        Period("2023-01", PeriodType.MONTH, date(2023, 1, 1), date(2023, 1, 31)),
        Period("2023", PeriodType.YEAR, date(2023, 1, 1), date(2023, 12, 31)),
        Period("2023-W05", PeriodType.WEEK, date(2023, 1, 30), date(2023, 2, 5)),
        Period("2023-W04", PeriodType.WEEK, date(2023, 1, 23), date(2023, 1, 29)),
    ]

    sorted_periods = sorted(periods)

    expected_order = [
        "2023",  # Year first
        "2023-Q1",  # Quarter next
        "2023-01",  # January month
        "2023-02",  # February month
        "2023-W04",  # Week 4
        "2023-W05",  # Week 5
    ]

    assert [p.period_id for p in sorted_periods] == expected_order, "Sorting failed!"
