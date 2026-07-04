"""Unit tests for FuturesProductFactory."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from mxm.config import MXMConfig
from mxm.refdata.factories import (
    FuturesProductFactory,
    FuturesProductSpec,
)
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
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
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="End of Month",
        trading_calendar="Default Calendar",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="FGHJKMNQUVXZ",
    )


def test_new_factory_starts_empty() -> None:
    """A new factory should start with an empty product cache."""
    factory = FuturesProductFactory()

    assert factory.all() == []
    assert factory.get("TEST") is None


def test_intern_stores_and_returns_product() -> None:
    """intern should store and return the supplied product."""
    factory = FuturesProductFactory()
    product = _make_product()

    result = factory.intern(product)

    assert result is product
    assert factory.get(product.product_id) is product
    assert factory.all() == [product]


def test_intern_returns_existing_product_for_same_product_id() -> None:
    """intern should preserve the first product instance for a product_id."""
    factory = FuturesProductFactory()
    original = _make_product("TEST")
    duplicate = _make_product("TEST")

    result = factory.intern(original)
    duplicate_result = factory.intern(duplicate)

    assert result is original
    assert duplicate_result is original
    assert factory.get("TEST") is original
    assert factory.all() == [original]


def test_require_returns_product_when_present() -> None:
    """require should return a cached product when present."""
    factory = FuturesProductFactory()
    product = factory.intern(_make_product("TEST"))

    assert factory.require("TEST") is product


def test_require_raises_when_product_missing() -> None:
    """require should raise KeyError when product_id is not cached."""
    factory = FuturesProductFactory()

    with pytest.raises(KeyError, match="UNKNOWN"):
        factory.require("UNKNOWN")


def test_clear_empties_cache() -> None:
    """clear should remove all cached products."""
    factory = FuturesProductFactory()
    factory.intern(_make_product("TEST"))

    factory.clear()

    assert factory.all() == []
    assert factory.get("TEST") is None


def test_factory_instances_have_independent_caches() -> None:
    """Separate factory instances should not share product cache state."""
    factory_a = FuturesProductFactory()
    factory_b = FuturesProductFactory()
    product = _make_product("TEST")

    factory_a.intern(product)

    assert factory_a.get("TEST") is product
    assert factory_b.get("TEST") is None


def test_create_from_spec_creates_and_interns_product() -> None:
    """create_from_spec should create and intern a product."""
    factory = FuturesProductFactory()
    spec: FuturesProductSpec = {
        "product_id": "TEST",
        "venue": "CME",
        "description": "Test Product",
        "unit": ProductUnit.TROY_OUNCE,
        "currency": Currency.USD,
        "contract_size": 100.0,
        "listing_rule": "Monthly",
        "period_types": (PeriodType.MONTH,),
        "settlement": SettlementMethod.PHYSICAL,
        "last_trading_rule": "3rd last business day of the delivery month",
        "expiry_rule": "End of Month",
        "trading_calendar": "Default Calendar",
        "tick_size": 0.1,
        "tick_value": 10.0,
        "valid_period_rule": "FGHJKMNQUVXZ",
    }

    product = factory.create_from_spec(spec)

    assert product.product_id == "TEST"
    assert factory.get("TEST") is product


def test_create_from_spec_rejects_missing_product_id() -> None:
    """create_from_spec should reject specs without product_id."""
    factory = FuturesProductFactory()
    spec: FuturesProductSpec = {}

    with pytest.raises(ValueError, match="product_id"):
        factory.create_from_spec(spec)


def test_initialise_uses_instance_cache(monkeypatch: MonkeyPatch) -> None:
    """initialise should populate only the receiving factory instance."""

    product = _make_product("TEST")

    def fake_build_futures_products(_: Path, source: str) -> list[FuturesProduct]:
        assert source == "csv"
        return [product]

    monkeypatch.setattr(
        "mxm.refdata.factories.futures_product_factory.build_futures_products",
        fake_build_futures_products,
    )

    factory_a = FuturesProductFactory()
    factory_b = FuturesProductFactory()

    result = factory_a.initialise_from_csv("/tmp/products.csv")

    assert result == [product]
    assert factory_a.get("TEST") is product
    assert factory_b.get("TEST") is None


def test_from_config_data_initialises_factory_from_configured_source(
    monkeypatch: MonkeyPatch,
) -> None:
    """from_config_data should create a factory initialised from configured source."""

    product = _make_product("TEST")

    def fake_build_futures_products(path: Path, source: str) -> list[FuturesProduct]:
        assert str(path) == "/tmp/products"
        assert source == "json"
        return [product]

    monkeypatch.setattr(
        "mxm.refdata.factories.futures_product_factory.build_futures_products",
        fake_build_futures_products,
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
    assert factory.require("TEST") is product
