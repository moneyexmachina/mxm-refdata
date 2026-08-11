"""PostgreSQL integration tests for period-cycle SQL/schema compatibility.

These tests exercise the real migrated PostgreSQL schema. They prove that the
period-cycle SQL adapter matches that schema, that its selection operations
have the intended PostgreSQL semantics, and that the persisted identity,
position, and foreign-key constraints behave as required.

Generic transaction lifecycle is tested separately by ``PostgresDatabase`` and
at the higher-level materialisation integration boundary.
"""

from __future__ import annotations

from datetime import date
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
    fetch_period_cycle_memberships_by_cycle_ids,
    fetch_period_cycles,
    fetch_period_cycles_by_ids,
    insert_period_cycle_memberships,
    insert_period_cycles,
)
from mxm.refdata.sql.periods import insert_periods
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres


def _january_period() -> Period:
    """Return the January 2024 period."""

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


def _february_period() -> Period:
    """Return the February 2024 period."""

    return Period(
        period_id="2024-02",
        period_type=PeriodType.MONTH,
        first_date=date(
            2024,
            2,
            1,
        ),
        last_date=date(
            2024,
            2,
            29,
        ),
    )


def _march_period() -> Period:
    """Return the March 2024 period."""

    return Period(
        period_id="2024-03",
        period_type=PeriodType.MONTH,
        first_date=date(
            2024,
            3,
            1,
        ),
        last_date=date(
            2024,
            3,
            31,
        ),
    )


def _first_quarter_period() -> Period:
    """Return the first-quarter 2024 period."""

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
    """Return the persisted identity of one cycle membership."""

    return (
        membership.cycle_id,
        membership.period_id,
    )


def test_period_cycles_and_memberships_round_trip_and_filter_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Cycle writes, reads, and filtered lookups match the real schema."""

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
                january,
                february,
                first_quarter,
            ],
        )
        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
                quarters,
            ],
        )
        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                january_membership,
                february_membership,
                quarter_membership,
            ],
        )

    with database.transaction() as connection:
        persisted_cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )
        selected_cycles = fetch_period_cycles_by_ids(
            connection,
            schema=database.schema,
            cycle_ids=[
                "MISSING_CYCLE",
                months.cycle_id,
                months.cycle_id,
            ],
        )
        persisted_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )
        selected_memberships = fetch_period_cycle_memberships_by_cycle_ids(
            connection,
            schema=database.schema,
            cycle_ids=[
                quarters.cycle_id,
                quarters.cycle_id,
            ],
        )

    assert persisted_cycles == expected_cycles

    assert selected_cycles == {
        months.cycle_id: months,
    }

    assert persisted_memberships == expected_memberships

    assert selected_memberships == {
        _membership_key(quarter_membership): quarter_membership,
    }


def test_period_cycle_persistence_uses_postgres_conflict_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Identical cycle state is idempotent while conflicting state is rejected."""

    database = migrated_postgres_database

    months = _calendar_months_cycle()

    with database.transaction() as connection:
        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
            ],
        )

    with database.transaction() as connection:
        insert_period_cycles(
            connection,
            schema=database.schema,
            period_cycles=[
                months,
                months,
            ],
        )

    conflicting_months = _calendar_months_cycle(
        name="Changed Calendar Months",
        cycle_size=11,
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
                    conflicting_months,
                ],
            )

    with database.transaction() as connection:
        persisted_cycles = fetch_period_cycles(
            connection,
            schema=database.schema,
        )

    assert persisted_cycles == {
        months.cycle_id: months,
    }


def test_period_cycle_membership_persistence_uses_postgres_conflict_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Membership identity and cycle-position conflicts are both rejected."""

    database = migrated_postgres_database

    january = _january_period()
    february = _february_period()
    march = _march_period()
    months = _calendar_months_cycle()

    january_membership = _january_membership()
    february_membership = _february_membership()

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
                january_membership,
                february_membership,
            ],
        )

    with database.transaction() as connection:
        insert_period_cycle_memberships(
            connection,
            schema=database.schema,
            memberships=[
                february_membership,
                january_membership,
                january_membership,
            ],
        )

    conflicting_identity = _january_membership(
        cycle_element=3,
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
                    conflicting_identity,
                ],
            )

    conflicting_position = _march_membership(
        cycle_element=2,
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
                    conflicting_position,
                ],
            )

    with database.transaction() as connection:
        persisted_memberships = fetch_period_cycle_memberships(
            connection,
            schema=database.schema,
        )

    assert persisted_memberships == {
        _membership_key(january_membership): january_membership,
        _membership_key(february_membership): february_membership,
    }


@pytest.mark.parametrize(
    "missing_reference",
    [
        "cycle",
        "period",
    ],
)
def test_period_cycle_membership_foreign_keys_are_enforced(
    migrated_postgres_database: PostgresDatabase,
    missing_reference: Literal[
        "cycle",
        "period",
    ],
) -> None:
    """The real schema rejects memberships whose parent records are absent."""

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
