"""Future contract class."""

import datetime
from dataclasses import dataclass

from mxm.refdata.models import Currency, ProductUnit
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


@dataclass(frozen=True)
class FuturesContract:
    """Represents an individual futures contract."""

    contract_id: str  # Unique identifier for the contract
    product_id: str  # Reference to the product ID
    period_id: str  # Reference to the period ID
    contract_size: float  # The specific size of this contract
    unit: ProductUnit  # Pre-populated unit of the product
    currency: Currency  # Pre-populated currency of the product
    trading_calendar: TradingCalendar  # Pre-populated trading calendar of the product
    first_day_of_interest: datetime.date  # The first day of interest for the contract
    last_trading_day: datetime.date  # The last trading day for the contract
