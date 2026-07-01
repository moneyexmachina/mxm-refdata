from __future__ import annotations

from dataclasses import dataclass

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.settlement import SettlementMethod
from mxm.refdata.models.units import ProductUnit


@dataclass(frozen=True)
class FuturesProduct:
    """Represents a tradeable futures product.

    This is the canonical domain reconstruction boundary.

    `from_dict` consumes a fully normalised JSON-compatible object
    (typically produced by CSV or JSON loaders) and converts it into
    a strongly typed domain model.

    This is the ONLY supported entry point for external reconstruction.
    """

    product_id: str
    venue: str
    description: str
    currency: Currency
    unit: ProductUnit
    contract_size: float
    valid_period_rule: str
    listing_rule: str
    period_types: tuple[PeriodType, ...]
    settlement: SettlementMethod
    last_trading_rule: str
    expiry_rule: str
    trading_calendar: str
    trading_hours: str | None = None
    tick_size: float | None = None
    tick_value: float | None = None
    initial_margin: float | None = None
    maintenance_margin: float | None = None
