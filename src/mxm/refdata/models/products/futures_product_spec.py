"""Models for complete curated futures product specifications.

A FuturesProduct represents the exchange-defined product offering.

A FuturesProductSpec represents the complete MXM-owned specification around
that product, including source metadata and the rules required to construct
its FuturesContract instances.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.weekdays import Weekday


@dataclass(frozen=True)
class FuturesProductSourceStatus:
    """Lifecycle and review status of a curated product specification."""

    created_at: date
    updated_at: date
    review_status: str
    curator: str

    def __post_init__(self) -> None:
        if self.updated_at < self.created_at:
            raise ValueError(
                "FuturesProductSourceStatus.updated_at cannot precede created_at"
            )


@dataclass(frozen=True)
class FuturesProductProvenance:
    """Provenance of a curated futures product specification."""

    source_type: str
    source_url: str
    source_accessed_at: date
    curation_method: str
    assistance: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class LastTradingRule:
    """Rule for deriving a contract's last trading day."""

    period_offset: int
    reference_event: ReferenceEvent
    n_reference: int
    business_day_offset: int
    weekday: Weekday | None = None

    def __post_init__(self) -> None:
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
    """Period shift used when deriving a contract's first day of interest."""

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
class FuturesProductSpec:
    """Complete MXM-owned specification for one futures product.

    The nested FuturesProduct contains the exchange-defined product offering.

    The surrounding fields describe MXM's curated source record and contain
    the additional information required to construct and manage the product's
    FuturesContract instances.
    """

    schema_version: str
    product_id: str
    asset_class: str
    source_status: FuturesProductSourceStatus
    provenance: FuturesProductProvenance
    product: FuturesProduct
    contract_rules: ContractRules

    def __post_init__(self) -> None:
        if self.product_id != self.product.product_id:
            raise ValueError(
                "FuturesProductSpec.product_id does not match "
                "FuturesProduct.product_id: "
                f"{self.product_id!r} != {self.product.product_id!r}"
            )
