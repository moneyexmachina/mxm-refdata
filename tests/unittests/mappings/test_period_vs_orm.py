"""Tests for the mappings between Period and PeriodORM."""

from datetime import date

from mxm_refdata.mappings.period_vs_orm import period_from_orm, period_to_orm
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import Period, PeriodType


def test_period_to_orm():
    """Test mapping from Period to PeriodORM."""
    period = Period(
        period_id="2025-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2025, 1, 1),
        last_date=date(2025, 3, 31),
    )
    orm = period_to_orm(period)

    assert orm.period_id == "2025-Q1"
    assert orm.period_type == PeriodType.QUARTER
    assert orm.first_date == date(2025, 1, 1)
    assert orm.last_date == date(2025, 3, 31)


def test_period_from_orm():
    """Test mapping from PeriodORM to Period."""
    orm = PeriodORM(
        period_id="2025-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2025, 1, 1),
        last_date=date(2025, 3, 31),
    )
    period = period_from_orm(orm)

    assert period.period_id == "2025-Q1"
    assert period.period_type == PeriodType.QUARTER
    assert period.first_date == date(2025, 1, 1)
    assert period.last_date == date(2025, 3, 31)
