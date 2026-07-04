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

from pathlib import Path
from typing import Any, TypedDict, cast

from mxm.config import MXMConfig
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.parsing.futures_product import (
    build_futures_products,
)


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

    def initialise(self, source: str, path: str) -> list[FuturesProduct]:
        return (
            self.initialise_from_json(path)
            if source == "json"
            else self.initialise_from_csv(path)
        )

    def initialise_from_csv(self, file_path: str) -> list[FuturesProduct]:
        """Legacy CSV loader (kept for compatibility)."""

        products = build_futures_products(Path(file_path), source="csv")

        return [self.intern(p) for p in products]

    def initialise_from_json(self, root_dir: str) -> list[FuturesProduct]:
        """Load products from JSON directory and intern them into cache."""

        products = build_futures_products(Path(root_dir).expanduser(), source="json")

        return [self.intern(p) for p in products]

    @classmethod
    def from_config(cls, config: MXMConfig) -> FuturesProductFactory:
        factory = cls()
        factory.initialise_from_json(config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"])
        return factory
