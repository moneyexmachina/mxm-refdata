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
    build_futures_products,
    futures_product_from_dict,
    parse_futures_products_csv,
)

# ---------------------------------------------------------------------
# FIXTURE
# ---------------------------------------------------------------------


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a temporary CSV file for testing new parsing module."""
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value,initial_margin,maintenance_margin
comex_gold_futures,COMEX,Gold Futures,USD,TROY_OUNCE,100.0,"FGHJKMNQUVXZ","Monthly contracts listed for 3 consecutive months",MONTH,PHYSICAL,"3rd last business day of delivery month","3rd last business day of delivery month",CME DEFAULT,"Sunday - Friday 6:00 p.m. - 5:00 p.m.",0.1,10.0,5000,4000
cbot_corn_futures,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","9 monthly contracts listed",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"Sunday - Friday 7:00 p.m. - 7:45 a.m.",0.0025,12.5,1000,800
"""
    file_path = tmp_path / "futures_products.csv"
    file_path.write_text(csv_content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------
# LAYER 1: CSV → DICTS (implicit via function output)
# ---------------------------------------------------------------------


def test_parse_futures_products_csv(sample_csv: Path) -> None:
    """Test CSV parsing produces correct number of dicts."""
    data = parse_futures_products_csv(sample_csv)

    assert len(data) == 2

    gold = data[0]
    assert gold["product_id"] == "comex_gold_futures"
    assert gold["venue"] == "COMEX"
    assert gold["currency"] == "USD"
    assert gold["unit"] == "TROY_OUNCE"
    assert gold["contract_size"] == "100.0"


# ---------------------------------------------------------------------
# LAYER 2: DICT → DOMAIN
# ---------------------------------------------------------------------


def test_futures_product_from_dict() -> None:
    """Test conversion from FuturesProductDict to FuturesProduct."""

    input_dict = {
        "product_id": "test_product",
        "venue": "TEST",
        "description": "Test Product",
        "currency": "USD",
        "unit": "BUSHEL",
        "contract_size": "100.0",
        "valid_period_rule": "RULE",
        "listing_rule": "RULE",
        "period_types": "MONTH",
        "settlement": "PHYSICAL",
        "last_trading_rule": "RULE",
        "expiry_rule": "RULE",
        "trading_calendar": "CME DEFAULT",
        "trading_hours": "hours",
        "tick_size": "0.1",
        "tick_value": "10.0",
        "initial_margin": "500",
        "maintenance_margin": "400",
    }

    product = futures_product_from_dict(input_dict)  # type: ignore[arg-type]

    assert isinstance(product, FuturesProduct)
    assert product.product_id == "test_product"
    assert product.currency == Currency.USD
    assert product.unit == ProductUnit.BUSHEL
    assert product.contract_size == 100.0
    assert product.settlement == SettlementMethod.PHYSICAL


# ---------------------------------------------------------------------
# LAYER 3: END-TO-END CSV PIPELINE
# ---------------------------------------------------------------------


def test_build_futures_products_csv(sample_csv: Path) -> None:
    """Test full CSV → FuturesProduct pipeline."""

    products = build_futures_products(sample_csv, source="csv")

    assert len(products) == 2

    gold = products[0]
    assert isinstance(gold, FuturesProduct)
    assert gold.product_id == "comex_gold_futures"
    assert gold.currency == Currency.USD
    assert gold.tick_size == 0.1
    assert gold.initial_margin == 5000.0
