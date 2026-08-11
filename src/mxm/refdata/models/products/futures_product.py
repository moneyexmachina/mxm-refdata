"""Domain model for a futures product."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.settlement import SettlementMethod
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday


@dataclass(frozen=True)
class LastTradingRule:
    """Rule for deriving a futures contract's last trading day."""

    period_offset: int
    reference_event: ReferenceEvent
    n_reference: int
    business_day_offset: int
    weekday: Weekday | None = None

    def __post_init__(self) -> None:
        """Validate reference-event-specific requirements."""

        if (
            self.reference_event is ReferenceEvent.WEEKDAY_OF_PERIOD
            and self.weekday is None
        ):
            raise ValueError(
                "LastTradingRule.weekday is required when "
                "reference_event is WEEKDAY_OF_PERIOD"
            )


@dataclass(frozen=True)
class FirstDayOfInterestShiftRule:
    """Period shift used to derive a contract's first day of interest."""

    shift_period_type: PeriodType
    n_shift: Mapping[str, int]


@dataclass(frozen=True)
class FirstDayOfInterestRule:
    """Rule for deriving a contract's first day of interest."""

    shift_rule: FirstDayOfInterestShiftRule
    reference_rule: str


@dataclass(frozen=True)
class ContractRules:
    """Rules required to construct contracts for a futures product."""

    last_trading_rule: LastTradingRule
    first_day_of_interest_rule: FirstDayOfInterestRule


@dataclass(frozen=True)
class FuturesProduct:
    """Complete operational definition of one futures product.

    A FuturesProduct describes an exchange-defined offering together with
    the MXM rules required to construct its FuturesContract instances.

    Source-document format, curation metadata, repository revision, file
    location, and content digests are ingestion concerns and are deliberately
    excluded from this domain model.
    """

    product_id: str
    asset_class: str

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

    contract_rules: ContractRules

    trading_hours: str | None = None

    tick_size: float | None = None
    tick_value: float | None = None

    initial_margin: float | None = None
    maintenance_margin: float | None = None
