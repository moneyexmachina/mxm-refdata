"""Focused unit tests for RefDataAPI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import cast

import pytest
from pytest import MonkeyPatch
from pytest_mock import MockerFixture

from mxm.config import MXMConfig
from mxm.refdata import queries
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.mappings import (
    futures_contract_to_orm,
    futures_product_to_orm,
    period_to_orm,
)
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.queries import RefDataLookupError
from mxm.refdata.utils.cache_manager import CacheManager


@pytest.fixture(scope="module")
def db_session_manager() -> SQLSessionManager:
    """Provide an SQLSessionManager using an in-memory SQLite database."""
    session_manager = SQLSessionManager.from_db_url("sqlite:///:memory:")
    session_manager.init_db()
    return session_manager


@pytest.fixture(autouse=True)
def reset_db(db_session_manager: SQLSessionManager) -> None:
    """Ensure a clean database state before each test."""
    db_session_manager.drop_db()
    db_session_manager.init_db()


@pytest.fixture
def refdata_config() -> MXMConfig:
    """Provide explicit RefDataAPI config for unit tests."""
    return cast(
        MXMConfig,
        {
            "SQL_DB_URL": "sqlite:///:memory:",
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
            "REFDATA_CONTRACT_START_DATE": "2000-01-02",
            "REFDATA_CONTRACT_END_DATE": "2046-12-31",
        },
    )


def _mock_check_refdata_ready(*_args: object, **_kwargs: object) -> None:
    _ = _args
    _ = _kwargs
    return None


@dataclass
class RefDataFixture:
    config: MXMConfig
    session_manager: SQLSessionManager
    cache: CacheManager[object]


@pytest.fixture
def refdata(
    db_session_manager: SQLSessionManager,
    refdata_config: MXMConfig,
    monkeypatch: MonkeyPatch,
) -> RefDataFixture:
    monkeypatch.setattr(
        "mxm.refdata.queries.check_refdata_ready",
        _mock_check_refdata_ready,
    )
    return RefDataFixture(
        config=refdata_config,
        session_manager=db_session_manager,
        cache=CacheManager(maxsize=10000),
    )


@pytest.fixture
def mock_data(db_session_manager: SQLSessionManager) -> None:
    """Populate the database with one product, one period, and one contract."""
    with db_session_manager.db_session_scope() as session:
        product = FuturesProduct(
            product_id="gold_fut",
            venue="CME",
            description="Gold Futures",
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            contract_size=100.0,
            valid_period_rule="FGHJKMNQUVXZ",
            listing_rule="Monthly",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.PHYSICAL,
            last_trading_rule="3rd last business day of the delivery month",
            expiry_rule="End of Month",
            trading_calendar="Default Calendar",
            tick_size=0.1,
            tick_value=10.0,
        )
        session.add(futures_product_to_orm(product))

        period = Period(
            period_id="Jan-2025",
            period_type=PeriodType.MONTH,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 31),
        )
        session.add(period_to_orm(period))

        contract = FuturesContract(
            product_id="gold_fut",
            period_id="Jan-2025",
            contract_id="gold_fut.Jan-2025",
            contract_size=100.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        session.add(futures_contract_to_orm(contract))


@pytest.mark.usefixtures("mock_data")
def test_get_product_by_id(refdata: RefDataFixture) -> None:
    product = queries.get_product_by_id(refdata, "gold_fut")

    assert product is not None
    assert product.product_id == "gold_fut"


@pytest.mark.usefixtures("mock_data")
def test_get_contracts_for_date(refdata: RefDataFixture) -> None:
    contracts = queries.get_contracts_for_date(refdata, date(2025, 1, 15))

    assert len(contracts) == 1
    assert contracts[0].contract_id == "gold_fut.Jan-2025"


@pytest.mark.usefixtures("mock_data")
def test_caching_behavior(refdata: RefDataFixture, mocker: MockerFixture) -> None:
    spy = mocker.spy(refdata.session_manager, "db_session_scope")

    queries.get_product_by_id(refdata, "gold_fut")
    assert spy.call_count == 1

    queries.get_product_by_id(refdata, "gold_fut")
    assert spy.call_count == 1


@pytest.fixture
def mock_data_active_contracts(db_session_manager: SQLSessionManager) -> None:
    with db_session_manager.db_session_scope() as session:
        gold = FuturesProduct(
            product_id="gold_fut",
            venue="CME",
            description="Gold Futures",
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            contract_size=100.0,
            valid_period_rule="FGHJKMNQUVXZ",
            listing_rule="Monthly",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.PHYSICAL,
            last_trading_rule="3rd last business day of the delivery month",
            expiry_rule="End of Month",
            trading_calendar="Default Calendar",
            tick_size=0.1,
            tick_value=10.0,
        )
        corn = FuturesProduct(
            product_id="corn_fut",
            venue="CBOT",
            description="Corn Futures",
            currency=Currency.USD,
            unit=ProductUnit.BUSHEL,
            contract_size=5000.0,
            valid_period_rule="HKNUZ",
            listing_rule="Monthly",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.PHYSICAL,
            last_trading_rule="Business day prior to 15th calendar day",
            expiry_rule="End of Month",
            trading_calendar="Default Calendar",
            tick_size=0.25,
            tick_value=12.5,
        )
        session.add(futures_product_to_orm(gold))
        session.add(futures_product_to_orm(corn))

        jan_2025 = Period(
            period_id="Jan-2025",
            period_type=PeriodType.MONTH,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 31),
        )
        feb_2025 = Period(
            period_id="Feb-2025",
            period_type=PeriodType.MONTH,
            first_date=date(2025, 2, 1),
            last_date=date(2025, 2, 28),
        )
        session.add(period_to_orm(jan_2025))
        session.add(period_to_orm(feb_2025))

        contracts = [
            FuturesContract(
                product_id="gold_fut",
                period_id="Jan-2025",
                contract_id="gold_fut.Jan-2025",
                contract_size=100.0,
                currency=Currency.USD,
                unit=ProductUnit.TROY_OUNCE,
                trading_calendar="Default Calendar",
                first_day_of_interest=date(2025, 1, 1),
                last_trading_day=date(2025, 1, 29),
            ),
            FuturesContract(
                product_id="gold_fut",
                period_id="Feb-2025",
                contract_id="gold_fut.Feb-2025",
                contract_size=100.0,
                currency=Currency.USD,
                unit=ProductUnit.TROY_OUNCE,
                trading_calendar="Default Calendar",
                first_day_of_interest=date(2025, 1, 30),
                last_trading_day=date(2025, 2, 26),
            ),
            FuturesContract(
                product_id="corn_fut",
                period_id="Jan-2025",
                contract_id="corn_fut.Jan-2025",
                contract_size=5000.0,
                currency=Currency.USD,
                unit=ProductUnit.BUSHEL,
                trading_calendar="Default Calendar",
                first_day_of_interest=date(2025, 1, 10),
                last_trading_day=date(2025, 1, 20),
            ),
            FuturesContract(
                product_id="corn_fut",
                period_id="Feb-2025",
                contract_id="corn_fut.Feb-2025",
                contract_size=5000.0,
                currency=Currency.USD,
                unit=ProductUnit.BUSHEL,
                trading_calendar="Default Calendar",
                first_day_of_interest=date(2025, 2, 1),
                last_trading_day=date(2025, 2, 10),
            ),
        ]

        for contract in contracts:
            session.add(futures_contract_to_orm(contract))


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_semantics_and_boundaries(
    refdata: RefDataFixture,
) -> None:
    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 1),
        product_id="gold_fut",
    )
    assert [contract.contract_id for contract in contracts] == ["gold_fut.Jan-2025"]

    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 29),
        product_id="gold_fut",
    )
    assert [contract.contract_id for contract in contracts] == ["gold_fut.Jan-2025"]

    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 30),
        product_id="corn_fut",
    )
    assert [contract.contract_id for contract in contracts] == []

    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 15),
        product_id="corn_fut",
    )
    assert [contract.contract_id for contract in contracts] == ["corn_fut.Jan-2025"]


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_product_id_filter(refdata: RefDataFixture) -> None:
    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 15),
        product_id="gold_fut",
    )

    assert all(contract.product_id == "gold_fut" for contract in contracts)
    assert [contract.contract_id for contract in contracts] == ["gold_fut.Jan-2025"]


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_product_ids_filter(refdata: RefDataFixture) -> None:
    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 15),
        product_ids=["gold_fut", "corn_fut"],
    )

    assert [contract.contract_id for contract in contracts] == [
        "corn_fut.Jan-2025",
        "gold_fut.Jan-2025",
    ]


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_empty_product_ids_returns_empty(
    refdata: RefDataFixture,
) -> None:
    contracts = queries.get_active_contracts(
        refdata,
        date(2025, 1, 15),
        product_ids=[],
    )

    assert contracts == []


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_rejects_both_product_id_and_product_ids(
    refdata: RefDataFixture,
) -> None:
    with pytest.raises(ValueError):
        queries.get_active_contracts(
            refdata,
            date(2025, 1, 15),
            product_id="gold_fut",
            product_ids=["gold_fut"],
        )


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_caching_behavior(
    refdata: RefDataFixture,
    mocker: MockerFixture,
) -> None:
    spy = mocker.spy(refdata.session_manager, "db_session_scope")

    queries.get_active_contracts(refdata, date(2025, 1, 15), product_id="gold_fut")
    assert spy.call_count == 1

    queries.get_active_contracts(refdata, date(2025, 1, 15), product_id="gold_fut")
    assert spy.call_count == 1


def test_get_contracts_for_product_orders_by_period(
    refdata: RefDataFixture,
    db_session_manager: SQLSessionManager,
) -> None:
    with db_session_manager.db_session_scope() as session:
        product = FuturesProduct(
            product_id="mix_tenor_fut",
            venue="CME",
            description="Mixed Tenor Futures",
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            contract_size=1.0,
            valid_period_rule="",
            listing_rule="Mixed",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.CASH,
            last_trading_rule="",
            expiry_rule="",
            trading_calendar="Default Calendar",
            tick_size=0.01,
            tick_value=1.0,
        )
        session.add(futures_product_to_orm(product))

        p_year_2025 = Period(
            period_id="2025",
            period_type=PeriodType.YEAR,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 12, 31),
        )
        p_month_jan_2025 = Period(
            period_id="Jan-2025",
            period_type=PeriodType.MONTH,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 31),
        )
        session.add(period_to_orm(p_year_2025))
        session.add(period_to_orm(p_month_jan_2025))

        c_month = FuturesContract(
            product_id="mix_tenor_fut",
            period_id="Jan-2025",
            contract_id="mix_tenor_fut.Jan-2025",
            contract_size=1.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2024, 12, 1),
            last_trading_day=date(2025, 1, 30),
        )
        c_year = FuturesContract(
            product_id="mix_tenor_fut",
            period_id="2025",
            contract_id="mix_tenor_fut.2025",
            contract_size=1.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2024, 1, 1),
            last_trading_day=date(2025, 12, 15),
        )
        session.add(futures_contract_to_orm(c_month))
        session.add(futures_contract_to_orm(c_year))

    contracts = queries.get_contracts_for_product(refdata, "mix_tenor_fut")

    assert [contract.contract_id for contract in contracts] == [
        "mix_tenor_fut.2025",
        "mix_tenor_fut.Jan-2025",
    ]


@pytest.mark.usefixtures("mock_data")
def test_get_contract_by_id_found(refdata: RefDataFixture) -> None:
    contract = queries.get_contract_by_id(refdata, "gold_fut.Jan-2025")

    assert contract.contract_id == "gold_fut.Jan-2025"


@pytest.mark.usefixtures("mock_data")
def test_get_contract_by_id_missing(refdata: RefDataFixture) -> None:
    with pytest.raises(RefDataLookupError):
        queries.get_contract_by_id(refdata, "does_not_exist")


@pytest.mark.usefixtures("mock_data")
def test_maybe_get_contract_by_id_missing(refdata: RefDataFixture) -> None:
    contract = queries.maybe_get_contract_by_id(refdata, "does_not_exist")

    assert contract is None


def test_get_contracts_by_id_preserves_order_and_ignores_missing(
    refdata: RefDataFixture,
    db_session_manager: SQLSessionManager,
) -> None:
    with db_session_manager.db_session_scope() as session:
        product = FuturesProduct(
            product_id="lookup_fut",
            venue="CME",
            description="Lookup Futures",
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            contract_size=1.0,
            valid_period_rule="",
            listing_rule="Monthly",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.CASH,
            last_trading_rule="",
            expiry_rule="",
            trading_calendar="Default Calendar",
            tick_size=0.01,
            tick_value=1.0,
        )
        session.add(futures_product_to_orm(product))

        period = Period(
            period_id="Jan-2025",
            period_type=PeriodType.MONTH,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 31),
        )
        session.add(period_to_orm(period))

        c1 = FuturesContract(
            product_id="lookup_fut",
            period_id="Jan-2025",
            contract_id="lookup_fut.A",
            contract_size=1.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        c2 = FuturesContract(
            product_id="lookup_fut",
            period_id="Jan-2025",
            contract_id="lookup_fut.B",
            contract_size=1.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 2),
            last_trading_day=date(2025, 1, 30),
        )
        session.add(futures_contract_to_orm(c1))
        session.add(futures_contract_to_orm(c2))

    contracts = queries.get_contracts_by_id(
        refdata, ["lookup_fut.B", "missing", "lookup_fut.A", "lookup_fut.B"]
    )

    assert [contract.contract_id for contract in contracts] == [
        "lookup_fut.B",
        "lookup_fut.A",
        "lookup_fut.B",
    ]


@pytest.mark.usefixtures("mock_data")
def test_get_contracts_by_id_empty_list_returns_empty(
    refdata: RefDataFixture,
) -> None:
    assert queries.get_contracts_by_id(refdata, []) == []


@pytest.mark.usefixtures("mock_data")
def test_get_contract_by_id_caching_behavior(
    refdata: RefDataFixture,
    mocker: MockerFixture,
) -> None:
    spy = mocker.spy(refdata.session_manager, "db_session_scope")

    queries.get_contract_by_id(refdata, "gold_fut.Jan-2025")
    assert spy.call_count == 1

    queries.get_contract_by_id(refdata, "gold_fut.Jan-2025")
    assert spy.call_count == 1


def test_get_contracts_by_id_caching_behavior(
    refdata: RefDataFixture,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
) -> None:
    with db_session_manager.db_session_scope() as session:
        product = FuturesProduct(
            product_id="lookup_cache_fut",
            venue="CME",
            description="Lookup Cache Futures",
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            contract_size=1.0,
            valid_period_rule="",
            listing_rule="Monthly",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.CASH,
            last_trading_rule="",
            expiry_rule="",
            trading_calendar="Default Calendar",
            tick_size=0.01,
            tick_value=1.0,
        )
        session.add(futures_product_to_orm(product))

        period = Period(
            period_id="Jan-2025",
            period_type=PeriodType.MONTH,
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 31),
        )
        session.add(period_to_orm(period))

        contract = FuturesContract(
            product_id="lookup_cache_fut",
            period_id="Jan-2025",
            contract_id="lookup_cache_fut.A",
            contract_size=1.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        session.add(futures_contract_to_orm(contract))

    spy = mocker.spy(refdata.session_manager, "db_session_scope")

    queries.get_contracts_by_id(refdata, ["lookup_cache_fut.A"])
    assert spy.call_count == 1

    queries.get_contracts_by_id(refdata, ["lookup_cache_fut.A"])
    assert spy.call_count == 1
