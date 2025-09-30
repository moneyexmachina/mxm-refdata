from sqlalchemy import Column, Date, Enum, String
from sqlalchemy.orm import relationship

from mxm_refdata.models.orm.base import Base
from mxm_refdata.models.periods import PeriodType


class PeriodORM(Base):
    """ORM model for the periods table."""

    __tablename__ = "periods"

    period_id = Column(String, primary_key=True, unique=True, nullable=False)
    period_type = Column(Enum(PeriodType), nullable=False)
    first_date = Column(Date, nullable=False)
    last_date = Column(Date, nullable=False)

    contracts = relationship("FuturesContractORM", back_populates="period")
