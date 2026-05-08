from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mxm.refdata.models.orm.base import Base
from mxm.refdata.models.periods import PeriodType

if TYPE_CHECKING:
    from mxm.refdata.models.orm.futures_contracts import FuturesContractORM


class PeriodORM(Base):
    """ORM model for the periods table."""

    __tablename__ = "periods"

    period_id: Mapped[str] = mapped_column(
        String, primary_key=True, unique=True, nullable=False
    )
    period_type: Mapped[PeriodType] = mapped_column(Enum(PeriodType), nullable=False)
    first_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_date: Mapped[date] = mapped_column(Date, nullable=False)

    contracts: Mapped[list["FuturesContractORM"]] = relationship(
        "FuturesContractORM", back_populates="period"
    )
