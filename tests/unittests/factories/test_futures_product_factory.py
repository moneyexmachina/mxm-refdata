"""Unit tests for FuturesProductFactory."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from mxm.config import MXMConfig
from mxm.refdata.factories import FuturesProductFactory
from mxm.refdata.factories.futures_product_factory import (
    FuturesProductCreateParams,
)
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.products.futures_product_spec import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProductProvenance,
    FuturesProductSourceStatus,
    FuturesProductSpec,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit


def _make_product(product_id: str = "TEST") -> FuturesProduct:
    return FuturesProduct(
        product_id=product_id,
        venue="CME",
        description=f"{product_id} Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100.0,
        listing_rule="Monthly",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=("3rd last business day of the delivery month"),
        expiry_rule="End of Month",
        trading_calendar="Default Calendar",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="FGHJKMNQUVXZ",
    )


def _make_contract_rules() -> ContractRules:
    return ContractRules(
        last_trading_rule=LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
            n_reference=-3,
            business_day_offset=0,
        ),
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift={
                    "Jan": 24,
                    "Feb": 24,
                    "Mar": 24,
                    "Apr": 24,
                    "May": 24,
                    "Jun": 24,
                    "Jul": 24,
                    "Aug": 24,
                    "Sep": 24,
                    "Oct": 24,
                    "Nov": 24,
                    "Dec": 24,
                },
            ),
            reference_rule="next_b_day_after_period",
        ),
    )


def _make_spec(
    product_id: str = "TEST",
    *,
    product: FuturesProduct | None = None,
) -> FuturesProductSpec:
    product_obj = product or _make_product(product_id)

    return FuturesProductSpec(
        schema_version="futures_product.v1",
        product_id=product_id,
        asset_class="futures",
        source_status=FuturesProductSourceStatus(
            created_at=date(2026, 7, 13),
            updated_at=date(2026, 7, 13),
            review_status="draft",
            curator="mxm",
        ),
        provenance=FuturesProductProvenance(
            source_type="manual_curation",
            source_url="https://example.com/product",
            source_accessed_at=date(2026, 7, 13),
            curation_method="human_interpreted",
            assistance="llm_assisted_drafting",
            notes=(),
        ),
        product=product_obj,
        contract_rules=_make_contract_rules(),
    )


# ---------------------------------------------------------------------
# EMPTY FACTORY
# ---------------------------------------------------------------------


def test_new_factory_starts_empty() -> None:
    factory = FuturesProductFactory()

    assert factory.all() == []
    assert factory.all_specs() == []
    assert factory.get("TEST") is None
    assert factory.get_spec("TEST") is None


# ---------------------------------------------------------------------
# PRODUCT INTERNING
# ---------------------------------------------------------------------


def test_intern_stores_and_returns_product() -> None:
    factory = FuturesProductFactory()
    product = _make_product()

    result = factory.intern(product)

    assert result is product
    assert factory.get(product.product_id) is product
    assert factory.all() == [product]


def test_intern_returns_existing_equal_product() -> None:
    factory = FuturesProductFactory()
    original = _make_product("TEST")
    duplicate = _make_product("TEST")

    result = factory.intern(original)
    duplicate_result = factory.intern(duplicate)

    assert result is original
    assert duplicate_result is original
    assert factory.get("TEST") is original
    assert factory.all() == [original]


def test_intern_rejects_conflicting_product_definition() -> None:
    factory = FuturesProductFactory()
    original = _make_product("TEST")
    conflicting = replace(
        original,
        description="Different Product",
    )

    factory.intern(original)

    with pytest.raises(
        ValueError,
        match="Conflicting FuturesProduct definitions",
    ):
        factory.intern(conflicting)


def test_require_returns_product_when_present() -> None:
    factory = FuturesProductFactory()
    product = factory.intern(_make_product("TEST"))

    assert factory.require("TEST") is product


def test_require_raises_when_product_missing() -> None:
    factory = FuturesProductFactory()

    with pytest.raises(KeyError, match="UNKNOWN"):
        factory.require("UNKNOWN")


# ---------------------------------------------------------------------
# SPECIFICATION INTERNING
# ---------------------------------------------------------------------


def test_intern_spec_stores_spec_and_product() -> None:
    factory = FuturesProductFactory()
    spec = _make_spec("TEST")

    result = factory.intern_spec(spec)

    assert result is spec
    assert factory.get_spec("TEST") is spec
    assert factory.get("TEST") is spec.product
    assert factory.all_specs() == [spec]
    assert factory.all() == [spec.product]


def test_intern_spec_returns_existing_equal_spec() -> None:
    factory = FuturesProductFactory()
    original = _make_spec("TEST")
    duplicate = _make_spec("TEST")

    first_result = factory.intern_spec(original)
    duplicate_result = factory.intern_spec(duplicate)

    assert first_result is original
    assert duplicate_result is original
    assert factory.all_specs() == [original]


def test_intern_spec_reuses_canonical_product_instance() -> None:
    factory = FuturesProductFactory()

    canonical_product = _make_product("TEST")
    equal_product = _make_product("TEST")
    spec = _make_spec(
        "TEST",
        product=equal_product,
    )

    factory.intern(canonical_product)
    canonical_spec = factory.intern_spec(spec)

    assert canonical_spec.product is canonical_product
    assert factory.require("TEST") is canonical_product
    assert factory.require_spec("TEST") is canonical_spec


def test_intern_spec_rejects_conflicting_specification() -> None:
    factory = FuturesProductFactory()
    original = _make_spec("TEST")
    conflicting = replace(
        original,
        schema_version="futures_product.v2",
    )

    factory.intern_spec(original)

    with pytest.raises(
        ValueError,
        match="Conflicting FuturesProductSpec definitions",
    ):
        factory.intern_spec(conflicting)


def test_require_spec_returns_spec_when_present() -> None:
    factory = FuturesProductFactory()
    spec = factory.intern_spec(_make_spec("TEST"))

    assert factory.require_spec("TEST") is spec


def test_require_spec_raises_when_spec_missing() -> None:
    factory = FuturesProductFactory()

    with pytest.raises(KeyError, match="UNKNOWN"):
        factory.require_spec("UNKNOWN")


# ---------------------------------------------------------------------
# SPECIFICATION PROJECTIONS
# ---------------------------------------------------------------------


def test_get_contract_rules_returns_rules() -> None:
    factory = FuturesProductFactory()
    spec = factory.intern_spec(_make_spec("TEST"))

    assert factory.get_contract_rules("TEST") is spec.contract_rules


def test_get_provenance_returns_provenance() -> None:
    factory = FuturesProductFactory()
    spec = factory.intern_spec(_make_spec("TEST"))

    assert factory.get_provenance("TEST") is spec.provenance


def test_get_source_status_returns_source_status() -> None:
    factory = FuturesProductFactory()
    spec = factory.intern_spec(_make_spec("TEST"))

    assert factory.get_source_status("TEST") is spec.source_status


def test_spec_projection_raises_for_product_without_spec() -> None:
    factory = FuturesProductFactory()
    factory.intern(_make_product("TEST"))

    with pytest.raises(KeyError, match="TEST"):
        factory.get_contract_rules("TEST")


# ---------------------------------------------------------------------
# CACHE LIFECYCLE
# ---------------------------------------------------------------------


def test_clear_empties_product_and_spec_caches() -> None:
    factory = FuturesProductFactory()
    factory.intern_spec(_make_spec("TEST"))

    factory.clear()

    assert factory.all() == []
    assert factory.all_specs() == []
    assert factory.get("TEST") is None
    assert factory.get_spec("TEST") is None


def test_factory_instances_have_independent_caches() -> None:
    factory_a = FuturesProductFactory()
    factory_b = FuturesProductFactory()
    spec = _make_spec("TEST")

    factory_a.intern_spec(spec)

    assert factory_a.get("TEST") is spec.product
    assert factory_a.get_spec("TEST") is spec
    assert factory_b.get("TEST") is None
    assert factory_b.get_spec("TEST") is None


# ---------------------------------------------------------------------
# CONTROLLED PRODUCT CONSTRUCTION
# ---------------------------------------------------------------------


def test_create_from_params_creates_and_interns_product() -> None:
    factory = FuturesProductFactory()

    params: FuturesProductCreateParams = {
        "product_id": "TEST",
        "venue": "CME",
        "description": "Test Product",
        "unit": ProductUnit.TROY_OUNCE,
        "currency": Currency.USD,
        "contract_size": 100.0,
        "listing_rule": "Monthly",
        "period_types": (PeriodType.MONTH,),
        "settlement": SettlementMethod.PHYSICAL,
        "last_trading_rule": ("3rd last business day of the delivery month"),
        "expiry_rule": "End of Month",
        "trading_calendar": "Default Calendar",
        "tick_size": 0.1,
        "tick_value": 10.0,
        "valid_period_rule": "FGHJKMNQUVXZ",
    }

    product = factory.create_from_params(params)

    assert product.product_id == "TEST"
    assert factory.get("TEST") is product
    assert factory.get_spec("TEST") is None


def test_create_from_params_rejects_missing_product_id() -> None:
    factory = FuturesProductFactory()
    params: FuturesProductCreateParams = {}

    with pytest.raises(ValueError, match="product_id"):
        factory.create_from_params(params)


# ---------------------------------------------------------------------
# INITIALISATION
# ---------------------------------------------------------------------


def test_initialise_parses_and_interns_specs(
    monkeypatch: MonkeyPatch,
) -> None:
    spec = _make_spec("TEST")

    def fake_parse_futures_product_specs(
        root_dir: Path,
    ) -> list[FuturesProductSpec]:
        assert root_dir == Path("/tmp/products")
        return [spec]

    monkeypatch.setattr(
        ("mxm.refdata.factories.futures_product_factory.parse_futures_product_specs"),
        fake_parse_futures_product_specs,
    )

    factory_a = FuturesProductFactory()
    factory_b = FuturesProductFactory()

    result = factory_a.initialise("/tmp/products")

    assert result == [spec.product]
    assert result[0] is spec.product
    assert factory_a.require("TEST") is spec.product
    assert factory_a.require_spec("TEST") is spec
    assert factory_b.get("TEST") is None
    assert factory_b.get_spec("TEST") is None


def test_initialise_returns_canonical_products(
    monkeypatch: MonkeyPatch,
) -> None:
    canonical_product = _make_product("TEST")
    equal_product = _make_product("TEST")
    spec = _make_spec(
        "TEST",
        product=equal_product,
    )

    def fake_parse_futures_product_specs(
        _: Path,
    ) -> list[FuturesProductSpec]:
        return [spec]

    monkeypatch.setattr(
        ("mxm.refdata.factories.futures_product_factory.parse_futures_product_specs"),
        fake_parse_futures_product_specs,
    )

    factory = FuturesProductFactory()
    factory.intern(canonical_product)

    result = factory.initialise("/tmp/products")

    assert result == [canonical_product]
    assert result[0] is canonical_product
    assert factory.require_spec("TEST").product is canonical_product


def test_from_config_initialises_factory_from_configured_root(
    monkeypatch: MonkeyPatch,
) -> None:
    spec = _make_spec("TEST")

    def fake_parse_futures_product_specs(
        root_dir: Path,
    ) -> list[FuturesProductSpec]:
        assert root_dir == Path("/tmp/products")
        return [spec]

    monkeypatch.setattr(
        ("mxm.refdata.factories.futures_product_factory.parse_futures_product_specs"),
        fake_parse_futures_product_specs,
    )

    config: MXMConfig = cast(
        MXMConfig,
        {
            "SQL_DB_URL": "sqlite:///:memory:",
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
            "REFDATA_CONTRACT_START_DATE": "1980-01-01",
            "REFDATA_CONTRACT_END_DATE": "2046-12-31",
        },
    )

    factory = FuturesProductFactory.from_config(config)

    assert isinstance(factory, FuturesProductFactory)
    assert factory.require("TEST") is spec.product
    assert factory.require_spec("TEST") is spec
