"""ORM model for the futures_products table."""

from sqlalchemy import Column, Enum, Float, String, Text
from sqlalchemy.orm import relationship

from mxm_refdata.models.orm.base import Base
from mxm_refdata.models.products.futures_product import (
    Currency,
    PeriodType,
    ProductUnit,
    SettlementMethod,
)


class FuturesProductORM(Base):
    """ORM model for the futures_products table."""

    __tablename__ = "futures_products"

    product_id = Column(String, primary_key=True, nullable=False)
    venue = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    currency = Column(Enum(Currency), nullable=False)
    unit = Column(Enum(ProductUnit), nullable=False)
    contract_size = Column(Float, nullable=False)
    valid_period_rule = Column(Text, nullable=False)
    listing_rule = Column(Text, nullable=False)
    period_types = Column(Enum(PeriodType), nullable=False)
    settlement = Column(Enum(SettlementMethod), nullable=False)
    last_trading_rule = Column(Text, nullable=False)
    expiry_rule = Column(Text, nullable=False)
    trading_calendar = Column(String, nullable=False)
    trading_hours = Column(Text, nullable=True)
    tick_size = Column(Float, nullable=True)
    tick_value = Column(Float, nullable=True)
    initial_margin = Column(Float, nullable=True)
    maintenance_margin = Column(Float, nullable=True)

    contracts = relationship(
        "FuturesContractORM", back_populates="product", cascade="all, delete-orphan"
    )
