"""
mxm.refdata.mappings.period_cycles_vs_orm

ORM ↔ domain mappings for PeriodCycle and PeriodCycleMembership.

Purpose
-------
`mxm-refdata` stores Period cycles as authoritative reference-data artifacts.
A PeriodCycle is a definition of a cycle over delivery periods, and a
PeriodCycleMembership places a specific Period into a given cycle with a
(cycle_instance, cycle_element) assignment.

This module provides the pure mapping functions between:
- ORM models in `mxm.refdata.models.orm.period_cycles`
and
- domain models in `mxm.refdata.models.period_cycles`

Conventions
-----------
- Enums are stored in the database as strings.
- PeriodType is stored as `PeriodType.name` (e.g. "MONTH", "QUARTER").
- CycleInstanceKind is stored as its `.value` (e.g. "YEAR").

These conventions should be kept stable to preserve refdata portability and
auditability.
"""

from __future__ import annotations

from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.models.periods import PeriodType

# ---------------------------------------------------------------------------
# PeriodCycle
# ---------------------------------------------------------------------------


def period_cycle_from_orm(orm: PeriodCycleORM) -> PeriodCycle:
    """
    Map ORM -> domain PeriodCycle.
    """
    return PeriodCycle(
        cycle_id=orm.cycle_id,
        name=orm.name,
        period_type=PeriodType[orm.period_type],  # stored as PeriodType.name
        cycle_size=int(orm.cycle_size),
        instance_kind=CycleInstanceKind(orm.instance_kind),  # stored as .value
    )


def period_cycle_to_orm(model: PeriodCycle) -> PeriodCycleORM:
    """
    Map domain -> ORM PeriodCycleORM.
    """
    return PeriodCycleORM(
        cycle_id=model.cycle_id,
        name=model.name,
        period_type=model.period_type.name,  # store as PeriodType.name
        instance_kind=model.instance_kind.value,  # store as .value
        cycle_size=int(model.cycle_size),
    )


# ---------------------------------------------------------------------------
# PeriodCycleMembership
# ---------------------------------------------------------------------------


def period_cycle_membership_from_orm(
    orm: PeriodCycleMembershipORM,
) -> PeriodCycleMembership:
    """
    Map ORM -> domain PeriodCycleMembership.
    """
    return PeriodCycleMembership(
        cycle_id=orm.cycle_id,
        period_id=orm.period_id,
        cycle_instance=int(orm.cycle_instance),
        cycle_element=int(orm.cycle_element),
    )


def period_cycle_membership_to_orm(
    model: PeriodCycleMembership,
) -> PeriodCycleMembershipORM:
    """
    Map domain -> ORM PeriodCycleMembershipORM.
    """
    return PeriodCycleMembershipORM(
        cycle_id=model.cycle_id,
        period_id=model.period_id,
        cycle_instance=int(model.cycle_instance),
        cycle_element=int(model.cycle_element),
    )
