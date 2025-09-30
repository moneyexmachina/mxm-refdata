"""Test suite for parsing csv file into normalised futures_product data."""

import pytest

from mxm_refdata.models.currencies import Currency
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.models.products.futures_product import SettlementMethod
from mxm_refdata.models.units import ProductUnit
from mxm_refdata.parsing.futures_products_from_csv import (
    parse_futures_products_csv_to_normalised_data,
)


@pytest.fixture
def sample_csv(tmp_path):
    """Create a temporary CSV file for testing."""
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value,initial_margin,maintenance_margin
comex_gold_futures,COMEX,Gold Futures,USD,TROY_OUNCE,100.0,"FGHJKMNQUVXZ","Monthly contracts listed for 3 consecutive months",MONTH,PHYSICAL,"3rd last business day of delivery month","3rd last business day of delivery month",CME DEFAULT,"Sunday - Friday 6:00 p.m. - 5:00 p.m.",0.1,10.0,5000,4000
cbot_corn_futures,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","9 monthly contracts listed",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"Sunday - Friday 7:00 p.m. - 7:45 a.m.",0.0025,12.5,1000,800
"""
    file_path = tmp_path / "futures_products.csv"
    file_path.write_text(csv_content)
    return file_path


def test_parse_futures_products_csv_to_normalised_data(sample_csv):
    """Test the parsing of a CSV file into normalized futures product data."""
    data = parse_futures_products_csv_to_normalised_data(str(sample_csv))

    # Assert the number of parsed products
    assert len(data) == 2

    # Assert the first product's fields
    gold_product = data[0]
    assert gold_product["product_id"] == "comex_gold_futures"
    assert gold_product["venue"] == "COMEX"
    assert gold_product["description"] == "Gold Futures"
    assert gold_product["currency"] == Currency.USD
    assert gold_product["unit"] == ProductUnit.TROY_OUNCE
    assert gold_product["contract_size"] == 100.0
    assert (
        gold_product["listing_rule"]
        == "Monthly contracts listed for 3 consecutive months"
    )
    assert gold_product["period_types"] == PeriodType.MONTH
    assert gold_product["settlement"] == SettlementMethod.PHYSICAL
    assert (
        gold_product["last_trading_rule"] == "3rd last business day of delivery month"
    )
    assert gold_product["expiry_rule"] == "3rd last business day of delivery month"
    assert gold_product["trading_calendar"] == "CME DEFAULT"
    assert gold_product["trading_hours"] == "Sunday - Friday 6:00 p.m. - 5:00 p.m."
    assert gold_product["tick_size"] == 0.1
    assert gold_product["tick_value"] == 10.0
    assert gold_product["initial_margin"] == 5000
    assert gold_product["maintenance_margin"] == 4000

    # Assert the second product's fields
    corn_product = data[1]
    assert corn_product["product_id"] == "cbot_corn_futures"
    assert corn_product["venue"] == "CBOT"
    assert corn_product["description"] == "Corn Futures"
    assert corn_product["currency"] == Currency.USD
    assert corn_product["unit"] == ProductUnit.BUSHEL
    assert corn_product["contract_size"] == 5000.0
    assert corn_product["listing_rule"] == "9 monthly contracts listed"
    assert corn_product["period_types"] == PeriodType.MONTH
    assert corn_product["settlement"] == SettlementMethod.PHYSICAL
    assert corn_product["last_trading_rule"] == "15th day prior to contract month"
    assert corn_product["expiry_rule"] == "15th day prior to contract month"
    assert corn_product["trading_calendar"] == "CME DEFAULT"
    assert corn_product["trading_hours"] == "Sunday - Friday 7:00 p.m. - 7:45 a.m."
    assert corn_product["tick_size"] == 0.0025
    assert corn_product["tick_value"] == 12.5
    assert corn_product["initial_margin"] == 1000
    assert corn_product["maintenance_margin"] == 800


def test_parse_futures_products_csv_with_missing_required_fields(tmp_path):
    """Test parsing fails if required fields are missing."""
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours
missing_field_product,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","Monthly contracts listed for the next year",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"7:00 p.m. - 7:45 a.m."
"""
    file_path = tmp_path / "missing_fields_futures_products.csv"
    file_path.write_text(csv_content)

    with pytest.raises(ValueError, match="Missing required fields in CSV"):
        parse_futures_products_csv_to_normalised_data(str(file_path))


def test_parse_futures_products_csv_with_optional_fields_missing(tmp_path):
    """Test parsing succeeds when optional fields are missing."""
    csv_content = """product_id,venue,description,currency,unit,contract_size,valid_period_rule,listing_rule,period_types,settlement,last_trading_rule,expiry_rule,trading_calendar,trading_hours,tick_size,tick_value
optional_fields_missing,CBOT,Corn Futures,USD,BUSHEL,5000.0,"FGHJKMNQUVXZ","Monthly contracts listed for the next year",MONTH,PHYSICAL,"15th day prior to contract month","15th day prior to contract month",CME DEFAULT,"7:00 p.m. - 7:45 a.m.",0.0025,12.5
"""
    file_path = tmp_path / "optional_fields_missing_futures_products.csv"
    file_path.write_text(csv_content)

    data = parse_futures_products_csv_to_normalised_data(str(file_path))

    assert len(data) == 1
    product = data[0]
    assert product["product_id"] == "optional_fields_missing"
    assert product["initial_margin"] is None
    assert product["maintenance_margin"] is None
