"""PostgreSQL integration tests for period-cycle persistence.

These tests use the shared migrated disposable-schema fixture. They exercise
real PostgreSQL constraints, conflict handling, transaction rollback, and
round-trip reconstruction for period cycles and their memberships.
"""

from __future__ import annotations

from typing import Literal

import pytest
from psycopg.errors import ForeignKeyViolation

from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.sql.period_cycles import (
    PeriodCycleConflictError,
    fetch_period_cycle_memberships,
    fetch_period_cycles,
    insert_period_cycle_memberships,
    insert_period_cycles,
)
from mxm.refdata.sql.periods import insert_periods
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres


def _january_period() -> Period:
    """Return the January 2024 period."""

    from datetime import date

    return Period(
        period_id="2024-01",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 31),
    )


def _february_period() -> Period:
    """Return the February 2024 period."""

    from datetime import date

    return Period(
        period_id="2024-02",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 2, 1),
        last_date=date(2024, 2, 29),
    )


def _march_period() -> Period:
    """Return the March 2024 period."""

    from datetime import date

    return Period(
        period_id="2024-03",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 3, 1),
        last_date=date(2024, 3, 31),
    )


def _first_quarter_period() -> Period:
    """Return the first-quarter 2024 period."""

    from datetime import date

    return Period(
        period_id="2024-Q1",
        period_type=PeriodType.QUARTER,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )


def _calendar_months_cycle(
    *,
    name: str = "Calendar Months",
    cycle_size: int = 12,
) -> PeriodCycle:
    """Return the calendar-month cycle definition."""

    return PeriodCycle(
        cycle_id="CALENDAR_MONTHS",
        name=name,
        period_type=PeriodType.MONTH,
        cycle_size=cycle_size,
        instance_kind=CycleInstanceKind.YEAR,
    )


def _calendar_quarters_cycle() -> PeriodCycle:
    """Return the calendar-quarter cycle definition."""

    return PeriodCycle(
        cycle_id="CALENDAR_QUARTERS",
        name="Calendar Quarters",
        period_type=PeriodType.QUARTER,
        cycle_size=4,
        instance_kind=CycleInstanceKind.YEAR,
    )


def _january_membership(
    *,
    cycle_element: int = 1,
) -> PeriodCycleMembership:
    """Return the January 2024 month-cycle membership."""

    return PeriodCycleMembership(
        cycle_id="CALENDAR_MONTHS",
        period_id="2024-01",
        cycle_instance=2024,
        cycle_element=cycle_element,
    )


def _february_membership(
    *,
    cycle_element: int = 2,
) -> PeriodCycleMembership:
    """Return the February 2024 month-cycle membership."""

    return PeriodCycleMembership(
        cycle_id="CALENDAR_MONTHS",
        period_id="2024-02",
        cycle_instance=2024,
        cycle_element=cycle_element,
    )


def _march_membership(
    *,
    cycle_element: int = 3,
) -> PeriodCycleMembership:
    """Return the March 2024 month-cycle membership."""

    return PeriodCycleMembership(
        cycle_id="CALENDAR_MONTHS",
        period_id="2024-03",
        cycle_instance=2024,
        cycle_element=cycle_element,
    )


def _first_quarter_membership() -> PeriodCycleMembership:
    """Return the first-quarter 2024 quarter-cycle membership."""

    return PeriodCycleMembership(
        cycle_id="CALENDAR_QUARTERS",
        period_id="2024-Q1",
        cycle_instance=2024,
        cycle_element=1,
    )


def _membership_key(
    membership: PeriodCycleMembership,
) -> tuple[str, str]:
    """Return the persisted primary identity of one membership."""

    return (
        membership.cycle_id,
        membership.period_id,
    )


def test_period_cycles_and_memberships_round_trip_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Persist and reconstruct cycles and memberships in one transaction."""

    database = migrated_postgres_database

    january = _january_period()
    february = _february_period()
    first_quarter = _first_quarter_period()

    months = _calendar_months_cycle()
    quarters = _calendar_quarters_cycle()

    january_membership = _january_membership()
    february_membership = _february_membership()
    quarter_membership = _first_quarter_membership()

    expected_cycles = {
        months.cycle_id: months,
        quarters.cycle_id: quarters,
    }

    expected_memberships = {
        _membership_key(january_membership): january_membership,
        _membership_key(february_membership): february_membership,
        _membership_key(quarter_membership): quarter_membership,
    }

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                first_quarter,
                february,
                january,
            ],
        )

        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                quarters,
                months,
            ],
        )

        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                quarter_membership,
                february_membership,
                january_membership,
            ],
        )

        transaction_cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )

        transaction_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert transaction_cycles == expected_cycles
    assert transaction_memberships == expected_memberships

    with database.transaction() as connection:
        committed_cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )

        committed_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert committed_cycles == expected_cycles
    assert committed_memberships == expected_memberships


def test_identical_cycle_and_membership_insertion_is_idempotent(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Replaying identical cycle state leaves persisted state unchanged."""

    database = migrated_postgres_database

    january = _january_period()
    february = _february_period()

    months = _calendar_months_cycle()

    january_membership = _january_membership()
    february_membership = _february_membership()

    expected_cycles = {
        months.cycle_id: months,
    }

    expected_memberships = {
        _membership_key(january_membership): january_membership,
        _membership_key(february_membership): february_membership,
    }

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                january,
                february,
            ],
        )

        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
            ],
        )

        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                january_membership,
                february_membership,
            ],
        )

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                february,
                january,
                january,
            ],
        )

        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
                months,
            ],
        )

        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                february_membership,
                january_membership,
                january_membership,
            ],
        )

    with database.transaction() as connection:
        persisted_cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )

        persisted_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert persisted_cycles == expected_cycles
    assert persisted_memberships == expected_memberships


def test_conflicting_cycle_rolls_back_other_cycle_inserts(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """A cycle identity conflict rolls back new cycles in its transaction."""

    database = migrated_postgres_database

    original_months = _calendar_months_cycle()
    conflicting_months = _calendar_months_cycle(
        name="Changed Calendar Months",
        cycle_size=11,
    )

    quarters = _calendar_quarters_cycle()

    with database.transaction() as connection:
        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                original_months,
            ],
        )

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"Persisted period cycle conflicts.*CALENDAR_MONTHS",
    ):
        with database.transaction() as connection:
            insert_period_cycles(
                connection,
                schema=database.schema,
                period_cycles=[
                    quarters,
                    conflicting_months,
                ],
            )

    with database.transaction() as connection:
        persisted_cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )

    assert persisted_cycles == {
        original_months.cycle_id: original_months,
    }

    assert quarters.cycle_id not in persisted_cycles


def test_membership_identity_conflict_rolls_back_other_membership_inserts(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """A primary-identity conflict rolls back other membership writes."""

    database = migrated_postgres_database

    january = _january_period()
    february = _february_period()
    months = _calendar_months_cycle()

    original_january = _january_membership(
        cycle_element=1,
    )

    conflicting_january = _january_membership(
        cycle_element=3,
    )

    new_february = _february_membership(
        cycle_element=2,
    )

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                january,
                february,
            ],
        )

        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
            ],
        )

        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                original_january,
            ],
        )

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"membership conflicts.*identity",
    ):
        with database.transaction() as connection:
            insert_period_cycle_memberships(
                connection,
                schema=database.schema,
                memberships=[
                    new_february,
                    conflicting_january,
                ],
            )

    with database.transaction() as connection:
        persisted_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert persisted_memberships == {
        _membership_key(original_january): original_january,
    }

    assert _membership_key(new_february) not in persisted_memberships


def test_membership_position_conflict_rolls_back_other_membership_inserts(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """A unique-position conflict rolls back other membership writes."""

    database = migrated_postgres_database

    january = _january_period()
    february = _february_period()
    march = _march_period()
    months = _calendar_months_cycle()

    original_january = _january_membership(
        cycle_element=1,
    )

    conflicting_february = _february_membership(
        cycle_element=1,
    )

    new_march = _march_membership(
        cycle_element=2,
    )

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                january,
                february,
                march,
            ],
        )

        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
            ],
        )

        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                original_january,
            ],
        )

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"position is occupied by a different membership",
    ):
        with database.transaction() as connection:
            insert_period_cycle_memberships(
                connection,
                schema=database.schema,
                memberships=[
                    conflicting_february,
                    new_march,
                ],
            )

    with database.transaction() as connection:
        persisted_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert persisted_memberships == {
        _membership_key(original_january): original_january,
    }

    assert _membership_key(conflicting_february) not in persisted_memberships
    assert _membership_key(new_march) not in persisted_memberships


@pytest.mark.parametrize(
    "missing_reference",
    [
        "cycle",
        "period",
    ],
)
def test_membership_foreign_keys_are_enforced(
    migrated_postgres_database: PostgresDatabase,
    missing_reference: Literal["cycle", "period"],
) -> None:
    """PostgreSQL rejects memberships with missing parent records."""

    database = migrated_postgres_database

    january = _january_period()
    months = _calendar_months_cycle()
    membership = _january_membership()

    with database.transaction() as connection:
        if missing_reference == "cycle":
            insert_periods(
                connection,
                schema=database.schema,
                periods=[
                    january,
                ],
            )
        else:
            insert_period_cycles(
                connection,
                schema=database.schema,
                period_cycles=[
                    months,
                ],
            )

    with pytest.raises(ForeignKeyViolation):
        with database.transaction() as connection:
            insert_period_cycle_memberships(
                connection,
                schema=database.schema,
                memberships=[
                    membership,
                ],
            )

    with database.transaction() as connection:
        persisted_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert persisted_memberships == {}
