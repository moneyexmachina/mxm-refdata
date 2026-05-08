"""
Test suite for parsing futures_products.csv into FuturesProduct domain objects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.parsing.futures_products_from_csv import parse_futures_products_csv


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a temporary CSV file for testing."""
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value,initial_margin,maintenance_margin
comex_gold_futures,COMEX,Gold Futures,USD,TROY_OUNCE,100.0,"FGHJKMNQUVXZ","Monthly contracts listed for 3 consecutive months",MONTH,PHYSICAL,"3rd last business day of delivery month","3rd last business day of delivery month",CME DEFAULT,"Sunday - Friday 6:00 p.m. - 5:00 p.m.",0.1,10.0,5000,4000
cbot_corn_futures,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","9 monthly contracts listed",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"Sunday - Friday 7:00 p.m. - 7:45 a.m.",0.0025,12.5,1000,800
"""
    file_path = tmp_path / "futures_products.csv"
    file_path.write_text(csv_content, encoding="utf-8")
    return file_path


def test_parse_futures_products_csv(sample_csv: Path) -> None:
    """Test parsing a CSV file into FuturesProduct domain objects."""
    data = parse_futures_products_csv(str(sample_csv))

    # Assert the number of parsed products
    assert len(data) == 2
    assert isinstance(data[0], FuturesProduct)
    assert isinstance(data[1], FuturesProduct)

    # Assert the first product's fields
    gold = data[0]
    assert gold.product_id == "comex_gold_futures"
    assert gold.venue == "COMEX"
    assert gold.description == "Gold Futures"
    assert gold.currency == Currency.USD
    assert gold.unit == ProductUnit.TROY_OUNCE
    assert gold.contract_size == 100.0
    assert gold.listing_rule == "Monthly contracts listed for 3 consecutive months"
    assert gold.period_types == (PeriodType.MONTH,)
    assert gold.settlement == SettlementMethod.PHYSICAL
    assert gold.last_trading_rule == "3rd last business day of delivery month"
    assert gold.expiry_rule == "3rd last business day of delivery month"
    assert gold.trading_calendar == "CME DEFAULT"
    assert gold.trading_hours == "Sunday - Friday 6:00 p.m. - 5:00 p.m."
    assert gold.tick_size == 0.1
    assert gold.tick_value == 10.0
    assert gold.initial_margin == 5000.0
    assert gold.maintenance_margin == 4000.0

    # Assert the second product's fields
    corn = data[1]
    assert corn.product_id == "cbot_corn_futures"
    assert corn.venue == "CBOT"
    assert corn.description == "Corn Futures"
    assert corn.currency == Currency.USD
    assert corn.unit == ProductUnit.BUSHEL
    assert corn.contract_size == 5000.0
    assert corn.listing_rule == "9 monthly contracts listed"
    assert corn.period_types == (PeriodType.MONTH,)
    assert corn.settlement == SettlementMethod.PHYSICAL
    assert corn.last_trading_rule == "15th day prior to contract month"
    assert corn.expiry_rule == "15th day prior to contract month"
    assert corn.trading_calendar == "CME DEFAULT"
    assert corn.trading_hours == "Sunday - Friday 7:00 p.m. - 7:45 a.m."
    assert corn.tick_size == 0.0025
    assert corn.tick_value == 12.5
    assert corn.initial_margin == 1000.0
    assert corn.maintenance_margin == 800.0


def test_parse_futures_products_csv_with_missing_required_fields(
    tmp_path: Path,
) -> None:
    """Test parsing fails if required fields are missing."""
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours
missing_field_product,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","Monthly contracts listed for the next year",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"7:00 p.m. - 7:45 a.m."
"""
    file_path = tmp_path / "missing_fields_futures_products.csv"
    file_path.write_text(csv_content, encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required fields in CSV"):
        parse_futures_products_csv(str(file_path))


def test_parse_futures_products_csv_with_optional_fields_missing(
    tmp_path: Path,
) -> None:
    """
    Test parsing succeeds when optional numeric fields are absent.

    Note: The CSV must still include the column headers for required fields.
    Optional values may be empty.
    """
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value,initial_margin,maintenance_margin
optional_fields_missing,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","Monthly contracts listed for the next year",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"7:00 p.m. - 7:45 a.m.",0.0025,12.5,,
"""
    file_path = tmp_path / "optional_fields_missing_futures_products.csv"
    file_path.write_text(csv_content, encoding="utf-8")

    data = parse_futures_products_csv(str(file_path))

    assert len(data) == 1
    p = data[0]
    assert p.product_id == "optional_fields_missing"
    assert p.period_types == (PeriodType.MONTH,)
    assert p.initial_margin is None
    assert p.maintenance_margin is None


def test_parse_futures_products_csv_with_multiple_period_types(tmp_path: Path) -> None:
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value,initial_margin,maintenance_margin
multi_pt,TEST,Multi PT Product,USD,BUSHEL,1.0,"FGHJKMNQUVXZ","Mixed periods",MONTH|QUARTER|YEAR,PHYSICAL,"rule","rule",CME DEFAULT,"hours",0.1,1.0,,
"""
    file_path = tmp_path / "multi_period_types.csv"
    file_path.write_text(csv_content, encoding="utf-8")

    data = parse_futures_products_csv(str(file_path))
    assert len(data) == 1
    p = data[0]
    assert p.period_types == (PeriodType.MONTH, PeriodType.QUARTER, PeriodType.YEAR)
