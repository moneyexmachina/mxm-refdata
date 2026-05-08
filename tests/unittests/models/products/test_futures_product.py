"""Unit tests for the FuturesProduct dataclass."""

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit


def test_futures_product_initialization():
    """Test initialization of a FuturesProduct with required fields."""
    product = FuturesProduct(
        product_id="GC",
        venue="COMEX",
        description="Gold Futures",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="monthly for all months",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="3rd Friday of the delivery month",
        trading_calendar="CME default",
    )

    assert product.product_id == "GC"
    assert product.venue == "COMEX"
    assert product.description == "Gold Futures"
    assert product.currency == Currency.USD
    assert product.unit == ProductUnit.TROY_OUNCE
    assert product.contract_size == 100.0
    assert product.listing_rule == "monthly for all months"
    assert product.period_types == (PeriodType.MONTH,)
    assert product.settlement == SettlementMethod.PHYSICAL
    assert product.expiry_rule == "3rd Friday of the delivery month"
    assert product.trading_calendar == "CME default"


def test_futures_product_optional_fields():
    """Test optional fields of FuturesProduct."""
    product = FuturesProduct(
        product_id="GC",
        venue="COMEX",
        description="Gold Futures",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="monthly for all months",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="3rd Friday of the delivery month",
        trading_calendar="CME default",
        trading_hours="23:00 - 22:00 UTC",
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=5000.0,
        maintenance_margin=4500.0,
    )

    assert product.trading_hours == "23:00 - 22:00 UTC"
    assert product.tick_size == 0.1
    assert product.tick_value == 10.0
    assert product.initial_margin == 5000.0
    assert product.maintenance_margin == 4500.0
