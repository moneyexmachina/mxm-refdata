"""
ORM model for the futures_products table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mxm.refdata.models.orm.base import Base
from mxm.refdata.models.products.futures_product import (
    Currency,
    ProductUnit,
    SettlementMethod,
)

if TYPE_CHECKING:
    from mxm.refdata.models.orm.futures_contracts import FuturesContractORM


class FuturesProductORM(Base):
    """ORM model for the futures_products table."""

    __tablename__ = "futures_products"

    product_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    venue: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    unit: Mapped[ProductUnit] = mapped_column(Enum(ProductUnit), nullable=False)
    contract_size: Mapped[float] = mapped_column(Float, nullable=False)

    valid_period_rule: Mapped[str] = mapped_column(Text, nullable=False)
    listing_rule: Mapped[str] = mapped_column(Text, nullable=False)

    period_types: Mapped[str] = mapped_column(Text, nullable=False)

    settlement: Mapped[SettlementMethod] = mapped_column(
        Enum(SettlementMethod), nullable=False
    )
    last_trading_rule: Mapped[str] = mapped_column(Text, nullable=False)
    expiry_rule: Mapped[str] = mapped_column(Text, nullable=False)

    trading_calendar: Mapped[str] = mapped_column(String, nullable=False)

    trading_hours: Mapped[str | None] = mapped_column(Text, nullable=True)

    tick_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    tick_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    initial_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    maintenance_margin: Mapped[float | None] = mapped_column(Float, nullable=True)

    contracts: Mapped[list[FuturesContractORM]] = relationship(
        "FuturesContractORM",
        back_populates="product",
        cascade="all, delete-orphan",
    )
