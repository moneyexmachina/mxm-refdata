"""PostgreSQL integration tests for period SQL/schema compatibility.

These tests exercise the real migrated PostgreSQL schema. They prove that the
period SQL adapter matches that schema, that its PostgreSQL query semantics are
correct, and that its idempotent/conflicting persistence behaviour works as
intended.

Generic transaction lifecycle is tested separately by ``PostgresDatabase`` and
at the higher-level materialisation integration boundary.
"""

from __future__ import annotations

from datetime import date

import pytest

from mxm.refdata.models import Period, PeriodType
from mxm.refdata.sql.periods import (
    PeriodConflictError,
    fetch_periods,
    fetch_periods_by_types,
    fetch_periods_in_range,
    insert_periods,
)
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres


def _month_period() -> Period:
    """Return a representative monthly period."""

    return Period(
        period_id="2024-01",
        period_type=PeriodType.MONTH,
        first_date=date(
            2024,
            1,
            1,
        ),
        last_date=date(
            2024,
            1,
            31,
        ),
    )


def _quarter_period() -> Period:
    """Return a representative quarterly period."""

    return Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(
            2024,
            1,
            1,
        ),
        last_date=date(
            2024,
            3,
            31,
        ),
    )


def _year_period() -> Period:
    """Return a representative yearly period."""

    return Period(
        period_id="2024",
        period_type=PeriodType.YEAR,
        first_date=date(
            2024,
            1,
            1,
        ),
        last_date=date(
            2024,
            12,
            31,
        ),
    )


def test_periods_round_trip_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Period writes and reads match the real migrated PostgreSQL schema."""

    database = migrated_postgres_database

    month = _month_period()
    quarter = _quarter_period()
    year = _year_period()

    expected_periods = {
        month.period_id: month,
        quarter.period_id: quarter,
        year.period_id: year,
    }

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                quarter,
                year,
                month,
            ],
        )

    with database.transaction() as connection:
        persisted_periods = fetch_periods(
            connection,
            schema=database.schema,
        )

    assert persisted_periods == expected_periods


def test_period_queries_use_postgres_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Period type and date-range queries return the intended PostgreSQL rows."""

    database = migrated_postgres_database

    month = _month_period()
    quarter = _quarter_period()
    year = _year_period()

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                month,
                quarter,
                year,
            ],
        )

    with database.transaction() as connection:
        cycle_periods = fetch_periods_by_types(
            connection,
            schema=database.schema,
            period_types=[
                PeriodType.MONTH,
                PeriodType.QUARTER,
            ],
        )

        first_quarter_periods = fetch_periods_in_range(
            connection,
            schema=database.schema,
            start_date=date(
                2024,
                1,
                1,
            ),
            end_date=date(
                2024,
                3,
                31,
            ),
        )

        january_periods = fetch_periods_in_range(
            connection,
            schema=database.schema,
            start_date=date(
                2024,
                1,
                1,
            ),
            end_date=date(
                2024,
                1,
                31,
            ),
        )

    assert cycle_periods == {
        month.period_id: month,
        quarter.period_id: quarter,
    }

    assert first_quarter_periods == {
        month.period_id: month,
        quarter.period_id: quarter,
    }

    assert january_periods == {
        month.period_id: month,
    }


def test_period_persistence_uses_postgres_conflict_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Identical period state is idempotent while conflicting state is rejected."""

    database = migrated_postgres_database

    month = _month_period()
    quarter = _quarter_period()

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                month,
                quarter,
            ],
        )

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                quarter,
                month,
                month,
            ],
        )

    with database.transaction() as connection:
        persisted_periods = fetch_periods(
            connection,
            schema=database.schema,
        )

    assert persisted_periods == {
        month.period_id: month,
        quarter.period_id: quarter,
    }

    conflicting_month = Period(
        period_id=month.period_id,
        period_type=month.period_type,
        first_date=month.first_date,
        last_date=date(
            2024,
            2,
            1,
        ),
    )

    with pytest.raises(
        PeriodConflictError,
        match=r"Persisted period conflicts.*2024-01",
    ):
        with database.transaction() as connection:
            insert_periods(
                connection,
                schema=database.schema,
                periods=[
                    conflicting_month,
                ],
            )

    with database.transaction() as connection:
        persisted_after_conflict = fetch_periods(
            connection,
            schema=database.schema,
        )

    assert persisted_after_conflict == {
        month.period_id: month,
        quarter.period_id: quarter,
    }
