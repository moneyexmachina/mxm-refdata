"""Application-level diagnostics for materialised MXM reference data.

This module combines read-only observations from the migration subsystem,
plain-SQL diagnostic queries, and the public ``RefDataReader`` capability.

It interprets those observations as operational readiness. It does not
migrate, build, rebuild, repair, or otherwise modify reference-data state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mxm.refdata.models import PeriodType
from mxm.refdata.models.period_cycles import CycleInstanceKind
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sql.diagnostics import (
    RefDataDiagnosticsPersistenceError,
    RefDataRowCounts,
    fetch_refdata_row_counts,
)
from mxm.refdata.sql.migration_runner import (
    MigrationError,
    MigrationInspection,
    MigrationRunner,
)
from mxm.refdata.sql.postgres import PostgresDatabase

__all__ = [
    "DiagnosticResult",
    "RefDataDiagnosticReport",
    "run_refdata_diagnostics",
]

type DiagnosticStatus = Literal[
    "pass",
    "fail",
]

CYCLE_ID_CALENDAR_MONTHS = "CALENDAR_MONTHS"
CYCLE_ID_CALENDAR_QUARTERS = "CALENDAR_QUARTERS"


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    """Result of one operational reference-data diagnostic check."""

    name: str
    status: DiagnosticStatus
    message: str = ""


@dataclass(frozen=True, slots=True)
class RefDataDiagnosticReport:
    """Aggregate diagnostic state for materialised reference data.

    ``migration`` is absent when migration inspection itself fails.

    ``counts`` is absent when the schema is not initialised, migrations are
    not current, or materialised row counts cannot be inspected safely.
    """

    migration: MigrationInspection | None
    counts: RefDataRowCounts | None
    results: tuple[DiagnosticResult, ...]

    @property
    def ready(self) -> bool:
        """Return whether reference data is operationally ready."""

        return (
            self.migration is not None
            and self.migration.current
            and self.counts is not None
            and all(result.status == "pass" for result in self.results)
        )


@dataclass(frozen=True, slots=True)
class _CanonicalCycleExpectation:
    """Expected structure of one canonical materialised period cycle."""

    cycle_id: str
    period_type: PeriodType
    cycle_size: int
    instance_kind: CycleInstanceKind


_CANONICAL_CYCLES = (
    _CanonicalCycleExpectation(
        cycle_id=CYCLE_ID_CALENDAR_MONTHS,
        period_type=PeriodType.MONTH,
        cycle_size=12,
        instance_kind=CycleInstanceKind.YEAR,
    ),
    _CanonicalCycleExpectation(
        cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
        period_type=PeriodType.QUARTER,
        cycle_size=4,
        instance_kind=CycleInstanceKind.YEAR,
    ),
)


def run_refdata_diagnostics(
    *,
    database: PostgresDatabase,
    reader: RefDataReader,
) -> RefDataDiagnosticReport:
    """Inspect materialised reference data and determine readiness.

    Migration state is inspected first because an absent or outdated schema
    cannot safely be assumed to expose the current materialised table shape.

    Once migrations are current, aggregate persisted-state observations are
    collected through ``sql.diagnostics`` and canonical domain state is
    inspected through ``RefDataReader``.

    The operation is strictly read-only.
    """

    results: list[DiagnosticResult] = []

    try:
        migration = MigrationRunner(
            database,
        ).inspect()
    except MigrationError as err:
        return RefDataDiagnosticReport(
            migration=None,
            counts=None,
            results=(
                _fail(
                    "migration state",
                    str(err),
                ),
            ),
        )

    results.append(
        _check_migration_initialised(
            migration,
        )
    )

    if not migration.initialised:
        return RefDataDiagnosticReport(
            migration=migration,
            counts=None,
            results=tuple(results),
        )

    results.append(
        _check_migration_current(
            migration,
        )
    )

    if not migration.current:
        return RefDataDiagnosticReport(
            migration=migration,
            counts=None,
            results=tuple(results),
        )

    try:
        with database.transaction() as connection:
            counts = fetch_refdata_row_counts(
                connection,
                schema=database.schema,
            )
    except RefDataDiagnosticsPersistenceError as err:
        results.append(
            _fail(
                "materialised row counts",
                str(err),
            )
        )

        return RefDataDiagnosticReport(
            migration=migration,
            counts=None,
            results=tuple(results),
        )

    results.extend(
        _check_materialised_counts(
            counts,
        )
    )

    results.extend(
        _check_canonical_cycles(
            reader,
        )
    )

    return RefDataDiagnosticReport(
        migration=migration,
        counts=counts,
        results=tuple(results),
    )


def _check_migration_initialised(
    migration: MigrationInspection,
) -> DiagnosticResult:
    """Check whether migration bootstrap has initialised the schema."""

    if not migration.initialised:
        return _fail(
            "migration initialised",
            "Reference-data schema has not been initialised.",
        )

    return _pass(
        "migration initialised",
    )


def _check_migration_current(
    migration: MigrationInspection,
) -> DiagnosticResult:
    """Check whether every packaged migration has been applied."""

    if migration.current:
        return _pass(
            "migration current",
        )

    pending = ", ".join(migration.pending_versions)

    return _fail(
        "migration current",
        f"Reference-data schema has pending migrations: {pending or 'unknown'}.",
    )


def _check_materialised_counts(
    counts: RefDataRowCounts,
) -> tuple[DiagnosticResult, ...]:
    """Interpret aggregate materialised row counts."""

    results: list[DiagnosticResult] = []

    missing_core_tables: list[str] = []

    if counts.products == 0:
        missing_core_tables.append("futures_products")

    if counts.periods == 0:
        missing_core_tables.append("periods")

    if counts.contracts == 0:
        missing_core_tables.append("futures_contracts")

    if missing_core_tables:
        results.append(
            _fail(
                "core reference data populated",
                "No materialised rows found in: "
                + ", ".join(missing_core_tables)
                + ".",
            )
        )
    else:
        results.append(
            _pass(
                "core reference data populated",
            )
        )

    if counts.product_sources != counts.products:
        results.append(
            _fail(
                "product provenance complete",
                "Futures-product provenance count does not match "
                "operational product count: "
                f"products={counts.products}, "
                f"product_sources={counts.product_sources}.",
            )
        )
    else:
        results.append(
            _pass(
                "product provenance complete",
            )
        )

    missing_cycle_tables: list[str] = []

    if counts.cycles == 0:
        missing_cycle_tables.append("period_cycles")

    if counts.memberships == 0:
        missing_cycle_tables.append("period_cycle_memberships")

    if missing_cycle_tables:
        results.append(
            _fail(
                "period cycles populated",
                "No materialised rows found in: "
                + ", ".join(missing_cycle_tables)
                + ".",
            )
        )
    else:
        results.append(
            _pass(
                "period cycles populated",
            )
        )

    return tuple(results)


def _check_canonical_cycles(
    reader: RefDataReader,
) -> tuple[DiagnosticResult, ...]:
    """Verify canonical calendar cycles through the read capability."""

    return tuple(
        _check_canonical_cycle(
            reader,
            expectation=expectation,
        )
        for expectation in _CANONICAL_CYCLES
    )


def _check_canonical_cycle(
    reader: RefDataReader,
    *,
    expectation: _CanonicalCycleExpectation,
) -> DiagnosticResult:
    """Verify one canonical cycle and its materialised memberships."""

    cycle = reader.get_cycle_by_id(
        expectation.cycle_id,
    )

    if cycle is None:
        return _fail(
            f"canonical cycle {expectation.cycle_id}",
            "Canonical period cycle is missing.",
        )

    mismatches: list[str] = []

    if cycle.period_type is not expectation.period_type:
        mismatches.append(
            "period_type="
            f"{cycle.period_type.value!r} "
            f"(expected {expectation.period_type.value!r})"
        )

    if cycle.cycle_size != expectation.cycle_size:
        mismatches.append(
            f"cycle_size={cycle.cycle_size!r} (expected {expectation.cycle_size!r})"
        )

    if cycle.instance_kind is not expectation.instance_kind:
        mismatches.append(
            "instance_kind="
            f"{cycle.instance_kind.value!r} "
            f"(expected {expectation.instance_kind.value!r})"
        )

    if mismatches:
        return _fail(
            f"canonical cycle {expectation.cycle_id}",
            "Canonical period-cycle structure is invalid: "
            + "; ".join(mismatches)
            + ".",
        )

    memberships = reader.get_cycle_memberships(
        expectation.cycle_id,
    )

    if not memberships:
        return _fail(
            f"canonical cycle {expectation.cycle_id}",
            "Canonical period cycle has no memberships.",
        )

    return _pass(
        f"canonical cycle {expectation.cycle_id}",
    )


def _pass(
    name: str,
) -> DiagnosticResult:
    """Construct one successful diagnostic result."""

    return DiagnosticResult(
        name=name,
        status="pass",
    )


def _fail(
    name: str,
    message: str,
) -> DiagnosticResult:
    """Construct one failed diagnostic result."""

    return DiagnosticResult(
        name=name,
        status="fail",
        message=message,
    )
