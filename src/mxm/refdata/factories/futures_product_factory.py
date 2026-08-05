"""Factory and interning cache for futures product specifications.

Semantics
---------
- At most one canonical FuturesProduct instance exists per product_id.
- At most one canonical FuturesProductSpec instance exists per product_id.
- JSON initialisation loads complete FuturesProductSpec objects.
- A cached FuturesProductSpec always references the canonical cached
  FuturesProduct instance.
- Conflicting products or specifications with the same product_id are rejected.
- Controlled programmatic construction of standalone FuturesProduct instances
  remains available primarily for tests and fixtures.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, TypedDict, cast

from mxm.config import MXMConfig
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.products.futures_product_spec import (
    ContractRules,
    FuturesProductProvenance,
    FuturesProductSourceStatus,
    FuturesProductSpec,
)
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.parsing.futures_product import (
    LoadedFuturesProductSpec,
    load_futures_product_specs,
)


class FuturesProductCreateParams(TypedDict, total=False):
    """Typed constructor parameters for controlled product creation.

    This payload is intended primarily for tests, fixtures, and controlled
    programmatic construction.

    It is not the persisted product-specification format.

    ``period_types`` must already be in its canonical domain representation.
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
    """Factory and interning cache for futures products and specifications."""

    def __init__(self) -> None:
        """Initialise empty product and specification caches."""

        self._products: dict[str, FuturesProduct] = {}
        self._specs: dict[str, FuturesProductSpec] = {}
        self._loaded_specs: dict[str, LoadedFuturesProductSpec] = {}

    # -----------------------------------------------------------------
    # Product cache
    # -----------------------------------------------------------------

    def intern(self, product: FuturesProduct) -> FuturesProduct:
        """Return the canonical product instance for ``product.product_id``.

        A second equal product resolves to the existing canonical instance.

        A structurally different product with the same product_id is rejected,
        because silently accepting it would make the resulting object graph
        depend on insertion order.
        """

        cached = self._products.get(product.product_id)

        if cached is None:
            self._products[product.product_id] = product
            return product

        if cached != product:
            raise ValueError(
                "Conflicting FuturesProduct definitions for product_id "
                f"{product.product_id!r}"
            )

        return cached

    def get(self, product_id: str) -> FuturesProduct | None:
        """Return a cached product, or ``None`` if it is unknown."""

        return self._products.get(product_id)

    def require(self, product_id: str) -> FuturesProduct:
        """Return a cached product or raise ``KeyError``."""

        product = self.get(product_id)

        if product is None:
            raise KeyError(f"Unknown product_id: {product_id!r}")

        return product

    def all(self) -> list[FuturesProduct]:
        """Return all cached products in insertion order."""

        return list(self._products.values())

    # -----------------------------------------------------------------
    # Specification cache
    # -----------------------------------------------------------------

    def intern_spec(
        self,
        spec: FuturesProductSpec,
    ) -> FuturesProductSpec:
        """Intern a complete product specification.

        The nested product is interned first. If an equal but non-identical
        product instance was already cached, the stored specification is
        rebuilt to reference the canonical product instance.
        """

        canonical_product = self.intern(spec.product)

        canonical_spec = (
            spec
            if spec.product is canonical_product
            else replace(
                spec,
                product=canonical_product,
            )
        )

        cached = self._specs.get(spec.product_id)

        if cached is None:
            self._specs[spec.product_id] = canonical_spec
            return canonical_spec

        if cached != canonical_spec:
            raise ValueError(
                "Conflicting FuturesProductSpec definitions for product_id "
                f"{spec.product_id!r}"
            )

        return cached

    def intern_loaded_spec(
        self,
        loaded_spec: LoadedFuturesProductSpec,
    ) -> LoadedFuturesProductSpec:
        """Intern a loaded specification together with its source identity.

        The nested FuturesProductSpec is interned first. If canonicalisation
        replaces the specification instance, the loaded specification is rebuilt
        to reference that canonical instance.

        Repeated equal loaded specifications resolve to the existing cached
        instance. Conflicting source artefacts for the same product_id are
        rejected.
        """

        canonical_spec = self.intern_spec(
            loaded_spec.specification,
        )

        canonical_loaded_spec = (
            loaded_spec
            if loaded_spec.specification is canonical_spec
            else replace(
                loaded_spec,
                specification=canonical_spec,
            )
        )

        product_id = canonical_spec.product_id
        cached = self._loaded_specs.get(product_id)

        if cached is None:
            self._loaded_specs[product_id] = canonical_loaded_spec
            return canonical_loaded_spec

        if cached != canonical_loaded_spec:
            raise ValueError(
                "Conflicting LoadedFuturesProductSpec definitions for "
                f"product_id {product_id!r}"
            )

        return cached

    def get_spec(
        self,
        product_id: str,
    ) -> FuturesProductSpec | None:
        """Return a cached complete specification, if available."""

        return self._specs.get(product_id)

    def require_spec(
        self,
        product_id: str,
    ) -> FuturesProductSpec:
        """Return a cached complete specification or raise ``KeyError``."""

        spec = self.get_spec(product_id)

        if spec is None:
            raise KeyError(
                f"Unknown futures product specification for product_id: {product_id!r}"
            )

        return spec

    def all_specs(self) -> list[FuturesProductSpec]:
        """Return all cached specifications in insertion order."""

        return list(self._specs.values())

    def get_loaded_spec(
        self,
        product_id: str,
    ) -> LoadedFuturesProductSpec | None:
        """Return a cached loaded specification, if available."""

        return self._loaded_specs.get(product_id)

    def require_loaded_spec(
        self,
        product_id: str,
    ) -> LoadedFuturesProductSpec:
        """Return a cached loaded specification or raise ``KeyError``."""

        loaded_spec = self.get_loaded_spec(product_id)

        if loaded_spec is None:
            raise KeyError(
                "Unknown loaded futures product specification for "
                f"product_id: {product_id!r}"
            )

        return loaded_spec

    def all_loaded_specs(self) -> list[LoadedFuturesProductSpec]:
        """Return all cached loaded specifications in insertion order."""

        return list(self._loaded_specs.values())

    # -----------------------------------------------------------------
    # Specification projections
    # -----------------------------------------------------------------

    def get_contract_rules(
        self,
        product_id: str,
    ) -> ContractRules:
        """Return the contract-construction rules for a product."""

        return self.require_spec(product_id).contract_rules

    def get_provenance(
        self,
        product_id: str,
    ) -> FuturesProductProvenance:
        """Return the provenance associated with a product specification."""

        return self.require_spec(product_id).provenance

    def get_source_status(
        self,
        product_id: str,
    ) -> FuturesProductSourceStatus:
        """Return the source lifecycle status for a product specification."""

        return self.require_spec(product_id).source_status

    # -----------------------------------------------------------------
    # Controlled programmatic construction
    # -----------------------------------------------------------------

    def create_from_params(
        self,
        params: FuturesProductCreateParams,
    ) -> FuturesProduct:
        """Construct and intern a standalone FuturesProduct.

        This path is intended primarily for tests, fixtures, and controlled
        programmatic creation. It does not create a FuturesProductSpec, so
        specification-dependent accessors such as ``get_contract_rules`` will
        remain unavailable for the resulting product.
        """

        product_id = params.get("product_id")

        if not product_id:
            raise ValueError(
                "FuturesProductCreateParams requires a non-empty 'product_id'"
            )

        product = FuturesProduct(
            **cast(dict[str, Any], params),
        )

        return self.intern(product)

    # -----------------------------------------------------------------
    # Initialisation
    # -----------------------------------------------------------------
    def initialise(
        self,
        root_dir: str,
    ) -> list[FuturesProduct]:
        """Load and intern specifications from a JSON directory."""

        loaded_specs = load_futures_product_specs(
            Path(root_dir).expanduser(),
        )

        canonical_loaded_specs = [
            self.intern_loaded_spec(loaded_spec) for loaded_spec in loaded_specs
        ]

        return [
            loaded_spec.specification.product for loaded_spec in canonical_loaded_specs
        ]

    @classmethod
    def from_config(
        cls,
        config: MXMConfig,
    ) -> FuturesProductFactory:
        """Construct and initialise a factory from MXM configuration."""

        factory = cls()

        factory.initialise(
            config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"],
        )

        return factory

    # -----------------------------------------------------------------
    # Cache lifecycle
    # -----------------------------------------------------------------

    def clear(self) -> None:
        """Clear all cached products and specifications."""

        self._products.clear()
        self._specs.clear()
        self._loaded_specs.clear()
