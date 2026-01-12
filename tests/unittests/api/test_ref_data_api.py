"""Focused unit tests for RefDataAPI (ensuring query correctness & caching)."""

from datetime import date

import pytest
from sqlalchemy import create_engine

from mxm_refdata.api.ref_data_api import RefDataAPI
from mxm_refdata.database.sql_session_manager import SQLSessionManager
from mxm_refdata.mappings.orm_converter import obj_to_orm
from mxm_refdata.models.contracts.futures_contract import FuturesContract
from mxm_refdata.models.periods import Period
from mxm_refdata.models.products.futures_product import FuturesProduct


@pytest.fixture(scope="module")
def db_session_manager():
    """Provides an instance of SQLSessionManager using an in-memory SQLite database."""
    test_engine = create_engine("sqlite:///:memory:")  # In-memory DB for unit tests
    session_manager = SQLSessionManager(engine=test_engine)
    session_manager.init_db()
    return session_manager


@pytest.fixture(autouse=True)
def reset_db(db_session_manager):
    """Ensure a clean database state before each test."""
    db_session_manager.drop_db()
    db_session_manager.init_db()


@pytest.fixture
def ref_data_api(db_session_manager, monkeypatch):
    """
    Fixture to create an instance of RefDataAPI for unit tests.

    These unit tests focus on query correctness & caching. We explicitly disable
    auto-bootstrap/initialisation here to avoid altering DB state and to keep the
    caching assertions stable and meaningful.
    """
    # Patch the bootstrap hook used inside RefDataAPI methods (if present)
    # This patch is intentionally scoped to tests using this fixture.
    monkeypatch.setattr(
        "mxm_refdata.api.ref_data_api.ensure_refdata_ready",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    return RefDataAPI(session_manager=db_session_manager)


@pytest.fixture
def mock_data(db_session_manager):
    """Pre-populates the database with business model objects, ensuring conversion is tested."""
    with db_session_manager.db_session_scope() as session:
        product = FuturesProduct(
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
            tick_size=0.1,
            tick_value=10.0,
        )
        session.add(obj_to_orm(product))

        period = Period(
            period_id="Jan-2025",
            period_type="MONTH",
            first_date=date(2025, 1, 1),
            last_date=date(2025, 1, 31),
        )
        session.add(obj_to_orm(period))

        contract = FuturesContract(
            product_id="gold_fut",
            period_id="Jan-2025",
            contract_id="gold_fut.Jan-2025",
            contract_size=100.0,
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        session.add(obj_to_orm(contract))


def test_get_product_by_id(ref_data_api, mock_data):
    """Test retrieving a product by ID."""
    product = ref_data_api.get_product_by_id("gold_fut")
    assert product is not None, "Expected product to be found."
    assert product.product_id == "gold_fut", "Product ID mismatch."


def test_get_contracts_for_date(ref_data_api, mock_data):
    """Test retrieving contracts active during their delivery period."""
    contracts = ref_data_api.get_contracts_for_date(date(2025, 1, 15))
    assert len(contracts) == 1, "Expected 1 active contract on this date."
    assert contracts[0].contract_id == "gold_fut.Jan-2025", "Contract ID mismatch."


def test_caching_behavior(ref_data_api, mock_data, mocker):
    """Test that caching prevents redundant DB queries."""
    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    # First query hits the DB
    ref_data_api.get_product_by_id("gold_fut")
    assert spy.call_count == 1, "Expected a database call on first query."

    # Second query should use cache (no additional db_session_scope calls)
    ref_data_api.get_product_by_id("gold_fut")
    assert spy.call_count == 1, "Expected cached data, no additional DB calls."


# -------------------------------------------------------------------------
# Bootstrap/mode behaviour tests (separate from unit query/caching tests)
# -------------------------------------------------------------------------


def test_auto_bootstrap_buildable(tmp_path, monkeypatch):
    """
    In buildable mode, RefDataAPI should materialise the refdata DB on first use
    when it is missing/empty.
    """
    db_path = tmp_path / "refdata" / "refdata.db"
    monkeypatch.setenv("SQL_DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("REFDATA_DB_MODE", "buildable")

    api = RefDataAPI()
    products = api.get_all_products()

    assert products, "Expected non-empty product list after auto-bootstrap."
    assert db_path.exists(), "Expected SQLite DB file to be created."


def test_auto_bootstrap_refused_managed(tmp_path, monkeypatch):
    """
    In managed mode, RefDataAPI must refuse to auto-create an empty/missing DB.
    """
    db_path = tmp_path / "refdata" / "refdata.db"
    monkeypatch.setenv("SQL_DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("REFDATA_DB_MODE", "managed")

    # Import here to avoid coupling unit tests to bootstrap internals unless needed
    from mxm_refdata.services.bootstrap import RefDataNotInitialisedError

    api = RefDataAPI()
    with pytest.raises(RefDataNotInitialisedError):
        api.get_all_products()
