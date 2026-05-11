"""Focused unit tests for RefDataAPI (ensuring query correctness & caching)."""

from datetime import date

import pytest
from pytest import MonkeyPatch
from pytest_mock import MockerFixture
from sqlalchemy import create_engine

from mxm.refdata.api.ref_data_api import RefDataAPI
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
def db_session_manager():
    """Provides an instance of SQLSessionManager using an in-memory SQLite database."""
    test_engine = create_engine("sqlite:///:memory:")  # In-memory DB for unit tests
    session_manager = SQLSessionManager(engine=test_engine)
    session_manager.init_db()
    return session_manager


@pytest.fixture(autouse=True)
def reset_db(db_session_manager: SQLSessionManager):
    """Ensure a clean database state before each test."""
    db_session_manager.drop_db()
    db_session_manager.init_db()


@pytest.fixture
def ref_data_api(db_session_manager: SQLSessionManager, monkeypatch: MonkeyPatch):
    """
    Fixture to create an instance of RefDataAPI for unit tests.

    These unit tests focus on query correctness & caching. We explicitly disable
    auto-bootstrap/initialisation here to avoid altering DB state and to keep the
    caching assertions stable and meaningful.
    """
    # Patch the bootstrap hook used inside RefDataAPI methods (if present)
    # This patch is intentionally scoped to tests using this fixture.
    monkeypatch.setattr(
        "mxm.refdata.api.ref_data_api.ensure_refdata_ready",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    return RefDataAPI(session_manager=db_session_manager)


@pytest.fixture
def mock_data(db_session_manager: SQLSessionManager):
    """Pre-populates the database with business model objects, ensuring conversion is tested."""
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
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        session.add(futures_contract_to_orm(contract))


def test_get_product_by_id(ref_data_api: RefDataAPI, mock_data):
    """Test retrieving a product by ID."""
    product = ref_data_api.get_product_by_id("gold_fut")
    assert product is not None, "Expected product to be found."
    assert product.product_id == "gold_fut", "Product ID mismatch."


def test_get_contracts_for_date(ref_data_api: RefDataAPI, mock_data):
    """Test retrieving contracts active during their delivery period."""
    contracts = ref_data_api.get_contracts_for_date(date(2025, 1, 15))
    assert len(contracts) == 1, "Expected 1 active contract on this date."
    assert contracts[0].contract_id == "gold_fut.Jan-2025", "Contract ID mismatch."


def test_caching_behavior(ref_data_api: RefDataAPI, mock_data, mocker: MockerFixture):
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
    from mxm.refdata.services.bootstrap import RefDataNotInitialisedError

    api = RefDataAPI()
    with pytest.raises(RefDataNotInitialisedError):
        api.get_all_products()


# -------------------------------------------------------------------------
# New tests for RefDataAPI.get_active_contracts (Session 6 additions)
# -------------------------------------------------------------------------


@pytest.fixture
def mock_data_active_contracts(db_session_manager: SQLSessionManager):
    """
    Pre-populates the database with:
      - 2 products
      - 2 periods
      - 4 contracts with distinct [first_day_of_interest, last_trading_day] windows
    This allows boundary + filtering tests for get_active_contracts.
    """
    with db_session_manager.db_session_scope() as session:
        # Products
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

        # Periods (only required if your schema enforces FK; harmless otherwise)
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

        # Contracts (Gold)
        # Active window: [2025-01-01, 2025-01-29]
        gold_jan = FuturesContract(
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
        # Active window: [2025-01-30, 2025-02-26]
        gold_feb = FuturesContract(
            product_id="gold_fut",
            period_id="Feb-2025",
            contract_id="gold_fut.Feb-2025",
            contract_size=100.0,
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 30),
            last_trading_day=date(2025, 2, 26),
        )

        # Contracts (Corn)
        # Active window: [2025-01-10, 2025-01-20]
        corn_jan = FuturesContract(
            product_id="corn_fut",
            period_id="Jan-2025",
            contract_id="corn_fut.Jan-2025",
            contract_size=5000.0,
            currency="USD",
            unit="BUSHEL",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 10),
            last_trading_day=date(2025, 1, 20),
        )
        # Active window: [2025-02-01, 2025-02-10]
        corn_feb = FuturesContract(
            product_id="corn_fut",
            period_id="Feb-2025",
            contract_id="corn_fut.Feb-2025",
            contract_size=5000.0,
            currency="USD",
            unit="BUSHEL",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 2, 1),
            last_trading_day=date(2025, 2, 10),
        )

        session.add(futures_contract_to_orm(gold_jan))
        session.add(futures_contract_to_orm(gold_feb))
        session.add(futures_contract_to_orm(corn_jan))
        session.add(futures_contract_to_orm(corn_feb))


def test_get_active_contracts_semantics_and_boundaries(
    ref_data_api: RefDataAPI, mock_data_active_contracts
):
    """
    Active is defined as: first_day_of_interest <= as_of_date <= last_trading_day.
    Verify inside-window and boundary inclusion, plus outside-window exclusion.
    """
    # Boundary inclusion for gold_jan
    c = ref_data_api.get_active_contracts(date(2025, 1, 1), product_id="gold_fut")
    assert [x.contract_id for x in c] == ["gold_fut.Jan-2025"]

    c = ref_data_api.get_active_contracts(date(2025, 1, 29), product_id="gold_fut")
    assert [x.contract_id for x in c] == ["gold_fut.Jan-2025"]

    # Outside window exclusion
    c = ref_data_api.get_active_contracts(date(2025, 1, 30), product_id="corn_fut")
    assert [
        x.contract_id for x in c
    ] == []  # corn_jan ended 2025-01-20, corn_feb starts 2025-02-01

    # Inside window for corn_jan
    c = ref_data_api.get_active_contracts(date(2025, 1, 15), product_id="corn_fut")
    assert [x.contract_id for x in c] == ["corn_fut.Jan-2025"]


def test_get_active_contracts_product_id_filter(
    ref_data_api: RefDataAPI, mock_data_active_contracts
):
    """Restricting by product_id should only return contracts from that product."""
    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 15), product_id="gold_fut"
    )
    assert all(c.product_id == "gold_fut" for c in contracts)
    assert [c.contract_id for c in contracts] == ["gold_fut.Jan-2025"]


def test_get_active_contracts_product_ids_filter(
    ref_data_api: RefDataAPI, mock_data_active_contracts
):
    """Restricting by product_ids should return active contracts across those products."""
    contracts = ref_data_api.get_active_contracts(
        date(2025, 1, 15),
        product_ids=["gold_fut", "corn_fut"],
    )
    # At 2025-01-15: gold_jan and corn_jan should both be active.
    assert [c.contract_id for c in contracts] == [
        "corn_fut.Jan-2025",
        "gold_fut.Jan-2025",
    ]


def test_get_active_contracts_empty_product_ids_returns_empty(
    ref_data_api: RefDataAPI, mock_data_active_contracts
):
    """An explicitly empty product_ids list should return an empty list."""
    contracts = ref_data_api.get_active_contracts(date(2025, 1, 15), product_ids=[])
    assert contracts == []


def test_get_active_contracts_rejects_both_product_id_and_product_ids(
    ref_data_api: RefDataAPI, mock_data_active_contracts
):
    """Providing both product_id and product_ids must raise ValueError."""
    with pytest.raises(ValueError):
        ref_data_api.get_active_contracts(
            date(2025, 1, 15),
            product_id="gold_fut",
            product_ids=["gold_fut"],
        )


def test_get_active_contracts_caching_behavior(
    ref_data_api: RefDataAPI, mock_data_active_contracts, mocker: MockerFixture
):
    """Caching should prevent redundant DB queries for identical get_active_contracts calls."""
    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_active_contracts(date(2025, 1, 15), product_id="gold_fut")
    assert spy.call_count == 1, "Expected a database call on first query."

    ref_data_api.get_active_contracts(date(2025, 1, 15), product_id="gold_fut")
    assert spy.call_count == 1, "Expected cached data, no additional DB calls."


def test_get_contracts_for_product_orders_by_period(
    ref_data_api: RefDataAPI,
    db_session_manager: SQLSessionManager,
):
    """
    get_contracts_for_product should return contracts ordered by Period, using the
    Period.__lt__ semantics (PERIOD_PRIORITY then first_date), with contract_id as
    a deterministic tie-breaker.

    This test uses mixed PeriodTypes (YEAR before MONTH) and non-overlapping dates
    to make the expected order unambiguous.
    """
    with db_session_manager.db_session_scope() as session:
        # Product
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

        # Periods: YEAR should sort before MONTH per PERIOD_PRIORITY
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

        # Contracts referencing those periods (inserted in reverse order intentionally)
        c_month = FuturesContract(
            product_id="mix_tenor_fut",
            period_id="Jan-2025",
            contract_id="mix_tenor_fut.Jan-2025",
            contract_size=1.0,
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2024, 12, 1),
            last_trading_day=date(2025, 1, 30),
        )
        c_year = FuturesContract(
            product_id="mix_tenor_fut",
            period_id="2025",
            contract_id="mix_tenor_fut.2025",
            contract_size=1.0,
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2024, 1, 1),
            last_trading_day=date(2025, 12, 15),
        )
        session.add(futures_contract_to_orm(c_month))
        session.add(futures_contract_to_orm(c_year))

    contracts = ref_data_api.get_contracts_for_product("mix_tenor_fut")
    assert [c.contract_id for c in contracts] == [
        "mix_tenor_fut.2025",
        "mix_tenor_fut.Jan-2025",
    ]


def test_get_contract_by_id_found(ref_data_api: RefDataAPI, mock_data):
    """get_contract_by_id should return the contract when it exists."""
    contract = ref_data_api.get_contract_by_id("gold_fut.Jan-2025")
    assert contract is not None, "Expected contract to be found."
    assert contract.contract_id == "gold_fut.Jan-2025", "Contract ID mismatch."


def test_get_contract_by_id_missing(ref_data_api: RefDataAPI, mock_data):
    """get_contract_by_id should return None when the contract does not exist."""
    contract = ref_data_api.get_contract_by_id("does_not_exist")
    assert contract is None, "Expected None for missing contract."


def test_get_contracts_by_id_preserves_order_and_ignores_missing(
    ref_data_api: RefDataAPI,
    db_session_manager: SQLSessionManager,
):
    """
    get_contracts_by_id should:
      - return only found contracts
      - preserve the input order
      - ignore missing ids
    """
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
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        c2 = FuturesContract(
            product_id="lookup_fut",
            period_id="Jan-2025",
            contract_id="lookup_fut.B",
            contract_size=1.0,
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 2),
            last_trading_day=date(2025, 1, 30),
        )
        session.add(futures_contract_to_orm(c1))
        session.add(futures_contract_to_orm(c2))

    contracts = ref_data_api.get_contracts_by_id(
        ["lookup_fut.B", "missing", "lookup_fut.A", "lookup_fut.B"]
    )
    assert [c.contract_id for c in contracts] == [
        "lookup_fut.B",
        "lookup_fut.A",
        "lookup_fut.B",
    ]


def test_get_contracts_by_id_empty_list_returns_empty(
    ref_data_api: RefDataAPI, mock_data
):
    """get_contracts_by_id should return [] when given an empty input list."""
    assert ref_data_api.get_contracts_by_id([]) == []


def test_get_contract_by_id_caching_behavior(
    ref_data_api: RefDataAPI,
    mock_data,
    mocker: MockerFixture,
):
    """Caching should prevent redundant DB queries for identical get_contract_by_id calls."""
    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_contract_by_id("gold_fut.Jan-2025")
    assert spy.call_count == 1, "Expected a database call on first query."

    ref_data_api.get_contract_by_id("gold_fut.Jan-2025")
    assert spy.call_count == 1, "Expected cached data, no additional DB calls."


def test_get_contracts_by_id_caching_behavior(
    ref_data_api: RefDataAPI,
    db_session_manager: SQLSessionManager,
    mocker: MockerFixture,
):
    """Caching should prevent redundant DB queries for identical get_contracts_by_id calls."""
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

        c1 = FuturesContract(
            product_id="lookup_cache_fut",
            period_id="Jan-2025",
            contract_id="lookup_cache_fut.A",
            contract_size=1.0,
            currency="USD",
            unit="TROY_OUNCE",
            trading_calendar="Default Calendar",
            first_day_of_interest=date(2025, 1, 1),
            last_trading_day=date(2025, 1, 29),
        )
        session.add(futures_contract_to_orm(c1))

    spy = mocker.spy(ref_data_api.session_manager, "db_session_scope")

    ref_data_api.get_contracts_by_id(["lookup_cache_fut.A"])
    assert spy.call_count == 1, "Expected a database call on first query."

    ref_data_api.get_contracts_by_id(["lookup_cache_fut.A"])
    assert spy.call_count == 1, "Expected cached data, no additional DB calls."
