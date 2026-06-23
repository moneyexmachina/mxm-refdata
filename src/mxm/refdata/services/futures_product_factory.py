"""
Factory for FuturesProduct instances.

Semantics
---------
- This factory provides *interning*: at most one FuturesProduct instance per
  product_id within this process.
- It may be initialised from CSV for convenience.
- It also supports construction from a typed dict payload (useful for tests),
  but the preferred path is to parse into FuturesProduct and then intern.
"""

from __future__ import annotations

from typing import Any, TypedDict, cast

from mxm.refdata.config import RefDataConfigData
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.parsing.futures_products_from_csv import parse_futures_products_csv


class FuturesProductSpec(TypedDict, total=False):
    """
    Typed input payload for creating FuturesProduct instances.

    Intended primarily for tests/fixtures and controlled programmatic creation.

    Notes:
      - This is *not* persisted format.
      - period_types must already be canonical: tuple[PeriodType, ...].
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
    trading_hours: str | None
    tick_size: float | None
    tick_value: float | None
    initial_margin: float | None
    maintenance_margin: float | None


class FuturesProductFactory:
    """Factory / interning cache for FuturesProduct instances."""

    def __init__(self) -> None:
        """Initialise an empty product interning cache."""
        self._cache: dict[str, FuturesProduct] = {}

    # -------------------------
    # Core cache operations
    # -------------------------

    def intern(self, product: FuturesProduct) -> FuturesProduct:
        """
        Return the canonical FuturesProduct instance for product.product_id.
        """
        cached = self._cache.get(product.product_id)
        if cached is None:
            self._cache[product.product_id] = product
            return product
        return cached

    def get(self, product_id: str) -> FuturesProduct | None:
        """Return product if present, else None."""
        return self._cache.get(product_id)

    def require(self, product_id: str) -> FuturesProduct:
        """Return product if present, else raise."""
        p = self._cache.get(product_id)
        if p is None:
            raise KeyError(f"Unknown product_id: {product_id!r}")
        return p

    def all(self) -> list[FuturesProduct]:
        """Return all cached products (order not guaranteed)."""
        return list(self._cache.values())

    def clear(self) -> None:
        """Clear the cache (useful in tests)."""
        self._cache.clear()

    # -------------------------
    # Construction helpers
    # -------------------------

    def create_from_spec(self, spec: FuturesProductSpec) -> FuturesProduct:
        """
        Create (and intern) a FuturesProduct from a typed spec payload.

        This is useful for tests, fixtures, and programmatic creation.

        Requirements:
          - spec must include product_id and all required FuturesProduct fields.
          - period_types must be a tuple[PeriodType, ...] (canonical).
        """
        if "product_id" not in spec or not spec["product_id"]:
            raise ValueError("FuturesProductSpec requires non-empty 'product_id'")

        # TypedDict is total=False, so we need to trust the caller for required keys.
        # This is intended for controlled/test usage.
        product = FuturesProduct(**cast(dict[str, Any], spec))  # safe boundary
        return self.intern(product)

    def initialise_from_csv(self, csv_file_path: str) -> list[FuturesProduct]:
        """Load products from CSV and intern them into this factory cache."""
        products = parse_futures_products_csv(csv_file_path)
        return [self.intern(product) for product in products]

    @classmethod
    def from_config_data(
        cls,
        config: RefDataConfigData,
    ) -> FuturesProductFactory:
        factory = cls()
        factory.initialise_from_csv(config["REFDATA_FUTURES_PRODUCTS_CSV_PATH"])
        return factory
