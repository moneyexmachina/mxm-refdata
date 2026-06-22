"""Focused unit tests for RefDataAPI."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from pytest_mock import MockerFixture

from mxm.refdata.api import RefDataAPI, RefDataLookupError
from mxm.refdata.config import RefDataConfigData
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
def refdata_config() -> RefDataConfigData:
    """Provide explicit RefDataAPI config for unit tests."""
    return {
        "SQL_DB_URL": "sqlite:///:memory:",
        "REFDATA_DB_MODE": "buildable",
        "REFDATA_FUTURES_PRODUCTS_CSV_PATH": "/tmp/products.csv",
        "REFDATA_CONTRACT_START_DATE": "2000-01-02",
        "REFDATA_CONTRACT_END_DATE": "2046-12-31",
    }


def _mock_ensure_refdata_ready(*_args: object, **_kwargs: object) -> None:
    _ = _args
    _ = _kwargs
    return None


@pytest.fixture
def ref_data_api(
    db_session_manager: SQLSessionManager,
    refdata_config: RefDataConfigData,
    monkeypatch: MonkeyPatch,
) -> RefDataAPI:
    """Create a RefDataAPI instance with explicit dependencies."""
    monkeypatch.setattr(
        "mxm.refdata.api.ensure_refdata_ready",
        _mock_ensure_refdata_ready,
    )
    return RefDataAPI(
        config=refdata_config,
        session_manager=db_session_manager,
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
def test_get_product_by_id(ref_data_api: RefDataAPI) -> None:
    product = ref_data_api.get_product_by_id("gold_fut")

    assert product is not None
    assert product.product_id == "gold_fut"


@pytest.mark.usefixtures("mock_data")
def test_get_contracts_for_date(ref_data_api: RefDataAPI) -> None:
    contracts = ref_data_api.get_contracts_for_date(date(2025, 1, 15))

    assert len(contracts) == 1
    assert contracts[0].contract_id == "gold_fut.Jan-2025"


@pytest.mark.usefixtures("mock_data")
def test_caching_behavior(ref_data_api: RefDataAPI, mocker: MockerFixture) -> None:
    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_product_by_id("gold_fut")
    assert spy.call_count == 1

    ref_data_api.get_product_by_id("gold_fut")
    assert spy.call_count == 1


def test_auto_bootstrap_buildable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    db_path = tmp_path / "refdata" / "refdata.db"
    called = False

    def fake_build_refdata(
        *, config: RefDataConfigData, session_manager: SQLSessionManager
    ) -> None:
        _ = config
        _ = session_manager
        nonlocal called
        called = True
        session_manager.init_db()

    monkeypatch.setattr(
        "mxm.refdata.services.bootstrap.build_refdata",
        fake_build_refdata,
    )

    api = RefDataAPI.from_config_data(
        {
            "SQL_DB_URL": f"sqlite:///{db_path}",
            "REFDATA_DB_MODE": "buildable",
        }
    )

    products = api.get_all_products()

    assert products == []
    assert called
    assert db_path.exists()


def test_auto_bootstrap_refused_managed(tmp_path: Path) -> None:
    from mxm.refdata.services.bootstrap import RefDataNotInitialisedError

    db_path = tmp_path / "refdata" / "refdata.db"

    api = RefDataAPI.from_config_data(
        {
            "SQL_DB_URL": f"sqlite:///{db_path}",
            "REFDATA_DB_MODE": "managed",
            "REFDATA_CONTRACT_START_DATE": "2000-01-02",
        }
    )

    with pytest.raises(RefDataNotInitialisedError):
        api.get_all_products()


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
    ref_data_api: RefDataAPI,
) -> None:
    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 1),
        product_id="gold_fut",
    )
    assert [contract.contract_id for contract in contracts] == ["gold_fut.Jan-2025"]

    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 29),
        product_id="gold_fut",
    )
    assert [contract.contract_id for contract in contracts] == ["gold_fut.Jan-2025"]

    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 30),
        product_id="corn_fut",
    )
    assert [contract.contract_id for contract in contracts] == []

    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 15),
        product_id="corn_fut",
    )
    assert [contract.contract_id for contract in contracts] == ["corn_fut.Jan-2025"]


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_product_id_filter(ref_data_api: RefDataAPI) -> None:
    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 15),
        product_id="gold_fut",
    )

    assert all(contract.product_id == "gold_fut" for contract in contracts)
    assert [contract.contract_id for contract in contracts] == ["gold_fut.Jan-2025"]


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_product_ids_filter(ref_data_api: RefDataAPI) -> None:
    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 15),
        product_ids=["gold_fut", "corn_fut"],
    )

    assert [contract.contract_id for contract in contracts] == [
        "corn_fut.Jan-2025",
        "gold_fut.Jan-2025",
    ]


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_empty_product_ids_returns_empty(
    ref_data_api: RefDataAPI,
) -> None:
    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 15),
        product_ids=[],
    )

    assert contracts == []


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_rejects_both_product_id_and_product_ids(
    ref_data_api: RefDataAPI,
) -> None:
    with pytest.raises(ValueError):
        ref_data_api.get_active_contracts(
            date(2025, 1, 15),
            product_id="gold_fut",
            product_ids=["gold_fut"],
        )


@pytest.mark.usefixtures("mock_data_active_contracts")
def test_get_active_contracts_caching_behavior(
    ref_data_api: RefDataAPI,
    mocker: MockerFixture,
) -> None:
    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_active_contracts(date(2025, 1, 15), product_id="gold_fut")
    assert spy.call_count == 1

    ref_data_api.get_active_contracts(date(2025, 1, 15), product_id="gold_fut")
    assert spy.call_count == 1


def test_get_contracts_for_product_orders_by_period(
    ref_data_api: RefDataAPI,
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

    contracts = ref_data_api.get_contracts_for_product("mix_tenor_fut")

    assert [contract.contract_id for contract in contracts] == [
        "mix_tenor_fut.2025",
        "mix_tenor_fut.Jan-2025",
    ]


@pytest.mark.usefixtures("mock_data")
def test_get_contract_by_id_found(ref_data_api: RefDataAPI) -> None:
    contract = ref_data_api.get_contract_by_id("gold_fut.Jan-2025")

    assert contract.contract_id == "gold_fut.Jan-2025"


@pytest.mark.usefixtures("mock_data")
def test_get_contract_by_id_missing(ref_data_api: RefDataAPI) -> None:
    with pytest.raises(RefDataLookupError):
        ref_data_api.get_contract_by_id("does_not_exist")


@pytest.mark.usefixtures("mock_data")
def test_maybe_get_contract_by_id_missing(ref_data_api: RefDataAPI) -> None:
    contract = ref_data_api.maybe_get_contract_by_id("does_not_exist")

    assert contract is None


def test_get_contracts_by_id_preserves_order_and_ignores_missing(
    ref_data_api: RefDataAPI,
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

    contracts = ref_data_api.get_contracts_by_id(
        ["lookup_fut.B", "missing", "lookup_fut.A", "lookup_fut.B"]
    )

    assert [contract.contract_id for contract in contracts] == [
        "lookup_fut.B",
        "lookup_fut.A",
        "lookup_fut.B",
    ]


@pytest.mark.usefixtures("mock_data")
def test_get_contracts_by_id_empty_list_returns_empty(
    ref_data_api: RefDataAPI,
) -> None:
    assert ref_data_api.get_contracts_by_id([]) == []


@pytest.mark.usefixtures("mock_data")
def test_get_contract_by_id_caching_behavior(
    ref_data_api: RefDataAPI,
    mocker: MockerFixture,
) -> None:
    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_contract_by_id("gold_fut.Jan-2025")
    assert spy.call_count == 1

    ref_data_api.get_contract_by_id("gold_fut.Jan-2025")
    assert spy.call_count == 1


def test_get_contracts_by_id_caching_behavior(
    ref_data_api: RefDataAPI,
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

    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_contracts_by_id(["lookup_cache_fut.A"])
    assert spy.call_count == 1

    ref_data_api.get_contracts_by_id(["lookup_cache_fut.A"])
    assert spy.call_count == 1
