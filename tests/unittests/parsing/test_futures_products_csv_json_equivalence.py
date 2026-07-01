from __future__ import annotations

import json
from pathlib import Path

import pytest

from mxm.refdata.parsing.futures_product import build_futures_products

# ---------------------------------------------------------------------
# FIXTURE: CSV
# ---------------------------------------------------------------------


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value,initial_margin,maintenance_margin
comex_gold_futures,COMEX,Gold Futures,USD,TROY_OUNCE,100.0,FGHJKMNQUVXZ,rule,MONTH,PHYSICAL,rule,rule,CME DEFAULT,hours,0.1,10.0,5000,4000
cbot_corn_futures,CBOT,Corn Futures,USD,BUSHEL,5000.0,FGHJKMNQUVXZ,rule,MONTH,PHYSICAL,rule,rule,CME DEFAULT,hours,0.0025,12.5,1000,800
ice_brent_futures,ICE,Brent Futures,USD,BARREL,1000.0,FGHJKMNQUVXZ,rule,MONTH,PHYSICAL,rule,rule,ICE DEFAULT,hours,0.01,1.0,2000,1500
"""
    file_path = tmp_path / "futures.csv"
    file_path.write_text(csv_content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------
# FIXTURE: JSON DIRECTORY (3 products)
# ---------------------------------------------------------------------


@pytest.fixture
def sample_json_dir(tmp_path: Path) -> Path:
    root = tmp_path / "json_products"
    root.mkdir()

    products = [
        {
            "product": {
                "product_id": "comex_gold_futures",
                "venue": "COMEX",
                "description": "Gold Futures",
                "currency": "USD",
                "unit": "TROY_OUNCE",
                "contract_size": 100.0,
                "valid_period_rule": "FGHJKMNQUVXZ",
                "listing_rule": "rule",
                "period_types": "MONTH",
                "settlement": "PHYSICAL",
                "last_trading_rule": "rule",
                "expiry_rule": "rule",
                "trading_calendar": "CME DEFAULT",
                "trading_hours": "hours",
                "tick_size": 0.1,
                "tick_value": 10.0,
                "initial_margin": 5000.0,
                "maintenance_margin": 4000.0,
            }
        },
        {
            "product": {
                "product_id": "cbot_corn_futures",
                "venue": "CBOT",
                "description": "Corn Futures",
                "currency": "USD",
                "unit": "BUSHEL",
                "contract_size": 5000.0,
                "valid_period_rule": "FGHJKMNQUVXZ",
                "listing_rule": "rule",
                "period_types": "MONTH",
                "settlement": "PHYSICAL",
                "last_trading_rule": "rule",
                "expiry_rule": "rule",
                "trading_calendar": "CME DEFAULT",
                "trading_hours": "hours",
                "tick_size": 0.0025,
                "tick_value": 12.5,
                "initial_margin": 1000.0,
                "maintenance_margin": 800.0,
            }
        },
        {
            "product": {
                "product_id": "ice_brent_futures",
                "venue": "ICE",
                "description": "Brent Futures",
                "currency": "USD",
                "unit": "BARREL",
                "contract_size": 1000.0,
                "valid_period_rule": "FGHJKMNQUVXZ",
                "listing_rule": "rule",
                "period_types": "MONTH",
                "settlement": "PHYSICAL",
                "last_trading_rule": "rule",
                "expiry_rule": "rule",
                "trading_calendar": "ICE DEFAULT",
                "trading_hours": "hours",
                "tick_size": 0.01,
                "tick_value": 1.0,
                "initial_margin": 2000.0,
                "maintenance_margin": 1500.0,
            }
        },
    ]

    for p in products:
        pid = p["product"]["product_id"]
        file_path = root / f"{pid}.json"
        file_path.write_text(json.dumps(p), encoding="utf-8")

    return root


# ---------------------------------------------------------------------
# TEST: CROSS-SOURCE EQUIVALENCE
# ---------------------------------------------------------------------


def test_csv_vs_json_equivalence(sample_csv: Path, sample_json_dir: Path) -> None:
    """Ensure CSV and JSON pipelines produce identical FuturesProduct outputs."""

    csv_products = build_futures_products(sample_csv, source="csv")
    json_products = build_futures_products(sample_json_dir, source="json")

    # -------------------------------------------------------------
    # Basic structural checks
    # -------------------------------------------------------------
    assert len(csv_products) == len(json_products)

    csv_by_id = {p.product_id: p for p in csv_products}
    json_by_id = {p.product_id: p for p in json_products}

    assert set(csv_by_id.keys()) == set(json_by_id.keys())

    # -------------------------------------------------------------
    # Deep equality check
    # -------------------------------------------------------------
    for product_id in csv_by_id:
        assert csv_by_id[product_id] == json_by_id[product_id]
