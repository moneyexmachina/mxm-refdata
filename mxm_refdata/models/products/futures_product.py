"""DataClass for a futures product."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from mxm_refdata.models.currencies import Currency
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.models.units import ProductUnit


class SettlementMethod(Enum):
    """Settlement methods for FuturesProducts."""

    PHYSICAL = "physical"
    FINANCIAL = "financial"
    CASH = "cash"
    OTHER = "other"


@dataclass(frozen=True)
class FuturesProduct:
    """Represents a tradeable futures product."""

    product_id: str  # Internal product code (aligned with venue's default code)
    venue: str  # The venue (e.g., exchange or counterparty) offering the product
    description: str  # Long-form name and/or description
    currency: Currency  # Currency of the product (from Currency enum)
    unit: ProductUnit  # Physical unit (from ProductUnit enum)
    contract_size: float  # Number of physical units per contract
    valid_period_rule: (
        str  # Rule for determining valid trading periods (e.g., "FGHJKMNQUVXZ")
    )
    listing_rule: (
        str  # Rule for determining available contracts (e.g., "monthly for all months")
    )
    period_types: tuple[PeriodType, ...]
    settlement: SettlementMethod  # Settlement type (physical, financial, etc.)
    last_trading_rule: str  # Rule for determining last trading day (e.g., "3rd last business day of delivery month")
    expiry_rule: str  # Rule for determining contract expiry (e.g., "3rd Friday of delivery month")
    trading_calendar: (
        str  # Placeholder for the trading calendar rule (e.g. CME default)
    )
    trading_hours: Optional[str] = None  # String representation of trading hours
    tick_size: Optional[float] = None
    tick_value: Optional[float] = None
    initial_margin: Optional[float] = None
    maintenance_margin: Optional[float] = None
