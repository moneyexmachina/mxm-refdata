"""Tests for refdata materialisation routines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import cast

import pytest
from pytest import MonkeyPatch
from pytest_mock import MockerFixture

from mxm.config import MXMConfig
from mxm.refdata import materialisation
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.factories import (
    FuturesContractFactory,
    FuturesProductFactory,
    PeriodFactory,
)
from mxm.refdata.materialisation import RefDataNotInitialisedError
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
from mxm.refdata.models.products.futures_product_spec import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProductProvenance,
    FuturesProductSourceStatus,
    FuturesProductSpec,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit


@pytest.fixture
def futures_product_specs(
    futures_products: list[FuturesProduct],
) -> list[FuturesProductSpec]:
    """Provide complete specifications for the test futures products."""

    return [
        FuturesProductSpec(
            schema_version="futures_product.v1",
            product_id=product.product_id,
            asset_class="futures",
            source_status=FuturesProductSourceStatus(
                created_at=date(2026, 7, 13),
                updated_at=date(2026, 7, 13),
                review_status="draft",
                curator="mxm",
            ),
            provenance=FuturesProductProvenance(
                source_type="test_fixture",
                source_url="https://example.com/test-product",
                source_accessed_at=date(2026, 7, 13),
                curation_method="test_fixture",
                assistance="none",
                notes=(),
            ),
            product=product,
            contract_rules=ContractRules(
                last_trading_rule=LastTradingRule(
                    period_offset=0,
                    reference_event=(ReferenceEvent.BUSINESS_DAY_OF_PERIOD),
                    n_reference=-3,
                    business_day_offset=0,
                ),
                first_day_of_interest_rule=FirstDayOfInterestRule(
                    shift_rule=FirstDayOfInterestShiftRule(
                        shift_period_type=PeriodType.MONTH,
                        n_shift={
                            "Jan": 24,
                            "Feb": 24,
                            "Mar": 24,
                            "Apr": 24,
                            "May": 24,
                            "Jun": 24,
                            "Jul": 24,
                            "Aug": 24,
                            "Sep": 24,
                            "Oct": 24,
                            "Nov": 24,
                            "Dec": 24,
                        },
                    ),
                    reference_rule="next_b_day_after_period",
                ),
            ),
        )
        for product in futures_products
    ]


@dataclass
class RefDataFixture:
    """Minimal refdata runtime object for materialisation tests."""

    config: MXMConfig
    session_manager: SQLSessionManager
    product_factory: FuturesProductFactory
    contract_factory: FuturesContractFactory
    period_factory: PeriodFactory


@pytest.fixture(scope="module")
def refdata_config() -> MXMConfig:
    """Provide fully materialised refdata config for tests."""
    return cast(
        MXMConfig,
        {
            "SQL_DB_URL": "sqlite:///:memory:",
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
            "REFDATA_CONTRACT_START_DATE": "2000-01-01",
            "REFDATA_CONTRACT_END_DATE": "2045-12-31",
        },
    )


@pytest.fixture(scope="module")
def futures_products() -> list[FuturesProduct]:
    """Provide test futures products."""
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
    """Provide test futures contracts."""
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
def session_manager() -> SQLSessionManager:
    """Provide an in-memory SQLite SQLSessionManager."""
    manager = SQLSessionManager.from_db_url("sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def refdata(
    refdata_config: MXMConfig,
    session_manager: SQLSessionManager,
    mocker: MockerFixture,
    futures_product_specs: list[FuturesProductSpec],
) -> RefDataFixture:
    """Provide a minimal refdata runtime fixture."""

    mocker.patch(
        ("mxm.refdata.factories.futures_product_factory.parse_futures_product_specs"),
        return_value=futures_product_specs,
    )

    return RefDataFixture(
        config=refdata_config,
        session_manager=session_manager,
        product_factory=FuturesProductFactory.from_config(refdata_config),
        contract_factory=FuturesContractFactory.from_config(refdata_config),
        period_factory=PeriodFactory(),
    )


@pytest.fixture(autouse=True)
def reset_db(refdata: RefDataFixture) -> None:
    """Ensure a clean database state before each test."""
    refdata.session_manager.drop_db()
    refdata.session_manager.init_db()


def test_build_refdata_initialises_schema_and_sets_up_instruments(
    refdata: RefDataFixture,
    mocker: MockerFixture,
    futures_contracts: list[FuturesContract],
) -> None:
    """build_refdata should initialise schema and populate instruments."""
    mocker.patch.object(
        refdata.contract_factory,
        "create_contracts_for_product",
        return_value=futures_contracts,
    )

    materialisation.build_refdata(refdata)

    with refdata.session_manager.db_session_scope() as session:
        assert session.query(PeriodORM).count() > 0
        assert session.query(FuturesProductORM).count() == 1
        assert session.query(FuturesContractORM).count() == 1


def test_rebuild_refdata_resets_database_then_sets_up_instruments(
    refdata: RefDataFixture,
    mocker: MockerFixture,
    futures_contracts: list[FuturesContract],
) -> None:
    """rebuild_refdata should destructively reset and repopulate instruments."""
    with refdata.session_manager.db_session_scope() as session:
        session.add(
            FuturesProductORM(
                product_id="OLD",
                venue="CME",
                description="Old Product",
                currency="USD",
                unit="TROY_OUNCE",
                contract_size=1.0,
                listing_rule="Monthly",
                period_types="MONTH",
                settlement="PHYSICAL",
                last_trading_rule="",
                expiry_rule="",
                trading_calendar="CME",
                tick_size=0.1,
                tick_value=1.0,
                valid_period_rule="FGHJKMNQUVXZ",
            )
        )

    mocker.patch.object(
        refdata.contract_factory,
        "create_contracts_for_product",
        return_value=futures_contracts,
    )

    materialisation.rebuild_refdata(refdata)

    with refdata.session_manager.db_session_scope() as session:
        product_ids = [p.product_id for p in session.query(FuturesProductORM).all()]
        assert product_ids == ["TEST"]
        assert session.query(FuturesContractORM).count() == 1


def _db_has_products(_: SQLSessionManager) -> bool:
    return True


def _db_has_no_products(_: SQLSessionManager) -> bool:
    return False


def test_ensure_refdata_ready_noops_when_products_exist(
    refdata: RefDataFixture,
    mocker: MockerFixture,
    monkeypatch: MonkeyPatch,
) -> None:
    """ensure_refdata_ready should do nothing when refdata is already populated."""
    monkeypatch.setattr(materialisation, "db_has_any_products", _db_has_products)
    build = mocker.patch.object(materialisation, "build_refdata")
    materialisation.ensure_refdata_ready(refdata)
    build.assert_not_called()


def _with_refdata_db_mode(refdata: RefDataFixture, db_mode: str) -> RefDataFixture:
    """Return a copy of the fixture with a different refdata DB mode."""
    config = cast(
        MXMConfig,
        {
            "SQL_DB_URL": refdata.config["SQL_DB_URL"],
            "REFDATA_DB_MODE": db_mode,
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": refdata.config[
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT"
            ],
            "REFDATA_CONTRACT_START_DATE": refdata.config[
                "REFDATA_CONTRACT_START_DATE"
            ],
            "REFDATA_CONTRACT_END_DATE": refdata.config["REFDATA_CONTRACT_END_DATE"],
        },
    )

    return RefDataFixture(
        config=config,
        session_manager=refdata.session_manager,
        product_factory=refdata.product_factory,
        contract_factory=refdata.contract_factory,
        period_factory=refdata.period_factory,
    )


def test_ensure_refdata_ready_raises_in_managed_mode_when_empty(
    refdata: RefDataFixture,
    monkeypatch: MonkeyPatch,
) -> None:
    """ensure_refdata_ready should raise when DB is empty and mode is managed."""
    monkeypatch.setattr(materialisation, "db_has_any_products", _db_has_no_products)
    managed_refdata = _with_refdata_db_mode(refdata, "managed")

    with pytest.raises(RefDataNotInitialisedError):
        materialisation.ensure_refdata_ready(managed_refdata)


def test_ensure_refdata_ready_builds_when_empty_and_buildable(
    refdata: RefDataFixture,
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """ensure_refdata_ready should build refdata when DB is empty and buildable."""
    monkeypatch.setattr(materialisation, "db_has_any_products", _db_has_no_products)
    build = mocker.patch.object(materialisation, "build_refdata")

    materialisation.ensure_refdata_ready(refdata)

    build.assert_called_once_with(refdata)


def test_initialise_periods(refdata: RefDataFixture) -> None:
    """initialise_periods should create periods in the database."""
    materialisation.initialise_periods(
        refdata,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    with refdata.session_manager.db_session_scope() as session:
        periods = session.query(PeriodORM).all()
        period_data = [(p.period_id, p.period_type) for p in periods]

    assert len(period_data) > 0
    assert any(period_type == PeriodType.MONTH for _, period_type in period_data)


def test_initialise_period_cycles(refdata: RefDataFixture) -> None:
    """initialise_period_cycles should create canonical cycle definitions."""
    materialisation.initialise_periods(
        refdata,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    materialisation.initialise_period_cycles(refdata)

    with refdata.session_manager.db_session_scope() as session:
        cycles = session.query(PeriodCycleORM).all()
        memberships = session.query(PeriodCycleMembershipORM).all()

    assert len(cycles) == 2
    assert len(memberships) > 0


def test_initialise_futures_products(refdata: RefDataFixture) -> None:
    """initialise_futures_products should store configured futures products."""
    materialisation.initialise_futures_products(refdata)

    with refdata.session_manager.db_session_scope() as session:
        products = session.query(FuturesProductORM).all()
        product_data = [(p.product_id, p.description) for p in products]

    assert product_data == [("TEST", "Test Product")]


def test_initialise_futures_contracts(
    refdata: RefDataFixture,
    futures_contracts: list[FuturesContract],
    mocker: MockerFixture,
) -> None:
    """initialise_futures_contracts should store generated futures contracts."""
    materialisation.initialise_periods(
        refdata,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    materialisation.initialise_futures_products(refdata)

    mocker.patch.object(
        refdata.contract_factory,
        "create_contracts_for_product",
        return_value=futures_contracts,
    )

    materialisation.initialise_futures_contracts(
        refdata,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    with refdata.session_manager.db_session_scope() as session:
        contracts = session.query(FuturesContractORM).all()
        contract_data = [(c.contract_id, c.product_id, c.period_id) for c in contracts]

    assert contract_data == [("TEST.Jan-2024", "TEST", "Jan-2024")]


def test_setup_instruments(
    refdata: RefDataFixture,
    futures_contracts: list[FuturesContract],
    mocker: MockerFixture,
) -> None:
    """setup_instruments should initialise all instrument entities in sequence."""
    mocker.patch.object(
        refdata.contract_factory,
        "create_contracts_for_product",
        return_value=futures_contracts,
    )

    materialisation.setup_instruments(
        refdata,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    with refdata.session_manager.db_session_scope() as session:
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
    refdata: RefDataFixture,
    mocker: MockerFixture,
) -> None:
    """setup_instruments should use configured date defaults when dates are omitted."""
    initialise_periods = mocker.patch.object(materialisation, "initialise_periods")
    initialise_period_cycles = mocker.patch.object(
        materialisation,
        "initialise_period_cycles",
    )
    initialise_futures_products = mocker.patch.object(
        materialisation,
        "initialise_futures_products",
    )
    initialise_futures_contracts = mocker.patch.object(
        materialisation,
        "initialise_futures_contracts",
    )

    materialisation.setup_instruments(refdata)

    initialise_periods.assert_called_once_with(
        refdata,
        start_date=date(2000, 1, 1),
        end_date=date(2045, 12, 31),
    )
    initialise_period_cycles.assert_called_once_with(refdata)
    initialise_futures_products.assert_called_once_with(refdata, json_root=None)
    initialise_futures_contracts.assert_called_once_with(
        refdata,
        start_date=date(2000, 1, 1),
        end_date=date(2045, 12, 31),
    )


def test_is_table_empty(refdata: RefDataFixture) -> None:
    """is_table_empty should report whether an ORM table contains rows."""
    assert materialisation.is_table_empty(
        refdata.session_manager,
        FuturesProductORM,
    )

    materialisation.initialise_futures_products(refdata)

    assert not materialisation.is_table_empty(
        refdata.session_manager,
        FuturesProductORM,
    )
