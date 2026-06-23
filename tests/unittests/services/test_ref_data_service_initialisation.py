"""Unit tests for RefDataService initialisation methods."""

from __future__ import annotations

from datetime import date

import pytest
from pytest_mock import MockerFixture

from mxm.refdata.config import RefDataConfigData
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.services.ref_data_service import RefDataService


@pytest.fixture(scope="module")
def refdata_config() -> RefDataConfigData:
    """Provide fully materialised refdata config for service tests."""
    return {
        "SQL_DB_URL": "sqlite:///:memory:",
        "REFDATA_DB_MODE": "buildable",
        "REFDATA_FUTURES_PRODUCTS_CSV_PATH": "/tmp/products.csv",
        "REFDATA_CONTRACT_START_DATE": "2000-01-01",
        "REFDATA_CONTRACT_END_DATE": "2045-12-31",
    }


@pytest.fixture(scope="module")
def futures_products() -> list[FuturesProduct]:
    """Provide a test futures product."""
    return [
        FuturesProduct(
            product_id="TEST",
            venue="CME",
            description="Test Product",
            unit=ProductUnit.TROY_OUNCE,
            currency=Currency.USD,
            contract_size=100.0,
            listing_rule="Monthly",
            period_types=(PeriodType.MONTH,),
            settlement=SettlementMethod.PHYSICAL,
            last_trading_rule="3rd last business day of the delivery month",
            expiry_rule="End of Month",
            trading_calendar="CME",
            tick_size=0.1,
            tick_value=10.0,
            valid_period_rule="FGHJKMNQUVXZ",
        )
    ]


@pytest.fixture(scope="module")
def futures_contracts() -> list[FuturesContract]:
    """Provide a test futures contract."""
    return [
        FuturesContract(
            product_id="TEST",
            period_id="Jan-2024",
            contract_id="TEST.Jan-2024",
            contract_size=100.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="CME",
            first_day_of_interest=date(2024, 1, 1),
            last_trading_day=date(2024, 1, 31),
        )
    ]


@pytest.fixture(scope="module")
def db_session_manager() -> SQLSessionManager:
    """Provide an SQLSessionManager using an in-memory SQLite database."""
    session_manager = SQLSessionManager.from_db_url("sqlite:///:memory:")
    session_manager.init_db()
    return session_manager


@pytest.fixture
def ref_data_service(
    refdata_config: RefDataConfigData,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
    futures_products: list[FuturesProduct],
) -> RefDataService:
    """Provide a configured RefDataService instance.

    Product factory construction reads the configured CSV path, so the CSV parser
    is patched before service construction.
    """
    mocker.patch(
        "mxm.refdata.services.futures_product_factory.parse_futures_products_csv",
        return_value=futures_products,
    )

    return RefDataService.from_config_data(
        config=refdata_config,
        session_manager=db_session_manager,
    )


@pytest.fixture(autouse=True)
def reset_db(ref_data_service: RefDataService) -> None:
    """Ensure a clean database state before each test."""
    ref_data_service.reset_database()


def test_from_config_data_constructs_configured_service(
    refdata_config: RefDataConfigData,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
    futures_products: list[FuturesProduct],
) -> None:
    """from_config_data should construct a service from explicit dependencies."""
    mocker.patch(
        "mxm.refdata.services.futures_product_factory.parse_futures_products_csv",
        return_value=futures_products,
    )

    service = RefDataService.from_config_data(
        config=refdata_config,
        session_manager=db_session_manager,
    )

    assert service.config is refdata_config
    assert service.session_manager is db_session_manager
    assert service.product_factory.require("TEST") is futures_products[0]


def test_initialise_periods(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
) -> None:
    """initialise_periods should create periods in the database."""
    ref_data_service.initialise_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    with db_session_manager.db_session_scope() as session:
        periods = session.query(PeriodORM).all()
        period_data = [(p.period_id, p.period_type) for p in periods]

    assert len(period_data) > 0
    assert any(ptype == PeriodType.MONTH for _, ptype in period_data)


def test_initialise_period_cycles(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
) -> None:
    """initialise_period_cycles should create canonical cycle definitions."""
    ref_data_service.initialise_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    ref_data_service.initialise_period_cycles()

    with db_session_manager.db_session_scope() as session:
        cycles = session.query(PeriodCycleORM).all()
        memberships = session.query(PeriodCycleMembershipORM).all()

    assert len(cycles) == 2
    assert len(memberships) > 0


def test_initialise_futures_products(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
) -> None:
    """initialise_futures_products should store configured futures products."""
    ref_data_service.initialise_futures_products()

    with db_session_manager.db_session_scope() as session:
        products = session.query(FuturesProductORM).all()
        product_data = [(p.product_id, p.description) for p in products]

    assert product_data == [("TEST", "Test Product")]


def test_initialise_futures_contracts(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
    futures_contracts: list[FuturesContract],
    mocker: MockerFixture,
) -> None:
    """initialise_futures_contracts should store generated futures contracts."""
    ref_data_service.initialise_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    ref_data_service.initialise_futures_products()

    mocker.patch.object(
        ref_data_service.contract_factory,
        "create_contracts_for_product",
        return_value=futures_contracts,
    )

    ref_data_service.initialise_futures_contracts(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    with db_session_manager.db_session_scope() as session:
        contracts = session.query(FuturesContractORM).all()
        contract_data = [(c.contract_id, c.product_id, c.period_id) for c in contracts]

    assert contract_data == [("TEST.Jan-2024", "TEST", "Jan-2024")]


def test_setup_instruments(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
    futures_contracts: list[FuturesContract],
    mocker: MockerFixture,
) -> None:
    """setup_instruments should initialise all instrument entities in sequence."""
    mocker.patch.object(
        ref_data_service.contract_factory,
        "create_contracts_for_product",
        return_value=futures_contracts,
    )

    ref_data_service.setup_instruments(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    with db_session_manager.db_session_scope() as session:
        periods_count = session.query(PeriodORM).count()
        product_data = [
            (p.product_id, p.description)
            for p in session.query(FuturesProductORM).all()
        ]
        contract_data = [
            (c.contract_id, c.product_id, c.period_id)
            for c in session.query(FuturesContractORM).all()
        ]

    assert periods_count > 0
    assert product_data == [("TEST", "Test Product")]
    assert contract_data == [("TEST.Jan-2024", "TEST", "Jan-2024")]


def test_setup_instruments_uses_configured_default_dates(
    ref_data_service: RefDataService,
    mocker: MockerFixture,
    futures_contracts: list[FuturesContract],
) -> None:
    """setup_instruments should use configured date defaults when dates are omitted."""
    initialise_periods = mocker.patch.object(ref_data_service, "initialise_periods")
    initialise_period_cycles = mocker.patch.object(
        ref_data_service,
        "initialise_period_cycles",
    )
    initialise_futures_products = mocker.patch.object(
        ref_data_service,
        "initialise_futures_products",
    )
    initialise_futures_contracts = mocker.patch.object(
        ref_data_service,
        "initialise_futures_contracts",
        return_value=futures_contracts,
    )

    ref_data_service.setup_instruments()

    initialise_periods.assert_called_once_with(
        start_date=date(2000, 1, 1),
        end_date=date(2045, 12, 31),
    )
    initialise_period_cycles.assert_called_once_with()
    initialise_futures_products.assert_called_once_with(csv_file_path=None)
    initialise_futures_contracts.assert_called_once_with(
        start_date=date(2000, 1, 1),
        end_date=date(2045, 12, 31),
    )


def test_reset_database(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
) -> None:
    """reset_database should fully clear managed tables."""
    ref_data_service.reset_database()

    with db_session_manager.db_session_scope() as session:
        periods_count = session.query(PeriodORM).count()
        products_count = session.query(FuturesProductORM).count()
        contracts_count = session.query(FuturesContractORM).count()

    assert periods_count == 0
    assert products_count == 0
    assert contracts_count == 0
