"""Unit tests for the PeriodFactory class."""

from datetime import date

import pytest

from mxm.refdata.models.periods import PeriodType
from mxm.refdata.services.period_factory import PeriodFactory


@pytest.fixture
def factory() -> PeriodFactory:
    """Fixture to create a PeriodFactory instance."""
    return PeriodFactory()


def test_get_period_by_id(factory: PeriodFactory) -> None:
    """Test getting a Period object by period_id."""
    period = factory.get_period_by_id("2024-Q1")

    assert period.period_id == "2024-Q1"
    assert period.period_type == PeriodType.QUARTER
    assert period.first_date == date(2024, 1, 1)
    assert period.last_date == date(2024, 3, 31)


def test_get_period_by_date(factory: PeriodFactory) -> None:
    """Test getting a Period object by date and type."""
    period = factory.get_period_by_date(
        date_obj=date(2024, 2, 15),
        period_type=PeriodType.MONTH,
    )

    assert period.period_id == "Feb-2024"
    assert period.period_type == PeriodType.MONTH
    assert period.first_date == date(2024, 2, 1)
    assert period.last_date == date(2024, 2, 29)


def test_get_period_dispatches_by_period_id(factory: PeriodFactory) -> None:
    period = factory.get_period(period_id="2024-Q1")

    assert period == factory.get_period_by_id("2024-Q1")


def test_cache_behavior(factory: PeriodFactory):
    """Test that the factory reuses cached Period objects."""
    period1 = factory.get_period(period_id="2024-Q1")
    period2 = factory.get_period(period_id="2024-Q1")
    assert period1 is period2  # Both references should point to the same object


def test_invalid_period_id(factory: PeriodFactory):
    """Test handling of invalid period_id."""
    with pytest.raises(ValueError, match="Unrecognized period_id format"):
        factory.get_period(period_id="Invalid-Format")


def test_generate_next_n_periods(factory: PeriodFactory):
    """Test generating the next n Period objects."""
    start_date = date(2024, 2, 15)
    periods = factory.get_next_n_periods(
        start_date=start_date, period_type=PeriodType.MONTH, n=3
    )
    assert len(periods) == 3
    assert periods[0].period_id == "Feb-2024"
    assert periods[1].period_id == "Mar-2024"
    assert periods[2].period_id == "Apr-2024"


def test_get_periods_in_range(factory: PeriodFactory):
    """Test generating periods within a date range."""
    start_date = date(2024, 1, 1)
    end_date = date(2024, 6, 30)
    periods = factory.get_periods_in_range(
        start_date=start_date, end_date=end_date, period_type=PeriodType.QUARTER
    )
    assert len(periods) == 2
    assert periods[0].period_id == "2024-Q1"
    assert periods[1].period_id == "2024-Q2"


def test_calculate_year_dates():
    """Test calculate_period_dates for a year."""
    first_date, last_date = PeriodFactory.calculate_period_dates(
        "2024", PeriodType.YEAR
    )
    assert first_date == date(2024, 1, 1)
    assert last_date == date(2024, 12, 31)


def test_calculate_month_dates():
    """Test calculate_period_dates for a month."""
    first_date, last_date = PeriodFactory.calculate_period_dates(
        "Feb-2024", PeriodType.MONTH
    )
    assert first_date == date(2024, 2, 1)
    assert last_date == date(2024, 2, 29)  # Leap year

    first_date, last_date = PeriodFactory.calculate_period_dates(
        "Nov-2023", PeriodType.MONTH
    )
    assert first_date == date(2023, 11, 1)
    assert last_date == date(2023, 11, 30)


def test_calculate_quarter_dates():
    """Test calculate_period_dates for a quarter."""
    first_date, last_date = PeriodFactory.calculate_period_dates(
        "2024-Q1", PeriodType.QUARTER
    )
    assert first_date == date(2024, 1, 1)
    assert last_date == date(2024, 3, 31)

    first_date, last_date = PeriodFactory.calculate_period_dates(
        "2024-Q3", PeriodType.QUARTER
    )
    assert first_date == date(2024, 7, 1)
    assert last_date == date(2024, 9, 30)


def test_calculate_week_dates():
    """Test calculate_period_dates for a week."""
    first_date, last_date = PeriodFactory.calculate_period_dates(
        "2024-W1", PeriodType.WEEK
    )
    assert first_date == date(2024, 1, 1)  # Monday
    assert last_date == date(2024, 1, 7)  # Sunday

    first_date, last_date = PeriodFactory.calculate_period_dates(
        "2024-W10", PeriodType.WEEK
    )
    assert first_date == date(2024, 3, 4)
    assert last_date == date(2024, 3, 10)


def test_calculate_period_dates_invalid_id():
    """Test calculate_period_dates with a malformed period_id."""
    with pytest.raises(ValueError):
        PeriodFactory.calculate_period_dates("InvalidID", PeriodType.YEAR)


def test_shift_years():
    shifted_date = PeriodFactory.shift_date_by_n_periods(
        date(2024, 1, 1), PeriodType.YEAR, 2
    )
    assert shifted_date == date(2026, 1, 1)


def test_shift_months():
    """Test shifting various dates forward by n months."""

    # Start-of-month shift
    shifted_date = PeriodFactory.shift_date_by_n_periods(
        date(2024, 1, 1), PeriodType.MONTH, 2
    )
    assert shifted_date == date(2024, 3, 1)


def test_shift_months_negative():
    """Test shifting a date backward by a negative number of months."""

    # Start-of-month shift backward
    shifted_date = PeriodFactory.shift_date_by_n_periods(
        date(2027, 6, 1),
        PeriodType.MONTH,
        -72,  # Shift 6 years back
    )
    assert shifted_date == date(2021, 6, 1), f"Expected 2021-06-01, got {shifted_date}"


def test_shift_quarters():
    shifted_date = PeriodFactory.shift_date_by_n_periods(
        date(2024, 1, 1), PeriodType.QUARTER, 2
    )
    assert shifted_date == date(2024, 7, 1)


def test_shift_weeks():
    shifted_date = PeriodFactory.shift_date_by_n_periods(
        date(2024, 1, 1), PeriodType.WEEK, 2
    )
    assert shifted_date == date(2024, 1, 15)


def test_shift_period_by_n_month(factory: PeriodFactory):
    """Test shifting a monthly period forward and backward."""
    period = factory.get_period(period_id="Jun-2025")

    shifted_forward = factory.shift_period_by_n(period, 2)
    assert shifted_forward.period_id == "Aug-2025"

    shifted_backward = factory.shift_period_by_n(period, -3)
    assert shifted_backward.period_id == "Mar-2025"


def test_shift_period_by_n_quarter(factory: PeriodFactory):
    """Test shifting a quarterly period forward and backward."""
    period = factory.get_period(period_id="2025-Q2")

    shifted_forward = factory.shift_period_by_n(period, 1)
    assert shifted_forward.period_id == "2025-Q3"

    shifted_backward = factory.shift_period_by_n(period, -2)
    assert shifted_backward.period_id == "2024-Q4"


def test_shift_period_by_n_year(factory: PeriodFactory):
    """Test shifting a yearly period forward and backward."""
    period = factory.get_period(period_id="2025")

    shifted_forward = factory.shift_period_by_n(period, 1)
    assert shifted_forward.period_id == "2026"

    shifted_backward = factory.shift_period_by_n(period, -2)
    assert shifted_backward.period_id == "2023"


def test_shift_period_by_n_week(factory: PeriodFactory):
    """Test shifting a weekly period forward and backward."""
    period = factory.get_period(period_id="2025-W10")

    shifted_forward = factory.shift_period_by_n(period, 2)
    assert shifted_forward.period_id == "2025-W12"

    shifted_backward = factory.shift_period_by_n(period, -3)
    assert shifted_backward.period_id == "2025-W7"
