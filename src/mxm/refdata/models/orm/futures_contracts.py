"""
ORM model for the futures_contracts table.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mxm.refdata.models.orm.base import Base
from mxm.refdata.models.products.futures_product import Currency, ProductUnit

if TYPE_CHECKING:
    from mxm.refdata.models.orm.futures_products import FuturesProductORM
    from mxm.refdata.models.orm.periods import PeriodORM


class FuturesContractORM(Base):
    """ORM model for the futures_contracts table."""

    __tablename__ = "futures_contracts"

    contract_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)

    product_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("futures_products.product_id"),
        nullable=False,
    )

    period_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("periods.period_id"),
        nullable=False,
    )

    contract_size: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    unit: Mapped[ProductUnit] = mapped_column(Enum(ProductUnit), nullable=False)

    trading_calendar: Mapped[str] = mapped_column(String, nullable=False)

    first_day_of_interest: Mapped[date] = mapped_column(Date, nullable=False)
    last_trading_day: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    product: Mapped["FuturesProductORM"] = relationship(
        "FuturesProductORM", back_populates="contracts"
    )
    period: Mapped["PeriodORM"] = relationship("PeriodORM", back_populates="contracts")
