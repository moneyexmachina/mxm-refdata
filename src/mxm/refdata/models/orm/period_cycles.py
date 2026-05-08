# mxm_refdata/models/orm/period_cycles.py

from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mxm.refdata.models.orm.base import Base
from mxm.refdata.models.orm.periods import PeriodORM


class PeriodCycleORM(Base):
    __tablename__ = "period_cycles"

    cycle_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    period_type: Mapped[str] = mapped_column(nullable=False)
    instance_kind: Mapped[str] = mapped_column(nullable=False)
    cycle_size: Mapped[int] = mapped_column(nullable=False)

    # Relationship: one cycle -> many memberships
    memberships = relationship(
        "PeriodCycleMembershipORM",
        back_populates="cycle",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"PeriodCycleORM(cycle_id={self.cycle_id!r}, name={self.name!r}, "
            f"period_type={self.period_type!r}, instance_kind={self.instance_kind!r}, "
            f"cycle_size={self.cycle_size!r})"
        )


class PeriodCycleMembershipORM(Base):
    """
    ORM table: period_cycle_memberships

    Membership relation: places a specific Period into a given PeriodCycle.
    """

    __tablename__ = "period_cycle_memberships"

    # Composite primary key: one period per cycle
    cycle_id: Mapped[str] = mapped_column(
        ForeignKey("period_cycles.cycle_id", ondelete="CASCADE"),
        primary_key=True,
    )

    period_id: Mapped[str] = mapped_column(
        ForeignKey("periods.period_id", ondelete="CASCADE"),
        primary_key=True,
    )

    cycle_instance: Mapped[int] = mapped_column(nullable=False)
    cycle_element: Mapped[int] = mapped_column(nullable=False)

    # Relationships
    cycle: Mapped["PeriodCycleORM"] = relationship(
        back_populates="memberships",
        lazy="select",
    )

    period: Mapped["PeriodORM"] = relationship(
        lazy="select",
    )

    __table_args__ = (
        UniqueConstraint(
            "cycle_id",
            "cycle_instance",
            "cycle_element",
            name="uq_cycle_instance_element",
        ),
    )

    def __repr__(self) -> str:
        return (
            "PeriodCycleMembershipORM("
            f"cycle_id={self.cycle_id!r}, "
            f"period_id={self.period_id!r}, "
            f"cycle_instance={self.cycle_instance!r}, "
            f"cycle_element={self.cycle_element!r})"
        )
