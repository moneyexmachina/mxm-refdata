# mxm_refdata/models/period_cycles.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mxm_refdata.models.periods import PeriodType


class CycleInstanceKind(str, Enum):
    """
    Defines what 'cycle_instance' means for a membership row.

    For calendar cycles, the instance is the calendar year.
    Other instance kinds may be added later (e.g. gas_year).
    """

    YEAR = "YEAR"


@dataclass(frozen=True)
class PeriodCycle:
    """
    Defines a cycle over periods.

    A cycle is an interpretation layer over Periods, not a property of Period itself.

    Example cycles:
    - CALENDAR_MONTHS: element=1..12, instance=year, applies to PeriodType.MONTH
    - CALENDAR_QUARTERS: element=1..4, instance=year, applies to PeriodType.QUARTER
    """

    cycle_id: str  # stable identifier, e.g. "CALENDAR_MONTHS"
    name: str  # human readable
    period_type: PeriodType  # the period type this cycle classifies
    cycle_size: int  # number of elements in one cycle (12, 4, ...)
    instance_kind: CycleInstanceKind = CycleInstanceKind.YEAR

    def __post_init__(self) -> None:
        if not self.cycle_id:
            raise ValueError("cycle_id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")
        if self.cycle_size < 1:
            raise ValueError("cycle_size must be >= 1")


@dataclass(frozen=True)
class PeriodCycleMembership:
    """
    Membership relation: places a specific Period into a given cycle.

    A Period may be a member of multiple cycles.
    A cycle may contain many periods.

    cycle_instance:
        For YEAR instance_kind cycles, this is the calendar year.
        (Other instance kinds may be introduced later.)
    """

    cycle_id: str
    period_id: str
    cycle_instance: int
    cycle_element: int  # 1..cycle_size

    def __post_init__(self) -> None:
        if not self.cycle_id:
            raise ValueError("cycle_id must be non-empty")
        if not self.period_id:
            raise ValueError("period_id must be non-empty")
        if self.cycle_instance <= 0:
            raise ValueError("cycle_instance must be > 0")
        if self.cycle_element < 1:
            raise ValueError("cycle_element must be >= 1")
