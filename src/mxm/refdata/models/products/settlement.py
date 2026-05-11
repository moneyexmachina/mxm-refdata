from enum import Enum


class SettlementMethod(Enum):
    """Settlement methods for FuturesProducts."""

    PHYSICAL = "physical"
    FINANCIAL = "financial"
    CASH = "cash"
    OTHER = "other"
