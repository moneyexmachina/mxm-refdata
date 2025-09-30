"""Mapping FuturesContract instances to and from FuturesContractORM instances."""

from mxm_refdata.models.contracts.futures_contract import FuturesContract
from mxm_refdata.models.orm import FuturesContractORM
from mxm_refdata.models.products.futures_product import Currency, ProductUnit


def futures_contract_to_orm(contract: FuturesContract) -> FuturesContractORM:
    """
    Map a FuturesContract object to a FuturesContractORM instance.

    Args:
        contract (FuturesContract): The internal FuturesContract object.

    Returns:
        FuturesContractORM: The corresponding ORM instance.
    """
    return FuturesContractORM(
        contract_id=contract.contract_id,
        product_id=contract.product_id,
        period_id=contract.period_id,
        contract_size=contract.contract_size,
        unit=contract.unit,
        currency=contract.currency,
        trading_calendar=contract.trading_calendar,
        first_day_of_interest=contract.first_day_of_interest,
        last_trading_day=contract.last_trading_day,
    )


def futures_contract_from_orm(orm: FuturesContractORM) -> FuturesContract:
    """
    Map a FuturesContractORM object to a FuturesContract object.

    Args:
        orm (FuturesContractORM): The ORM object to map from.

    Returns:
        FuturesContract: The mapped internal representation.
    """
    return FuturesContract(
        product_id=orm.product_id,  # Directly use product_id
        period_id=orm.period_id,  # Directly use period_id
        contract_id=orm.contract_id,
        contract_size=orm.contract_size,
        currency=Currency[orm.currency.name],  # Map string to Currency Enum
        unit=ProductUnit[orm.unit.name],  # Map string to ProductUnit Enum
        trading_calendar=orm.trading_calendar,
        first_day_of_interest=orm.first_day_of_interest,
        last_trading_day=orm.last_trading_day,
    )
