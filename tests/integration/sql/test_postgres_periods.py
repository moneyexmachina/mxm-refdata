"""PostgreSQL integration tests for plain-SQL period persistence."""

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
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 31),
    )


def _quarter_period() -> Period:
    """Return a representative quarterly period."""

    return Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )


def _year_period() -> Period:
    """Return a representative yearly period."""

    return Period(
        period_id="2024",
        period_type=PeriodType.YEAR,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 12, 31),
    )


def test_periods_round_trip_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Persist and reconstruct representative periods."""

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

        persisted_periods = fetch_periods(
            connection,
            schema=database.schema,
        )

    assert persisted_periods == expected_periods

    with database.transaction() as connection:
        committed_periods = fetch_periods(
            connection,
            schema=database.schema,
        )

    assert committed_periods == expected_periods


def test_period_type_and_range_queries_use_postgres_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Filter persisted periods by type and inclusive containment range."""

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
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
        )

        january_periods = fetch_periods_in_range(
            connection,
            schema=database.schema,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
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


def test_identical_period_insertion_is_idempotent(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Reinserting identical periods leaves persisted state unchanged."""

    database = migrated_postgres_database

    month = _month_period()
    quarter = _quarter_period()

    expected_periods = {
        month.period_id: month,
        quarter.period_id: quarter,
    }

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

    assert persisted_periods == expected_periods


def test_conflicting_period_rolls_back_complete_transaction(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """A period identity conflict rolls back other writes in its transaction."""

    database = migrated_postgres_database

    original_month = _month_period()

    conflicting_month = Period(
        period_id=original_month.period_id,
        period_type=original_month.period_type,
        first_date=original_month.first_date,
        last_date=date(2024, 2, 1),
    )

    additional_quarter = _quarter_period()

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                original_month,
            ],
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
                    additional_quarter,
                ],
            )

    with database.transaction() as connection:
        persisted_periods = fetch_periods(
            connection,
            schema=database.schema,
        )

    assert persisted_periods == {
        original_month.period_id: original_month,
    }

    assert additional_quarter.period_id not in persisted_periods
