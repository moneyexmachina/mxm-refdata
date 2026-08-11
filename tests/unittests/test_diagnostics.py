"""Unit tests for application-level MXM reference-data diagnostics."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

from psycopg import Connection
from pytest import MonkeyPatch

from mxm.refdata import diagnostics as diagnostics_module
from mxm.refdata.diagnostics import (
    DiagnosticResult,
    run_refdata_diagnostics,
)
from mxm.refdata.models import PeriodType
from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sql.diagnostics import (
    RefDataDiagnosticsPersistenceError,
    RefDataRowCounts,
)
from mxm.refdata.sql.migration_runner import (
    MigrationInspection,
    MigrationStateError,
)
from mxm.refdata.sql.postgres import (
    PostgresDatabase,
    PostgresRow,
)


class FakePostgresDatabase:
    """Minimal transaction provider for diagnostic unit tests."""

    def __init__(
        self,
        *,
        schema: str = "refdata_test_abc",
    ) -> None:
        """Initialise the fake database."""

        self.schema = schema
        self.transaction_calls = 0
        self.connection = cast(
            Connection[PostgresRow],
            object(),
        )

    @contextmanager
    def transaction(
        self,
    ) -> Generator[Connection[PostgresRow]]:
        """Yield one opaque connection through the transaction boundary."""

        self.transaction_calls += 1
        yield self.connection


class FakeRefDataReader:
    """Minimal read capability exposing period-cycle observations."""

    def __init__(
        self,
        *,
        cycles: dict[str, PeriodCycle] | None = None,
        memberships: (
            dict[
                str,
                list[PeriodCycleMembership],
            ]
            | None
        ) = None,
    ) -> None:
        """Initialise configured cycle observations."""

        self.cycles = dict(cycles or {})
        self.memberships = {
            cycle_id: list(values) for cycle_id, values in (memberships or {}).items()
        }

        self.cycle_lookup_calls: list[str] = []
        self.membership_lookup_calls: list[str] = []

    def get_cycle_by_id(
        self,
        cycle_id: str,
    ) -> PeriodCycle | None:
        """Return a configured period cycle."""

        self.cycle_lookup_calls.append(cycle_id)
        return self.cycles.get(cycle_id)

    def get_cycle_memberships(
        self,
        cycle_id: str,
    ) -> list[PeriodCycleMembership]:
        """Return configured memberships for one cycle."""

        self.membership_lookup_calls.append(cycle_id)
        return list(
            self.memberships.get(
                cycle_id,
                [],
            )
        )


def _as_database(
    database: FakePostgresDatabase,
) -> PostgresDatabase:
    """Cast a fake database to the production boundary."""

    return cast(
        PostgresDatabase,
        database,
    )


def _as_reader(
    reader: FakeRefDataReader,
) -> RefDataReader:
    """Cast a fake reader to the production read capability."""

    return cast(
        RefDataReader,
        reader,
    )


def _migration_inspection(
    *,
    initialised: bool = True,
    pending_versions: tuple[str, ...] = (),
) -> MigrationInspection:
    """Construct representative migration inspection state."""

    packaged_versions = (
        "001",
        "002",
    )

    if not initialised:
        return MigrationInspection(
            initialised=False,
            packaged_versions=packaged_versions,
            applied_versions=(),
            pending_versions=packaged_versions,
        )

    applied_versions = tuple(
        version for version in packaged_versions if version not in pending_versions
    )

    return MigrationInspection(
        initialised=True,
        packaged_versions=packaged_versions,
        applied_versions=applied_versions,
        pending_versions=pending_versions,
    )


def _healthy_counts() -> RefDataRowCounts:
    """Construct representative healthy materialised row counts."""

    return RefDataRowCounts(
        products=86,
        product_sources=86,
        periods=799,
        contracts=31_447,
        cycles=2,
        memberships=752,
    )


def _calendar_months_cycle(
    *,
    period_type: PeriodType = PeriodType.MONTH,
    cycle_size: int = 12,
) -> PeriodCycle:
    """Construct the canonical calendar-month cycle."""

    return PeriodCycle(
        cycle_id=diagnostics_module.CYCLE_ID_CALENDAR_MONTHS,
        name="Calendar Months",
        period_type=period_type,
        cycle_size=cycle_size,
        instance_kind=CycleInstanceKind.YEAR,
    )


def _calendar_quarters_cycle() -> PeriodCycle:
    """Construct the canonical calendar-quarter cycle."""

    return PeriodCycle(
        cycle_id=diagnostics_module.CYCLE_ID_CALENDAR_QUARTERS,
        name="Calendar Quarters",
        period_type=PeriodType.QUARTER,
        cycle_size=4,
        instance_kind=CycleInstanceKind.YEAR,
    )


def _month_membership() -> PeriodCycleMembership:
    """Construct one representative calendar-month membership."""

    return PeriodCycleMembership(
        cycle_id=diagnostics_module.CYCLE_ID_CALENDAR_MONTHS,
        period_id="2024-01",
        cycle_instance=2024,
        cycle_element=1,
    )


def _quarter_membership() -> PeriodCycleMembership:
    """Construct one representative calendar-quarter membership."""

    return PeriodCycleMembership(
        cycle_id=diagnostics_module.CYCLE_ID_CALENDAR_QUARTERS,
        period_id="2024-Q1",
        cycle_instance=2024,
        cycle_element=1,
    )


def _healthy_reader() -> FakeRefDataReader:
    """Construct healthy canonical period-cycle observations."""

    months = _calendar_months_cycle()
    quarters = _calendar_quarters_cycle()

    return FakeRefDataReader(
        cycles={
            months.cycle_id: months,
            quarters.cycle_id: quarters,
        },
        memberships={
            months.cycle_id: [
                _month_membership(),
            ],
            quarters.cycle_id: [
                _quarter_membership(),
            ],
        },
    )


def _result_by_name(
    results: tuple[DiagnosticResult, ...],
    name: str,
) -> DiagnosticResult:
    """Return one diagnostic result by its stable name."""

    matches = [result for result in results if result.name == name]

    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly one diagnostic result named {name!r}, got {matches!r}"
        )

    return matches[0]


def _install_migration_inspection(
    monkeypatch: MonkeyPatch,
    inspection: MigrationInspection,
) -> None:
    """Install a migration runner returning fixed inspection state."""

    class FakeMigrationRunner:
        """Migration runner returning one fixed observation."""

        def __init__(
            self,
            database: PostgresDatabase,
        ) -> None:
            """Accept the composed database dependency."""

            del database

        def inspect(self) -> MigrationInspection:
            """Return the configured migration inspection."""

            return inspection

    monkeypatch.setattr(
        diagnostics_module,
        "MigrationRunner",
        FakeMigrationRunner,
    )


def _install_migration_failure(
    monkeypatch: MonkeyPatch,
    error: MigrationStateError,
) -> None:
    """Install a migration runner whose inspection fails."""

    class FailingMigrationRunner:
        """Migration runner raising one fixed inspection failure."""

        def __init__(
            self,
            database: PostgresDatabase,
        ) -> None:
            """Accept the composed database dependency."""

            del database

        def inspect(self) -> MigrationInspection:
            """Raise the configured migration-state failure."""

            raise error

    monkeypatch.setattr(
        diagnostics_module,
        "MigrationRunner",
        FailingMigrationRunner,
    )


# ---------------------------------------------------------------------------
# MIGRATION GATING
# ---------------------------------------------------------------------------


def test_diagnostics_stops_when_schema_is_uninitialised(
    monkeypatch: MonkeyPatch,
) -> None:
    """An uninitialised schema prevents materialised-state inspection."""

    inspection = _migration_inspection(
        initialised=False,
    )

    _install_migration_inspection(
        monkeypatch,
        inspection,
    )

    def unexpected_count_fetch(
        connection: Connection[PostgresRow],
        *,
        schema: str,
    ) -> RefDataRowCounts:
        """Fail if materialised tables are inspected."""

        del connection, schema
        raise AssertionError(
            "Materialised row counts must not be queried for an uninitialised schema"
        )

    monkeypatch.setattr(
        diagnostics_module,
        "fetch_refdata_row_counts",
        unexpected_count_fetch,
    )

    database = FakePostgresDatabase()
    reader = FakeRefDataReader()

    report = run_refdata_diagnostics(
        database=_as_database(database),
        reader=_as_reader(reader),
    )

    assert report.migration == inspection
    assert report.counts is None
    assert report.ready is False

    result = _result_by_name(
        report.results,
        "migration initialised",
    )

    assert result.status == "fail"
    assert "not been initialised" in result.message

    assert database.transaction_calls == 0
    assert reader.cycle_lookup_calls == []
    assert reader.membership_lookup_calls == []


def test_diagnostics_stops_when_migrations_are_pending(
    monkeypatch: MonkeyPatch,
) -> None:
    """Pending migrations prevent current-table diagnostic inspection."""

    inspection = _migration_inspection(
        pending_versions=("002",),
    )

    _install_migration_inspection(
        monkeypatch,
        inspection,
    )

    def unexpected_count_fetch(
        connection: Connection[PostgresRow],
        *,
        schema: str,
    ) -> RefDataRowCounts:
        """Fail if current table shape is inspected."""

        del connection, schema
        raise AssertionError(
            "Materialised row counts must not be queried while migrations are pending"
        )

    monkeypatch.setattr(
        diagnostics_module,
        "fetch_refdata_row_counts",
        unexpected_count_fetch,
    )

    database = FakePostgresDatabase()
    reader = FakeRefDataReader()

    report = run_refdata_diagnostics(
        database=_as_database(database),
        reader=_as_reader(reader),
    )

    assert report.migration == inspection
    assert report.counts is None
    assert report.ready is False

    initialised_result = _result_by_name(
        report.results,
        "migration initialised",
    )
    current_result = _result_by_name(
        report.results,
        "migration current",
    )

    assert initialised_result.status == "pass"
    assert current_result.status == "fail"
    assert "002" in current_result.message

    assert database.transaction_calls == 0
    assert reader.cycle_lookup_calls == []
    assert reader.membership_lookup_calls == []


def test_diagnostics_reports_migration_inspection_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    """Invalid migration state becomes a diagnostic failure."""

    error = MigrationStateError("migration ledger is inconsistent")

    _install_migration_failure(
        monkeypatch,
        error,
    )

    database = FakePostgresDatabase()
    reader = FakeRefDataReader()

    report = run_refdata_diagnostics(
        database=_as_database(database),
        reader=_as_reader(reader),
    )

    assert report.migration is None
    assert report.counts is None
    assert report.ready is False

    assert report.results == (
        DiagnosticResult(
            name="migration state",
            status="fail",
            message="migration ledger is inconsistent",
        ),
    )

    assert database.transaction_calls == 0
    assert reader.cycle_lookup_calls == []
    assert reader.membership_lookup_calls == []


# ---------------------------------------------------------------------------
# MATERIALISED COUNT POLICY
# ---------------------------------------------------------------------------


def test_healthy_materialised_counts_pass_all_count_checks() -> None:
    """Non-empty coherent materialised counts satisfy count policy."""

    results = diagnostics_module._check_materialised_counts(
        _healthy_counts(),
    )

    assert results == (
        DiagnosticResult(
            name="core reference data populated",
            status="pass",
        ),
        DiagnosticResult(
            name="product provenance complete",
            status="pass",
        ),
        DiagnosticResult(
            name="period cycles populated",
            status="pass",
        ),
    )


def test_materialised_counts_report_missing_core_tables() -> None:
    """Core-data diagnostics identify all empty core tables together."""

    counts = RefDataRowCounts(
        products=0,
        product_sources=0,
        periods=799,
        contracts=0,
        cycles=2,
        memberships=752,
    )

    results = diagnostics_module._check_materialised_counts(
        counts,
    )

    core_result = _result_by_name(
        results,
        "core reference data populated",
    )

    assert core_result.status == "fail"
    assert "futures_products" in core_result.message
    assert "futures_contracts" in core_result.message
    assert "periods" not in core_result.message


def test_materialised_counts_require_complete_product_provenance() -> None:
    """Every operational product requires one provenance record."""

    counts = RefDataRowCounts(
        products=86,
        product_sources=85,
        periods=799,
        contracts=31_447,
        cycles=2,
        memberships=752,
    )

    results = diagnostics_module._check_materialised_counts(
        counts,
    )

    provenance_result = _result_by_name(
        results,
        "product provenance complete",
    )

    assert provenance_result.status == "fail"
    assert "products=86" in provenance_result.message
    assert "product_sources=85" in provenance_result.message


def test_materialised_counts_require_cycle_memberships() -> None:
    """Canonical cycle tables are not ready without memberships."""

    counts = RefDataRowCounts(
        products=86,
        product_sources=86,
        periods=799,
        contracts=31_447,
        cycles=2,
        memberships=0,
    )

    results = diagnostics_module._check_materialised_counts(
        counts,
    )

    cycle_result = _result_by_name(
        results,
        "period cycles populated",
    )

    assert cycle_result.status == "fail"
    assert "period_cycle_memberships" in cycle_result.message
    assert "period_cycles" not in cycle_result.message


# ---------------------------------------------------------------------------
# CANONICAL CYCLE POLICY
# ---------------------------------------------------------------------------


def test_canonical_cycles_pass_when_structure_and_memberships_are_valid() -> None:
    """Both canonical calendar cycles satisfy domain readiness policy."""

    reader = _healthy_reader()

    results = diagnostics_module._check_canonical_cycles(
        _as_reader(reader),
    )

    assert results == (
        DiagnosticResult(
            name="canonical cycle CALENDAR_MONTHS",
            status="pass",
        ),
        DiagnosticResult(
            name="canonical cycle CALENDAR_QUARTERS",
            status="pass",
        ),
    )


def test_missing_canonical_cycle_fails_diagnostics() -> None:
    """A missing canonical period cycle is operationally invalid."""

    quarters = _calendar_quarters_cycle()

    reader = FakeRefDataReader(
        cycles={
            quarters.cycle_id: quarters,
        },
        memberships={
            quarters.cycle_id: [
                _quarter_membership(),
            ],
        },
    )

    results = diagnostics_module._check_canonical_cycles(
        _as_reader(reader),
    )

    month_result = _result_by_name(
        results,
        "canonical cycle CALENDAR_MONTHS",
    )
    quarter_result = _result_by_name(
        results,
        "canonical cycle CALENDAR_QUARTERS",
    )

    assert month_result.status == "fail"
    assert "missing" in month_result.message.lower()

    assert quarter_result.status == "pass"


def test_malformed_canonical_cycle_reports_structural_mismatches() -> None:
    """Canonical cycle identity alone is insufficient for readiness."""

    malformed_months = _calendar_months_cycle(
        period_type=PeriodType.QUARTER,
        cycle_size=4,
    )
    quarters = _calendar_quarters_cycle()

    reader = FakeRefDataReader(
        cycles={
            malformed_months.cycle_id: malformed_months,
            quarters.cycle_id: quarters,
        },
        memberships={
            malformed_months.cycle_id: [
                _month_membership(),
            ],
            quarters.cycle_id: [
                _quarter_membership(),
            ],
        },
    )

    results = diagnostics_module._check_canonical_cycles(
        _as_reader(reader),
    )

    month_result = _result_by_name(
        results,
        "canonical cycle CALENDAR_MONTHS",
    )

    assert month_result.status == "fail"
    assert "period_type" in month_result.message
    assert "cycle_size" in month_result.message


def test_canonical_cycle_requires_materialised_memberships() -> None:
    """A structurally valid canonical cycle must contain memberships."""

    months = _calendar_months_cycle()
    quarters = _calendar_quarters_cycle()

    reader = FakeRefDataReader(
        cycles={
            months.cycle_id: months,
            quarters.cycle_id: quarters,
        },
        memberships={
            months.cycle_id: [],
            quarters.cycle_id: [
                _quarter_membership(),
            ],
        },
    )

    results = diagnostics_module._check_canonical_cycles(
        _as_reader(reader),
    )

    month_result = _result_by_name(
        results,
        "canonical cycle CALENDAR_MONTHS",
    )

    assert month_result.status == "fail"
    assert "no memberships" in month_result.message.lower()


# ---------------------------------------------------------------------------
# AGGREGATE READINESS
# ---------------------------------------------------------------------------


def test_healthy_diagnostic_observations_produce_ready_report(
    monkeypatch: MonkeyPatch,
) -> None:
    """Current migrations and healthy materialised state are ready."""

    inspection = _migration_inspection()

    _install_migration_inspection(
        monkeypatch,
        inspection,
    )

    counts = _healthy_counts()

    def fake_fetch_refdata_row_counts(
        connection: Connection[PostgresRow],
        *,
        schema: str,
    ) -> RefDataRowCounts:
        """Return healthy aggregate persisted-state observations."""

        del connection

        assert schema == "refdata_test_abc"

        return counts

    monkeypatch.setattr(
        diagnostics_module,
        "fetch_refdata_row_counts",
        fake_fetch_refdata_row_counts,
    )

    database = FakePostgresDatabase()
    reader = _healthy_reader()

    report = run_refdata_diagnostics(
        database=_as_database(database),
        reader=_as_reader(reader),
    )

    assert report.migration == inspection
    assert report.counts == counts
    assert report.ready is True

    assert all(result.status == "pass" for result in report.results)

    assert {result.name for result in report.results} == {
        "migration initialised",
        "migration current",
        "core reference data populated",
        "product provenance complete",
        "period cycles populated",
        "canonical cycle CALENDAR_MONTHS",
        "canonical cycle CALENDAR_QUARTERS",
    }


def test_count_inspection_failure_produces_not_ready_report(
    monkeypatch: MonkeyPatch,
) -> None:
    """Failure to observe materialised counts prevents readiness."""

    inspection = _migration_inspection()

    _install_migration_inspection(
        monkeypatch,
        inspection,
    )

    def failing_fetch_refdata_row_counts(
        connection: Connection[PostgresRow],
        *,
        schema: str,
    ) -> RefDataRowCounts:
        """Raise a representative persistence-observation failure."""

        del connection, schema

        raise RefDataDiagnosticsPersistenceError("could not interpret row-count result")

    monkeypatch.setattr(
        diagnostics_module,
        "fetch_refdata_row_counts",
        failing_fetch_refdata_row_counts,
    )

    database = FakePostgresDatabase()
    reader = _healthy_reader()

    report = run_refdata_diagnostics(
        database=_as_database(database),
        reader=_as_reader(reader),
    )

    assert report.migration == inspection
    assert report.counts is None
    assert report.ready is False

    count_result = _result_by_name(
        report.results,
        "materialised row counts",
    )

    assert count_result.status == "fail"
    assert "could not interpret row-count result" in count_result.message

    assert reader.cycle_lookup_calls == []
    assert reader.membership_lookup_calls == []
