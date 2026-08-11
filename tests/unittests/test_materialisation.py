"""Unit tests for MXM reference-data materialisation."""

from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Self, cast

import pytest
from psycopg import Connection, sql
from pytest import MonkeyPatch

from mxm.config import MXMConfig
from mxm.refdata import materialisation as materialisation_module
from mxm.refdata.models import (
    FuturesContract,
    FuturesProduct,
    Period,
    PeriodType,
)
from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.sources.futures_product import (
    FuturesProductSourceMetadata,
    FuturesProductSourceRecord,
)
from mxm.refdata.sql.postgres import (
    PostgresDatabase,
    PostgresRow,
)

_SOURCE_REVISION = "a" * 40


@dataclass(frozen=True)
class ProductStub:
    """Minimal product value used at mocked materialisation boundaries."""

    product_id: str
    trading_calendar: str


@dataclass(frozen=True)
class ContractStub:
    """Minimal contract value used at mocked generation boundaries."""

    contract_id: str


class FakeCursor:
    """Minimal cursor recording SQL executed by schema lifecycle operations."""

    def __init__(self) -> None:
        """Initialise an empty execution log."""

        self.executions: list[object] = []

    def __enter__(self) -> Self:
        """Enter the cursor context."""

        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Exit the cursor context."""

        del exc_type, exc_value, traceback

    def execute(
        self,
        query: object,
    ) -> None:
        """Record one SQL execution."""

        self.executions.append(query)


class FakeConnection:
    """Minimal connection exposing one recording cursor."""

    def __init__(self) -> None:
        """Initialise the fake connection."""

        self.cursor_calls = 0
        self.fake_cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        """Return the recording cursor."""

        self.cursor_calls += 1
        return self.fake_cursor


class FakePostgresDatabase:
    """Minimal transaction provider for materialisation unit tests."""

    def __init__(
        self,
        *,
        schema: str = "refdata_test_abc",
    ) -> None:
        """Initialise an owned schema and one opaque connection."""

        self.schema = schema
        self.connection = FakeConnection()
        self.transaction_calls = 0

    @contextmanager
    def transaction(
        self,
    ) -> Generator[Connection[PostgresRow]]:
        """Yield one opaque connection through a transaction boundary."""

        self.transaction_calls += 1

        yield cast(
            Connection[PostgresRow],
            self.connection,
        )


def _as_database(
    database: FakePostgresDatabase,
) -> PostgresDatabase:
    """Cast a fake database to the production database boundary."""

    return cast(
        PostgresDatabase,
        database,
    )


def _config(
    *,
    source_root: str = "/tmp/products",
    start_date: str = "2024-01-01",
    end_date: str = "2024-12-31",
) -> MXMConfig:
    """Construct representative materialisation configuration."""

    return cast(
        MXMConfig,
        {
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": source_root,
            "REFDATA_CONTRACT_START_DATE": start_date,
            "REFDATA_CONTRACT_END_DATE": end_date,
        },
    )


def _product(
    product_id: str,
    *,
    trading_calendar: str = "CME",
) -> FuturesProduct:
    """Construct a minimal typed product for orchestration tests."""

    return cast(
        FuturesProduct,
        ProductStub(
            product_id=product_id,
            trading_calendar=trading_calendar,
        ),
    )


def _contract(
    contract_id: str,
) -> FuturesContract:
    """Construct a minimal typed contract for orchestration tests."""

    return cast(
        FuturesContract,
        ContractStub(
            contract_id=contract_id,
        ),
    )


def _source_metadata(
    *,
    source_relative_path: str = "products/test.json",
    source_digest: str = "b" * 64,
) -> FuturesProductSourceMetadata:
    """Construct representative futures-product source metadata."""

    return FuturesProductSourceMetadata(
        schema_version="futures_product.v1",
        source_relative_path=source_relative_path,
        source_digest=source_digest,
        created_at=date(2026, 1, 1),
        updated_at=date(2026, 2, 1),
        review_status="reviewed",
        curator="mxm",
        source_type="exchange",
        source_url="https://example.com/product",
        source_accessed_at=date(2026, 1, 15),
        curation_method="manual",
        assistance="none",
        notes=("Representative source metadata.",),
    )


def _period(
    *,
    period_id: str,
    period_type: PeriodType,
    first_date: date,
    last_date: date,
) -> Period:
    """Construct one representative period."""

    return Period(
        period_id=period_id,
        period_type=period_type,
        first_date=first_date,
        last_date=last_date,
    )


def _month_period(
    *,
    period_id: str = "Jan-2024",
    first_date: date = date(2024, 1, 1),
    last_date: date = date(2024, 1, 31),
) -> Period:
    """Construct a representative monthly period."""

    return _period(
        period_id=period_id,
        period_type=PeriodType.MONTH,
        first_date=first_date,
        last_date=last_date,
    )


def _quarter_period(
    *,
    period_id: str = "2024-Q1",
    first_date: date = date(2024, 1, 1),
    last_date: date = date(2024, 3, 31),
) -> Period:
    """Construct a representative quarterly period."""

    return _period(
        period_id=period_id,
        period_type=PeriodType.QUARTER,
        first_date=first_date,
        last_date=last_date,
    )


def _year_period(
    *,
    period_id: str = "2024",
    first_date: date = date(2024, 1, 1),
    last_date: date = date(2024, 12, 31),
) -> Period:
    """Construct a representative yearly period."""

    return _period(
        period_id=period_id,
        period_type=PeriodType.YEAR,
        first_date=first_date,
        last_date=last_date,
    )


def _desired_state() -> materialisation_module._RefDataDesiredState:
    """Construct a complete representative desired state."""

    month = _month_period()

    cycles, memberships = materialisation_module._build_period_cycle_state(
        (month,),
    )

    product = _product("PRODUCT_A")
    metadata = _source_metadata()
    contract = _contract("PRODUCT_A.Jan-2024")

    return materialisation_module._RefDataDesiredState(
        periods=(month,),
        period_cycles=cycles,
        period_cycle_memberships=memberships,
        futures_products=(product,),
        futures_product_source_metadata=(
            (
                product.product_id,
                metadata,
            ),
        ),
        futures_product_source_revision=_SOURCE_REVISION,
        futures_contracts=(contract,),
    )


def _install_migration_runner(
    monkeypatch: MonkeyPatch,
    *,
    events: list[str],
) -> None:
    """Install a migration runner that records migration execution."""

    class FakeMigrationRunner:
        """Minimal migration runner recording one migration operation."""

        def __init__(
            self,
            database: PostgresDatabase,
        ) -> None:
            """Accept the composed database dependency."""

            del database

        def migrate(self) -> list[str]:
            """Record migration execution."""

            events.append("migrate")
            return []

    monkeypatch.setattr(
        materialisation_module,
        "MigrationRunner",
        FakeMigrationRunner,
    )


# ---------------------------------------------------------------------------
# Desired-state construction
# ---------------------------------------------------------------------------


def test_build_desired_state_separates_products_metadata_and_revision(
    monkeypatch: MonkeyPatch,
) -> None:
    """Source adapter records are unpacked into distinct desired-state values."""

    product_a = _product("PRODUCT_A")
    product_b = _product("PRODUCT_B")

    metadata_a = _source_metadata(
        source_relative_path="a.json",
        source_digest="a" * 64,
    )
    metadata_b = _source_metadata(
        source_relative_path="b.json",
        source_digest="b" * 64,
    )

    source_records = [
        FuturesProductSourceRecord(
            product=product_a,
            metadata=metadata_a,
        ),
        FuturesProductSourceRecord(
            product=product_b,
            metadata=metadata_b,
        ),
    ]

    def fake_load_futures_products(
        root_dir: object,
    ) -> list[FuturesProductSourceRecord]:
        """Return representative source-provider records."""

        assert str(root_dir) == "/tmp/products"
        return source_records

    def fake_resolve_source_revision(
        root_dir: object,
    ) -> str:
        """Return representative repository snapshot metadata."""

        assert str(root_dir) == "/tmp/products"
        return _SOURCE_REVISION

    def fake_generate_periods(
        start_date: date,
        end_date: date,
        period_types: Iterable[PeriodType],
        *,
        include_partial_end_period: bool = False,
    ) -> list[Period]:
        """Return no periods because generation is not under test here."""

        del start_date, end_date, period_types, include_partial_end_period
        return []

    def fake_validate_calendar_coverage(
        *,
        products: tuple[FuturesProduct, ...],
        start_date: date,
        end_date: date,
    ) -> None:
        """Accept calendar coverage for desired-state boundary testing."""

        del products, start_date, end_date

    def fake_generate_contracts(
        *,
        product: FuturesProduct,
        periods: Iterable[Period],
    ) -> list[FuturesContract]:
        """Return no contracts because contract generation is tested elsewhere."""

        del product, periods
        return []

    monkeypatch.setattr(
        materialisation_module,
        "load_futures_products",
        fake_load_futures_products,
    )
    monkeypatch.setattr(
        materialisation_module,
        "resolve_futures_product_source_revision",
        fake_resolve_source_revision,
    )
    monkeypatch.setattr(
        materialisation_module,
        "generate_periods",
        fake_generate_periods,
    )
    monkeypatch.setattr(
        materialisation_module,
        "validate_calendar_coverage_for_contract_initialisation",
        fake_validate_calendar_coverage,
    )
    monkeypatch.setattr(
        materialisation_module,
        "generate_futures_contracts",
        fake_generate_contracts,
    )

    state = materialisation_module._build_desired_state(
        config=_config(),
    )

    assert state.futures_products == (
        product_a,
        product_b,
    )

    assert state.futures_product_source_metadata == (
        (
            product_a.product_id,
            metadata_a,
        ),
        (
            product_b.product_id,
            metadata_b,
        ),
    )

    assert state.futures_product_source_revision == _SOURCE_REVISION


def test_build_desired_state_uses_horizon_and_generates_each_product(
    monkeypatch: MonkeyPatch,
) -> None:
    """Configured horizon drives generation and every product generates contracts."""

    product_a = _product("PRODUCT_A")
    product_b = _product("PRODUCT_B")

    source_records = [
        FuturesProductSourceRecord(
            product=product_a,
            metadata=_source_metadata(
                source_relative_path="a.json",
                source_digest="a" * 64,
            ),
        ),
        FuturesProductSourceRecord(
            product=product_b,
            metadata=_source_metadata(
                source_relative_path="b.json",
                source_digest="b" * 64,
            ),
        ),
    ]

    month = _month_period()

    generated_period_calls: list[
        tuple[
            date,
            date,
            tuple[PeriodType, ...],
        ]
    ] = []

    calendar_validation_calls: list[
        tuple[
            tuple[FuturesProduct, ...],
            date,
            date,
        ]
    ] = []

    contract_generation_calls: list[
        tuple[
            str,
            tuple[Period, ...],
        ]
    ] = []

    contract_a = _contract("PRODUCT_A.Jan-2024")
    contract_b = _contract("PRODUCT_B.Jan-2024")

    def fake_load_futures_products(
        root_dir: object,
    ) -> list[FuturesProductSourceRecord]:
        """Return the configured product universe."""

        del root_dir
        return source_records

    def fake_resolve_source_revision(
        root_dir: object,
    ) -> str:
        """Return the configured repository revision."""

        del root_dir
        return _SOURCE_REVISION

    def fake_generate_periods(
        start_date: date,
        end_date: date,
        period_types: Iterable[PeriodType],
        *,
        include_partial_end_period: bool = False,
    ) -> list[Period]:
        """Record the requested generation horizon."""

        assert include_partial_end_period is False

        generated_period_calls.append(
            (
                start_date,
                end_date,
                tuple(period_types),
            )
        )

        return [month]

    def fake_validate_calendar_coverage(
        *,
        products: tuple[FuturesProduct, ...],
        start_date: date,
        end_date: date,
    ) -> None:
        """Record the calendar-validation horizon."""

        calendar_validation_calls.append(
            (
                products,
                start_date,
                end_date,
            )
        )

    def fake_generate_contracts(
        *,
        product: FuturesProduct,
        periods: Iterable[Period],
    ) -> list[FuturesContract]:
        """Record each product participating in contract generation."""

        available_periods = tuple(periods)

        contract_generation_calls.append(
            (
                product.product_id,
                available_periods,
            )
        )

        if product.product_id == "PRODUCT_A":
            return [contract_a]

        return [contract_b]

    monkeypatch.setattr(
        materialisation_module,
        "load_futures_products",
        fake_load_futures_products,
    )
    monkeypatch.setattr(
        materialisation_module,
        "resolve_futures_product_source_revision",
        fake_resolve_source_revision,
    )
    monkeypatch.setattr(
        materialisation_module,
        "generate_periods",
        fake_generate_periods,
    )
    monkeypatch.setattr(
        materialisation_module,
        "validate_calendar_coverage_for_contract_initialisation",
        fake_validate_calendar_coverage,
    )
    monkeypatch.setattr(
        materialisation_module,
        "generate_futures_contracts",
        fake_generate_contracts,
    )

    state = materialisation_module._build_desired_state(
        config=_config(
            start_date="2024-01-01",
            end_date="2024-12-31",
        ),
    )

    assert generated_period_calls == [
        (
            date(2024, 1, 1),
            date(2024, 12, 31),
            (
                PeriodType.YEAR,
                PeriodType.QUARTER,
                PeriodType.MONTH,
            ),
        )
    ]

    assert calendar_validation_calls == [
        (
            (
                product_a,
                product_b,
            ),
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
    ]

    assert contract_generation_calls == [
        (
            "PRODUCT_A",
            (month,),
        ),
        (
            "PRODUCT_B",
            (month,),
        ),
    ]

    assert state.futures_contracts == (
        contract_a,
        contract_b,
    )


def test_build_desired_state_rejects_invalid_date_range_before_source_loading(
    monkeypatch: MonkeyPatch,
) -> None:
    """An invalid configured horizon fails before source-provider work."""

    source_load_calls = 0

    def fake_load_futures_products(
        root_dir: object,
    ) -> list[FuturesProductSourceRecord]:
        """Record an unexpected source-provider call."""

        nonlocal source_load_calls

        del root_dir
        source_load_calls += 1
        return []

    monkeypatch.setattr(
        materialisation_module,
        "load_futures_products",
        fake_load_futures_products,
    )

    with pytest.raises(
        ValueError,
        match=r"start date must not be after end date",
    ):
        materialisation_module._build_desired_state(
            config=_config(
                start_date="2025-01-01",
                end_date="2024-12-31",
            ),
        )

    assert source_load_calls == 0


# ---------------------------------------------------------------------------
# Period-cycle desired state
# ---------------------------------------------------------------------------


def test_build_period_cycle_state_creates_canonical_cycles() -> None:
    """Materialisation defines canonical month and quarter cycles."""

    cycles, memberships = materialisation_module._build_period_cycle_state(
        (),
    )

    assert memberships == ()

    assert cycles == (
        PeriodCycle(
            cycle_id=materialisation_module.CYCLE_ID_CALENDAR_MONTHS,
            name="Calendar Months",
            period_type=PeriodType.MONTH,
            cycle_size=12,
            instance_kind=CycleInstanceKind.YEAR,
        ),
        PeriodCycle(
            cycle_id=materialisation_module.CYCLE_ID_CALENDAR_QUARTERS,
            name="Calendar Quarters",
            period_type=PeriodType.QUARTER,
            cycle_size=4,
            instance_kind=CycleInstanceKind.YEAR,
        ),
    )


def test_build_period_cycle_state_maps_months_and_quarters_to_positions() -> None:
    """Calendar periods receive the expected year instance and cycle element."""

    january = _month_period(
        period_id="Jan-2024",
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 31),
    )
    december = _month_period(
        period_id="Dec-2025",
        first_date=date(2025, 12, 1),
        last_date=date(2025, 12, 31),
    )
    first_quarter = _quarter_period(
        period_id="2024-Q1",
        first_date=date(2024, 1, 1),
        last_date=date(2024, 3, 31),
    )
    fourth_quarter = _quarter_period(
        period_id="2025-Q4",
        first_date=date(2025, 10, 1),
        last_date=date(2025, 12, 31),
    )

    _, memberships = materialisation_module._build_period_cycle_state(
        (
            january,
            december,
            first_quarter,
            fourth_quarter,
        ),
    )

    assert memberships == (
        PeriodCycleMembership(
            cycle_id=materialisation_module.CYCLE_ID_CALENDAR_MONTHS,
            period_id=january.period_id,
            cycle_instance=2024,
            cycle_element=1,
        ),
        PeriodCycleMembership(
            cycle_id=materialisation_module.CYCLE_ID_CALENDAR_MONTHS,
            period_id=december.period_id,
            cycle_instance=2025,
            cycle_element=12,
        ),
        PeriodCycleMembership(
            cycle_id=materialisation_module.CYCLE_ID_CALENDAR_QUARTERS,
            period_id=first_quarter.period_id,
            cycle_instance=2024,
            cycle_element=1,
        ),
        PeriodCycleMembership(
            cycle_id=materialisation_module.CYCLE_ID_CALENDAR_QUARTERS,
            period_id=fourth_quarter.period_id,
            cycle_instance=2025,
            cycle_element=4,
        ),
    )


def test_build_period_cycle_state_ignores_non_cycle_period_types() -> None:
    """Periods outside month and quarter cycles create no memberships."""

    year = _year_period()

    week = _period(
        period_id="2024-W1",
        period_type=PeriodType.WEEK,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 7),
    )

    _, memberships = materialisation_module._build_period_cycle_state(
        (
            year,
            week,
        ),
    )

    assert memberships == ()


# ---------------------------------------------------------------------------
# Desired-state persistence
# ---------------------------------------------------------------------------


def test_persist_desired_state_uses_one_transaction_and_dependency_order(
    monkeypatch: MonkeyPatch,
) -> None:
    """The complete desired state is written atomically in dependency order."""

    state = _desired_state()

    fake_database = FakePostgresDatabase()
    database = _as_database(fake_database)

    events: list[str] = []
    connections: list[Connection[PostgresRow]] = []
    schemas: list[str] = []

    persisted_sources: list[
        tuple[
            str,
            FuturesProductSourceMetadata,
            str,
        ]
    ] = []

    def record(
        event: str,
        connection: Connection[PostgresRow],
        schema: str,
    ) -> None:
        """Record one materialisation persistence operation."""

        events.append(event)
        connections.append(connection)
        schemas.append(schema)

    def fake_insert_periods(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        periods: Sequence[Period],
    ) -> None:
        """Record period persistence."""

        assert tuple(periods) == state.periods
        record("periods", connection, schema)

    def fake_insert_period_cycles(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        period_cycles: Sequence[PeriodCycle],
    ) -> None:
        """Record period-cycle persistence."""

        assert tuple(period_cycles) == state.period_cycles
        record("cycles", connection, schema)

    def fake_insert_memberships(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        memberships: Sequence[PeriodCycleMembership],
    ) -> None:
        """Record period-cycle-membership persistence."""

        assert tuple(memberships) == state.period_cycle_memberships
        record("memberships", connection, schema)

    def fake_insert_products(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        products: Sequence[FuturesProduct],
    ) -> None:
        """Record operational-product persistence."""

        assert tuple(products) == state.futures_products
        record("products", connection, schema)

    def fake_upsert_sources(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        sources: Sequence[
            tuple[
                str,
                FuturesProductSourceMetadata,
                str,
            ]
        ],
    ) -> None:
        """Record source-provenance persistence."""

        persisted_sources.extend(sources)
        record("product_sources", connection, schema)

    def fake_insert_contracts(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        contracts: Sequence[FuturesContract],
    ) -> None:
        """Record futures-contract persistence."""

        assert tuple(contracts) == state.futures_contracts
        record("contracts", connection, schema)

    monkeypatch.setattr(
        materialisation_module,
        "insert_periods",
        fake_insert_periods,
    )
    monkeypatch.setattr(
        materialisation_module,
        "insert_period_cycles",
        fake_insert_period_cycles,
    )
    monkeypatch.setattr(
        materialisation_module,
        "insert_period_cycle_memberships",
        fake_insert_memberships,
    )
    monkeypatch.setattr(
        materialisation_module,
        "insert_futures_products",
        fake_insert_products,
    )
    monkeypatch.setattr(
        materialisation_module,
        "upsert_futures_product_sources",
        fake_upsert_sources,
    )
    monkeypatch.setattr(
        materialisation_module,
        "insert_futures_contracts",
        fake_insert_contracts,
    )

    materialisation_module._persist_desired_state(
        database=database,
        desired_state=state,
    )

    assert fake_database.transaction_calls == 1

    assert events == [
        "periods",
        "cycles",
        "memberships",
        "products",
        "product_sources",
        "contracts",
    ]

    assert all(connection is connections[0] for connection in connections)

    assert schemas == ["refdata_test_abc"] * 6

    assert persisted_sources == [
        (
            product_id,
            metadata,
            _SOURCE_REVISION,
        )
        for (
            product_id,
            metadata,
        ) in state.futures_product_source_metadata
    ]


# ---------------------------------------------------------------------------
# Build lifecycle
# ---------------------------------------------------------------------------


def test_build_refdata_constructs_state_before_migration_and_persistence(
    monkeypatch: MonkeyPatch,
) -> None:
    """Build validates desired state before touching PostgreSQL."""

    events: list[str] = []
    desired_state = object()

    config = _config()
    database = _as_database(
        FakePostgresDatabase(),
    )

    def fake_build_desired_state(
        *,
        config: MXMConfig,
    ) -> object:
        """Record desired-state construction."""

        del config
        events.append("desired_state")
        return desired_state

    def fake_persist_desired_state(
        *,
        database: PostgresDatabase,
        desired_state: object,
    ) -> None:
        """Record final state persistence."""

        del database

        assert desired_state is desired_state_value
        events.append("persist")

    desired_state_value = desired_state

    monkeypatch.setattr(
        materialisation_module,
        "_build_desired_state",
        fake_build_desired_state,
    )
    monkeypatch.setattr(
        materialisation_module,
        "_persist_desired_state",
        fake_persist_desired_state,
    )

    _install_migration_runner(
        monkeypatch,
        events=events,
    )

    materialisation_module.build_refdata(
        config=config,
        database=database,
    )

    assert events == [
        "desired_state",
        "migrate",
        "persist",
    ]


def test_build_refdata_does_not_touch_database_when_state_construction_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    """Desired-state failure prevents migration and persistence."""

    events: list[str] = []

    def failing_build_desired_state(
        *,
        config: MXMConfig,
    ) -> object:
        """Fail before any database mutation can occur."""

        del config
        events.append("desired_state")
        raise RuntimeError("desired state failed")

    class UnexpectedMigrationRunner:
        """Migration runner that must never be constructed."""

        def __init__(
            self,
            database: PostgresDatabase,
        ) -> None:
            """Fail if migration is attempted."""

            del database
            raise AssertionError("Migration must not be attempted")

    monkeypatch.setattr(
        materialisation_module,
        "_build_desired_state",
        failing_build_desired_state,
    )
    monkeypatch.setattr(
        materialisation_module,
        "MigrationRunner",
        UnexpectedMigrationRunner,
    )

    with pytest.raises(
        RuntimeError,
        match=r"desired state failed",
    ):
        materialisation_module.build_refdata(
            config=_config(),
            database=_as_database(
                FakePostgresDatabase(),
            ),
        )

    assert events == ["desired_state"]


# ---------------------------------------------------------------------------
# Rebuild lifecycle
# ---------------------------------------------------------------------------


def test_rebuild_refdata_orders_validation_drop_migration_and_persistence(
    monkeypatch: MonkeyPatch,
) -> None:
    """Rebuild validates desired state before its destructive operation."""

    events: list[str] = []
    desired_state = object()

    database = _as_database(
        FakePostgresDatabase(),
    )

    def fake_build_desired_state(
        *,
        config: MXMConfig,
    ) -> object:
        """Record desired-state construction."""

        del config
        events.append("desired_state")
        return desired_state

    def fake_drop_owned_schema(
        database: PostgresDatabase,
    ) -> None:
        """Record the destructive schema lifecycle operation."""

        del database
        events.append("drop_schema")

    def fake_persist_desired_state(
        *,
        database: PostgresDatabase,
        desired_state: object,
    ) -> None:
        """Record final persistence."""

        del database

        assert desired_state is desired_state_value
        events.append("persist")

    desired_state_value = desired_state

    monkeypatch.setattr(
        materialisation_module,
        "_build_desired_state",
        fake_build_desired_state,
    )
    monkeypatch.setattr(
        materialisation_module,
        "_drop_owned_schema",
        fake_drop_owned_schema,
    )
    monkeypatch.setattr(
        materialisation_module,
        "_persist_desired_state",
        fake_persist_desired_state,
    )

    _install_migration_runner(
        monkeypatch,
        events=events,
    )

    materialisation_module.rebuild_refdata(
        config=_config(),
        database=database,
    )

    assert events == [
        "desired_state",
        "drop_schema",
        "migrate",
        "persist",
    ]


def test_rebuild_refdata_does_not_drop_schema_when_state_construction_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    """Invalid desired state cannot destroy an existing refdata schema."""

    drop_calls = 0

    def failing_build_desired_state(
        *,
        config: MXMConfig,
    ) -> object:
        """Fail desired-state construction."""

        del config
        raise RuntimeError("desired state failed")

    def fake_drop_owned_schema(
        database: PostgresDatabase,
    ) -> None:
        """Record an invalid destructive call."""

        nonlocal drop_calls

        del database
        drop_calls += 1

    monkeypatch.setattr(
        materialisation_module,
        "_build_desired_state",
        failing_build_desired_state,
    )
    monkeypatch.setattr(
        materialisation_module,
        "_drop_owned_schema",
        fake_drop_owned_schema,
    )

    with pytest.raises(
        RuntimeError,
        match=r"desired state failed",
    ):
        materialisation_module.rebuild_refdata(
            config=_config(),
            database=_as_database(
                FakePostgresDatabase(),
            ),
        )

    assert drop_calls == 0


def test_drop_owned_schema_targets_only_configured_schema() -> None:
    """Rebuild schema lifecycle targets the database boundary's owned schema."""

    fake_database = FakePostgresDatabase(
        schema="refdata_test_abc",
    )

    materialisation_module._drop_owned_schema(
        _as_database(fake_database),
    )

    assert fake_database.transaction_calls == 1
    assert fake_database.connection.cursor_calls == 1

    executions = fake_database.connection.fake_cursor.executions

    assert len(executions) == 1

    query = executions[0]

    assert isinstance(
        query,
        sql.Composable,
    )

    query_text = " ".join(query.as_string().split())

    assert query_text == ('DROP SCHEMA IF EXISTS "refdata_test_abc" CASCADE')


@pytest.mark.parametrize(
    "schema",
    [
        "public",
        "pg_catalog",
        "information_schema",
    ],
)
def test_drop_owned_schema_rejects_protected_schemas(
    schema: str,
) -> None:
    """Rebuild cannot destroy PostgreSQL infrastructure schemas."""

    fake_database = FakePostgresDatabase(
        schema=schema,
    )

    with pytest.raises(
        ValueError,
        match=r"protected PostgreSQL schema",
    ):
        materialisation_module._drop_owned_schema(
            _as_database(fake_database),
        )

    assert fake_database.transaction_calls == 0


def test_drop_owned_schema_rejects_empty_schema() -> None:
    """Rebuild requires an explicit non-empty owned schema."""

    fake_database = FakePostgresDatabase(
        schema="",
    )

    with pytest.raises(
        ValueError,
        match=r"empty schema name",
    ):
        materialisation_module._drop_owned_schema(
            _as_database(fake_database),
        )

    assert fake_database.transaction_calls == 0


# ---------------------------------------------------------------------------
# Trading-calendar coverage
# ---------------------------------------------------------------------------


def test_calendar_coverage_expands_horizon_for_every_product(
    monkeypatch: MonkeyPatch,
) -> None:
    """Contract rules require two years lookback and one year lookahead."""

    coverage_calls: list[
        tuple[
            str,
            date,
            date,
        ]
    ] = []

    class FakeTradingCalendar:
        """Trading calendar recording requested coverage ranges."""

        def __init__(
            self,
            calendar_name: str,
        ) -> None:
            """Retain the requested calendar name."""

            self.calendar_name = calendar_name

        def ensure_range_in_coverage(
            self,
            start_date: date,
            end_date: date,
        ) -> None:
            """Record the required coverage interval."""

            coverage_calls.append(
                (
                    self.calendar_name,
                    start_date,
                    end_date,
                )
            )

    monkeypatch.setattr(
        materialisation_module,
        "TradingCalendar",
        FakeTradingCalendar,
    )

    products = (
        _product(
            "PRODUCT_A",
            trading_calendar="CALENDAR_A",
        ),
        _product(
            "PRODUCT_B",
            trading_calendar="CALENDAR_B",
        ),
    )

    materialisation_module.validate_calendar_coverage_for_contract_initialisation(
        products=products,
        start_date=date(2020, 1, 1),
        end_date=date(2030, 12, 31),
    )

    assert coverage_calls == [
        (
            "CALENDAR_A",
            date(2018, 1, 1),
            date(2031, 12, 31),
        ),
        (
            "CALENDAR_B",
            date(2018, 1, 1),
            date(2031, 12, 31),
        ),
    ]


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


def test_build_desired_state_rejects_empty_source_root() -> None:
    """Materialisation requires an explicit futures-product source root."""

    with pytest.raises(
        ValueError,
        match=r"REFDATA_FUTURES_PRODUCTS_JSON_ROOT.*non-empty text",
    ):
        materialisation_module._build_desired_state(
            config=_config(
                source_root="",
            ),
        )


def test_build_desired_state_rejects_invalid_iso_date() -> None:
    """Materialisation requires valid ISO contract-horizon dates."""

    with pytest.raises(
        ValueError,
        match=r"REFDATA_CONTRACT_START_DATE.*ISO date",
    ):
        materialisation_module._build_desired_state(
            config=_config(
                start_date="not-a-date",
            ),
        )
