"""Mapping Period instances to and from PeriodORM instances."""

from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import Period, PeriodType


def period_to_orm(period: Period) -> PeriodORM:
    """
    Map an internal Period object to a PeriodORM instance.

    Args:
        period (Period): Internal Period instance.

    Returns:
        PeriodORM: Corresponding ORM representation.
    """
    return PeriodORM(
        period_id=period.period_id,
        period_type=period.period_type,
        first_date=period.first_date,
        last_date=period.last_date,
    )


def period_from_orm(orm: PeriodORM) -> Period:
    """
    Map a PeriodORM instance to an internal Period object.

    Args:
        orm (PeriodORM): ORM representation of a Period.

    Returns:
        Period: Internal representation of the Period.
    """
    return Period(
        period_id=orm.period_id,
        period_type=PeriodType[orm.period_type.name],
        first_date=orm.first_date,
        last_date=orm.last_date,
    )
