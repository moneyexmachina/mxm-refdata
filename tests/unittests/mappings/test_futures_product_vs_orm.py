"""Tests for the mappings between FuturesProduct and FuturesProductORM."""

from mxm_refdata.mappings.futures_product_vs_orm import (
    futures_product_from_orm,
    futures_product_to_orm,
)
from mxm_refdata.models.currencies import Currency
from mxm_refdata.models.orm import FuturesProductORM
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm_refdata.models.units import ProductUnit


def test_futures_product_to_orm():
    product = FuturesProduct(
        product_id="test_product",
        venue="TEST",
        description="Test Futures Product",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="Monthly contracts for all months",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="3rd Friday of the delivery month",
        trading_calendar="TEST_CALENDAR",
        trading_hours="24/7",
        tick_size=0.01,
        tick_value=10.0,
    )

    orm_instance = futures_product_to_orm(product)
    assert orm_instance.product_id == product.product_id
    assert orm_instance.currency == product.currency
    assert orm_instance.unit == product.unit
    assert orm_instance.settlement == product.settlement


def test_futures_product_from_orm() -> None:
    orm_instance = FuturesProductORM(
        product_id="test_product",
        venue="TEST",
        description="Test Futures Product",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="Monthly contracts for all months",
        period_types="MONTH",  # <-- encoded TEXT
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="3rd Friday of the delivery month",
        trading_calendar="TEST_CALENDAR",
        trading_hours="24/7",
        tick_size=0.01,
        tick_value=10.0,
    )

    product = futures_product_from_orm(orm_instance)
    assert product.period_types == (PeriodType.MONTH,)
    assert product.product_id == orm_instance.product_id
    assert product.currency == orm_instance.currency
    assert product.unit == orm_instance.unit
    assert product.settlement == orm_instance.settlement
