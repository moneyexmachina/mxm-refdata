"""Unit tests for RefDataService initialization methods."""

from datetime import date

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import create_engine

from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.services.ref_data_service import RefDataService


@pytest.fixture(scope="module")
def futures_products():
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
            trading_calendar="Default Calendar",
            tick_size=0.1,
            tick_value=10.0,
            valid_period_rule="FGHJKMNQUVXZ",
        )
    ]


@pytest.fixture(scope="module")
def futures_contracts():
    return [
        FuturesContract(
            product_id="TEST",
            period_id="Jan-2024",
            contract_id="TEST.Jan-2024",
            contract_size=100.0,
            currency=Currency.USD,
            unit=ProductUnit.TROY_OUNCE,
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2024, 1, 1),
            last_trading_day=date(2024, 1, 31),
        )
    ]


@pytest.fixture(scope="module")
def db_session_manager():
    """Provide an instance of SQLSessionManager using an in-memory SQLite database."""
    test_engine = create_engine("sqlite:///:memory:")
    session_manager = SQLSessionManager(engine=test_engine)
    session_manager.init_db()
    return session_manager


@pytest.fixture
def ref_data_service(db_session_manager: SQLSessionManager):
    """Fixture to create an instance of RefDataService."""
    return RefDataService(session_manager=db_session_manager)


@pytest.fixture(autouse=True)
def reset_db(ref_data_service: RefDataService):
    """Ensure a clean database state before each test."""
    ref_data_service.reset_database()


def test_initialise_periods(
    ref_data_service: RefDataService, db_session_manager: SQLSessionManager
):
    """Test that periods are correctly initialized and stored in the database."""
    ref_data_service.initialise_periods(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )

    with db_session_manager.db_session_scope() as session:
        periods = session.query(PeriodORM).all()
        period_data = [(p.period_id, p.period_type) for p in periods]

    assert len(period_data) > 0, "Expected periods to be initialized in the database."
    assert any(ptype == PeriodType.MONTH for _, ptype in period_data), (
        "Expected monthly periods."
    )


def test_initialise_futures_products(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
    futures_products: list[FuturesProduct],
):
    """Test that futures products are correctly loaded from a CSV file."""
    mocker.patch(
        "mxm.refdata.services.futures_product_factory.FuturesProductFactory.initialise_from_csv",
        return_value=futures_products,
    )

    ref_data_service.initialise_futures_products()

    with db_session_manager.db_session_scope() as session:
        products = session.query(FuturesProductORM).all()
        product_data = [(p.product_id, p.description) for p in products]

    assert len(product_data) == 1, "Expected 1 product in the database."
    assert product_data[0][0] == "TEST", "Expected product ID to match CSV mock."


def test_initialise_futures_contracts(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
    futures_products: list[FuturesProduct],
    futures_contracts: list[FuturesContract],
):
    """Test that futures contracts are correctly generated based on existing products and periods."""
    ref_data_service.initialise_periods(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )

    mocker.patch(
        "mxm.refdata.services.futures_product_factory.FuturesProductFactory.initialise_from_csv",
        return_value=futures_products,
    )
    ref_data_service.initialise_futures_products()

    mocker.patch(
        "mxm.refdata.services.futures_contract_factory.FuturesContractFactory.create_contracts_for_product",
        return_value=futures_contracts,
    )

    ref_data_service.initialise_futures_contracts(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )

    with db_session_manager.db_session_scope() as session:
        contracts = session.query(FuturesContractORM).all()
        contract_data = [(c.contract_id, c.product_id, c.period_id) for c in contracts]

    assert len(contract_data) == 1, "Expected 1 contract to be generated."
    assert contract_data[0][0] == "TEST.Jan-2024", "Expected contract ID to match mock."


def test_setup_instruments(
    ref_data_service: RefDataService,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
    futures_products: list[FuturesProduct],
    futures_contracts: list[FuturesContract],
):
    """Test that setup_instruments correctly initializes all entities in sequence."""
    mocker.patch(
        "mxm.refdata.services.futures_product_factory.FuturesProductFactory.initialise_from_csv",
        return_value=futures_products,
    )

    mocker.patch(
        "mxm.refdata.services.futures_contract_factory.FuturesContractFactory.create_contracts_for_product",
        return_value=futures_contracts,
    )

    ref_data_service.setup_instruments(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )

    with db_session_manager.db_session_scope() as session:
        periods = session.query(PeriodORM).all()
        period_data = [(p.period_id, p.period_type) for p in periods]

        products = session.query(FuturesProductORM).all()
        product_data = [(p.product_id, p.description) for p in products]

        contracts = session.query(FuturesContractORM).all()
        contract_data = [(c.contract_id, c.product_id, c.period_id) for c in contracts]

    assert len(period_data) > 0, "Expected periods to be initialized."
    assert len(product_data) == 1, "Expected 1 product in the database."
    assert len(contract_data) == 1, "Expected 1 contract in the database."
    assert contract_data[0][0] == "TEST.Jan-2024", "Expected contract ID to match mock."


def test_reset_database(
    ref_data_service: RefDataService, db_session_manager: SQLSessionManager
):
    """Test that reset_database fully clears all tables."""
    ref_data_service.reset_database()

    with db_session_manager.db_session_scope() as session:
        periods_count = session.query(PeriodORM).count()
        products_count = session.query(FuturesProductORM).count()
        contracts_count = session.query(FuturesContractORM).count()

    assert periods_count == 0, "Expected periods table to be empty after reset."
    assert products_count == 0, "Expected products table to be empty after reset."
    assert contracts_count == 0, "Expected contracts table to be empty after reset."
