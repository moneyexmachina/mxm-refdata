"""Test suite for the ORM-to-Model conversion utilities."""

import pytest

from mxm_refdata.mappings.orm_converter import (
    get_model_class,
    get_orm_class,
    obj_to_orm,
    orm_to_obj,
)
from mxm_refdata.models.contracts.futures_contract import FuturesContract
from mxm_refdata.models.orm import FuturesContractORM, FuturesProductORM, PeriodORM
from mxm_refdata.models.periods import Period
from mxm_refdata.models.products.futures_product import FuturesProduct


def test_get_orm_class():
    """Test retrieval of ORM class for a given internal model class."""
    assert get_orm_class(FuturesProduct) == FuturesProductORM
    assert get_orm_class(FuturesContract) == FuturesContractORM
    assert get_orm_class(Period) == PeriodORM

    with pytest.raises(ValueError, match="No ORM class for <class 'str'>"):
        get_orm_class(str)


def test_get_model_class():
    """Test retrieval of internal model class for a given ORM class."""
    assert get_model_class(FuturesProductORM) == FuturesProduct
    assert get_model_class(FuturesContractORM) == FuturesContract
    assert get_model_class(PeriodORM) == Period

    with pytest.raises(ValueError, match="No model class for <class 'int'>"):
        get_model_class(int)


def test_orm_to_obj():
    """Test converting an ORM object to an internal model object."""
    orm_obj = FuturesProductORM(
        product_id="gold_fut",
        venue="CME",
        description="Gold Futures",
        currency="USD",
        unit="TROY_OUNCE",
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="Monthly",
        period_types="MONTH",
        settlement="PHYSICAL",
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="End of Month",
        trading_calendar="Default Calendar",
        trading_hours=None,
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=None,
        maintenance_margin=None,
    )

    model_obj = orm_to_obj(orm_obj)

    assert isinstance(model_obj, FuturesProduct)
    assert model_obj.product_id == orm_obj.product_id
    assert model_obj.venue == orm_obj.venue
    assert model_obj.description == orm_obj.description
    assert model_obj.currency == orm_obj.currency
    assert model_obj.unit == orm_obj.unit
    assert model_obj.contract_size == orm_obj.contract_size
    assert model_obj.valid_period_rule == orm_obj.valid_period_rule
    assert model_obj.listing_rule == orm_obj.listing_rule
    assert model_obj.period_types == orm_obj.period_types
    assert model_obj.settlement == orm_obj.settlement
    assert model_obj.last_trading_rule == orm_obj.last_trading_rule
    assert model_obj.expiry_rule == orm_obj.expiry_rule
    assert model_obj.trading_calendar == orm_obj.trading_calendar
    assert model_obj.trading_hours == orm_obj.trading_hours
    assert model_obj.tick_size == orm_obj.tick_size
    assert model_obj.tick_value == orm_obj.tick_value
    assert model_obj.initial_margin == orm_obj.initial_margin
    assert model_obj.maintenance_margin == orm_obj.maintenance_margin


def test_obj_to_orm():
    """Test converting an internal model object to an ORM object."""
    model_obj = FuturesProduct(
        product_id="gold_fut",
        venue="CME",
        description="Gold Futures",
        currency="USD",
        unit="TROY_OUNCE",
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="Monthly",
        period_types="MONTH",
        settlement="PHYSICAL",
        last_trading_rule="3rd last business day of the delivery month",
        expiry_rule="End of Month",
        trading_calendar="Default Calendar",
        trading_hours=None,
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=None,
        maintenance_margin=None,
    )

    orm_obj = obj_to_orm(model_obj)

    assert isinstance(orm_obj, FuturesProductORM)
    assert orm_obj.product_id == model_obj.product_id
    assert orm_obj.venue == model_obj.venue
    assert orm_obj.description == model_obj.description
    assert orm_obj.currency == model_obj.currency
    assert orm_obj.unit == model_obj.unit
    assert orm_obj.contract_size == model_obj.contract_size
    assert orm_obj.valid_period_rule == model_obj.valid_period_rule
    assert orm_obj.listing_rule == model_obj.listing_rule
    assert orm_obj.period_types == model_obj.period_types
    assert orm_obj.settlement == model_obj.settlement
    assert orm_obj.last_trading_rule == model_obj.last_trading_rule
    assert orm_obj.expiry_rule == model_obj.expiry_rule
    assert orm_obj.trading_calendar == model_obj.trading_calendar
    assert orm_obj.trading_hours == model_obj.trading_hours
    assert orm_obj.tick_size == model_obj.tick_size
    assert orm_obj.tick_value == model_obj.tick_value
    assert orm_obj.initial_margin == model_obj.initial_margin
    assert orm_obj.maintenance_margin == model_obj.maintenance_margin
