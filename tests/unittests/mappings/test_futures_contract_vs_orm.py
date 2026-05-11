"""Unit-tests for mapping FuturesContract to and from ORM."""

import datetime

import pytest

from mxm.refdata.mappings.futures_contract_vs_orm import (
    futures_contract_from_orm,
    futures_contract_to_orm,
)
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.products.futures_product import ProductUnit


@pytest.fixture
def futures_contract():
    """Fixture for a sample FuturesContract."""
    return FuturesContract(
        product_id="GOLD",
        period_id="2024-12",
        contract_id="GOLD_2024-12",
        contract_size=100.0,
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        trading_calendar="CME Default",
        first_day_of_interest=datetime.date(2024, 12, 1),
        last_trading_day=datetime.date(2024, 12, 31),
    )


def test_futures_contract_to_orm(futures_contract: FuturesContract):
    """Test mapping FuturesContract to ORM."""
    orm_instance = futures_contract_to_orm(futures_contract)

    assert isinstance(orm_instance, FuturesContractORM), (
        "Mapping should return an ORM instance."
    )
    assert orm_instance.contract_id == futures_contract.contract_id
    assert orm_instance.product_id == futures_contract.product_id
    assert orm_instance.period_id == futures_contract.period_id
    assert orm_instance.contract_size == futures_contract.contract_size
    assert orm_instance.currency == futures_contract.currency
    assert orm_instance.unit == futures_contract.unit
    assert orm_instance.trading_calendar == futures_contract.trading_calendar
    assert orm_instance.first_day_of_interest == futures_contract.first_day_of_interest
    assert orm_instance.last_trading_day == futures_contract.last_trading_day


def test_futures_contract_from_orm(futures_contract: FuturesContract):
    """Test mapping ORM to FuturesContract."""
    # Create ORM instance
    contract_orm = FuturesContractORM(
        contract_id=futures_contract.contract_id,
        product_id=futures_contract.product_id,
        period_id=futures_contract.period_id,
        contract_size=futures_contract.contract_size,
        currency=futures_contract.currency,
        unit=futures_contract.unit,
        trading_calendar=futures_contract.trading_calendar,
        first_day_of_interest=futures_contract.first_day_of_interest,
        last_trading_day=futures_contract.last_trading_day,
    )

    # Map back to internal FuturesContract
    contract = futures_contract_from_orm(contract_orm)

    assert isinstance(contract, FuturesContract), (
        "Mapping should return a FuturesContract instance."
    )
    assert contract.contract_id == contract_orm.contract_id
    assert contract.product_id == contract_orm.product_id
    assert contract.period_id == contract_orm.period_id
    assert contract.contract_size == contract_orm.contract_size
    assert contract.currency == contract_orm.currency
    assert contract.unit == contract_orm.unit
    assert contract.trading_calendar == contract_orm.trading_calendar
    assert contract.first_day_of_interest == contract_orm.first_day_of_interest
    assert contract.last_trading_day == contract_orm.last_trading_day


def test_futures_contract_round_trip(futures_contract: FuturesContract):
    """Test round-trip mapping between FuturesContract and ORM."""
    # Map to ORM and back to internal
    orm_instance = futures_contract_to_orm(futures_contract)
    contract = futures_contract_from_orm(orm_instance)

    assert contract == futures_contract, (
        "Round-trip mapping should preserve the contract."
    )
