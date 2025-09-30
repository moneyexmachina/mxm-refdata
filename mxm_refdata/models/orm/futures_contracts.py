"""ORM model for the futures_contracts table."""

from sqlalchemy import Column, Enum, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from mxm_refdata.models.orm.base import Base
from mxm_refdata.models.products.futures_product import (
    Currency,
    ProductUnit,
)


class FuturesContractORM(Base):
    """ORM model for the futures_contracts table."""

    __tablename__ = "futures_contracts"

    contract_id = Column(
        String, primary_key=True, nullable=False
    )  # Unique contract identifier
    product_id = Column(
        String, ForeignKey("futures_products.product_id"), nullable=False
    )  # Foreign key to FuturesProduct
    period_id = Column(
        String, ForeignKey("periods.period_id"), nullable=False
    )  # Foreign key to Period
    contract_size = Column(Float, nullable=False)  # Size of the contract
    currency = Column(Enum(Currency), nullable=False)
    unit = Column(Enum(ProductUnit), nullable=False)
    trading_calendar = Column(
        String, nullable=False
    )  # Trading calendar of the contract
    first_day_of_interest = Column(
        String, nullable=False
    )  # First day of interest for the contract
    last_trading_day = Column(
        String, nullable=False
    )  # Last trading day for the contract

    # Relationships
    product = relationship("FuturesProductORM", back_populates="contracts")
    period = relationship("PeriodORM", back_populates="contracts")
