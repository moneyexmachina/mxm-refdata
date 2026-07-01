from __future__ import annotations

from pathlib import Path

import pytest

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.parsing.futures_product import (
    FuturesProductDict,
    build_futures_products,
    futures_product_from_dict,
    parse_futures_products_json,
)

# ---------------------------------------------------------------------
# FIXTURE: JSON directory structure
# ---------------------------------------------------------------------


@pytest.fixture
def sample_json_dir(tmp_path: Path) -> Path:
    """Create a temporary JSON directory with 2 product files."""

    root = tmp_path / "json_products"
    root.mkdir()

    comex_dir = root / "comex"
    cbot_dir = root / "cbot"

    comex_dir.mkdir()
    cbot_dir.mkdir()

    (comex_dir / "gold.json").write_text(
        """{
  "product": {
    "product_id": "comex_gold_futures",
    "venue": "COMEX",
    "description": "Gold Futures",
    "currency": "USD",
    "unit": "TROY_OUNCE",
    "contract_size": 100.0,
    "valid_period_rule": "FGHJKMNQUVXZ",
    "listing_rule": "Monthly contracts listed for 3 consecutive months",
    "period_types": "MONTH",
    "settlement": "PHYSICAL",
    "last_trading_rule": "3rd last business day of delivery month",
    "expiry_rule": "3rd last business day of delivery month",
    "trading_calendar": "CME DEFAULT",
    "trading_hours": "Sunday - Friday 6:00 p.m. - 5:00 p.m.",
    "tick_size": 0.1,
    "tick_value": 10.0,
    "initial_margin": 5000.0,
    "maintenance_margin": 4000.0
  }
}
""",
        encoding="utf-8",
    )

    (cbot_dir / "corn.json").write_text(
        """{
  "product": {
    "product_id": "cbot_corn_futures",
    "venue": "CBOT",
    "description": "Corn Futures",
    "currency": "USD",
    "unit": "BUSHEL",
    "contract_size": 5000.0,
    "valid_period_rule": "FGHJKMNQUVXZ",
    "listing_rule": "9 monthly contracts listed",
    "period_types": "MONTH",
    "settlement": "PHYSICAL",
    "last_trading_rule": "15th day prior to contract month",
    "expiry_rule": "15th day prior to contract month",
    "trading_calendar": "CME DEFAULT",
    "trading_hours": "Sunday - Friday 7:00 p.m. - 7:45 a.m.",
    "tick_size": 0.0025,
    "tick_value": 12.5,
    "initial_margin": 1000.0,
    "maintenance_margin": 800.0
  }
}
""",
        encoding="utf-8",
    )

    return root


# ---------------------------------------------------------------------
# LAYER 1: JSON → DICTS
# ---------------------------------------------------------------------


def test_parse_futures_products_json(sample_json_dir: Path) -> None:
    """Test JSON directory parsing produces correct dict count."""

    data = parse_futures_products_json(sample_json_dir)

    assert len(data) == 2

    gold = next(p for p in data if p["product_id"] == "comex_gold_futures")
    assert gold["venue"] == "COMEX"
    assert gold["currency"] == "USD"
    assert gold["unit"] == "TROY_OUNCE"


# ---------------------------------------------------------------------
# LAYER 2: DICT → DOMAIN
# ---------------------------------------------------------------------


def test_futures_product_from_dict_json() -> None:
    """Test dict → domain conversion (JSON style input)."""

    input_dict: FuturesProductDict = {
        "product_id": "test_product",
        "venue": "TEST",
        "description": "Test Product",
        "currency": "USD",
        "unit": "BUSHEL",
        "contract_size": 100.0,
        "valid_period_rule": "RULE",
        "listing_rule": "RULE",
        "period_types": "MONTH",
        "settlement": "PHYSICAL",
        "last_trading_rule": "RULE",
        "expiry_rule": "RULE",
        "trading_calendar": "CME DEFAULT",
        "trading_hours": "hours",
        "tick_size": 0.1,
        "tick_value": 10.0,
        "initial_margin": 500,
        "maintenance_margin": 400,
    }

    product = futures_product_from_dict(input_dict)

    assert isinstance(product, FuturesProduct)
    assert product.product_id == "test_product"
    assert product.currency == Currency.USD
    assert product.unit == ProductUnit.BUSHEL
    assert product.contract_size == 100.0
    assert product.settlement == SettlementMethod.PHYSICAL


# ---------------------------------------------------------------------
# LAYER 3: END-TO-END JSON PIPELINE
# ---------------------------------------------------------------------


def test_build_futures_products_json(sample_json_dir: Path) -> None:
    """End-to-end JSON → FuturesProduct pipeline test."""

    products = build_futures_products(sample_json_dir, source="json")

    # -----------------------------------------------------------------
    # Basic structural assertions
    # -----------------------------------------------------------------
    assert len(products) == 2
    assert all(isinstance(p, FuturesProduct) for p in products)

    # -----------------------------------------------------------------
    # Lookup for deterministic validation
    # -----------------------------------------------------------------
    by_id = {p.product_id: p for p in products}

    gold = by_id["comex_gold_futures"]
    corn = by_id["cbot_corn_futures"]

    # -----------------------------------------------------------------
    # COMEX GOLD
    # -----------------------------------------------------------------
    assert gold.venue == "COMEX"
    assert gold.description == "Gold Futures"
    assert gold.currency == Currency.USD
    assert gold.unit == ProductUnit.TROY_OUNCE
    assert gold.contract_size == 100.0
    assert gold.valid_period_rule == "FGHJKMNQUVXZ"
    assert gold.listing_rule == "Monthly contracts listed for 3 consecutive months"
    assert gold.trading_calendar == "CME DEFAULT"
    assert gold.trading_hours == "Sunday - Friday 6:00 p.m. - 5:00 p.m."
    assert gold.tick_size == 0.1
    assert gold.tick_value == 10.0
    assert gold.initial_margin == 5000.0
    assert gold.maintenance_margin == 4000.0

    # -----------------------------------------------------------------
    # CBOT CORN
    # -----------------------------------------------------------------
    assert corn.venue == "CBOT"
    assert corn.description == "Corn Futures"
    assert corn.currency == Currency.USD
    assert corn.unit == ProductUnit.BUSHEL
    assert corn.contract_size == 5000.0
    assert corn.valid_period_rule == "FGHJKMNQUVXZ"
    assert corn.listing_rule == "9 monthly contracts listed"
    assert corn.trading_calendar == "CME DEFAULT"
    assert corn.trading_hours == "Sunday - Friday 7:00 p.m. - 7:45 a.m."
    assert corn.tick_size == 0.0025
    assert corn.tick_value == 12.5
    assert corn.initial_margin == 1000.0
    assert corn.maintenance_margin == 800.0
