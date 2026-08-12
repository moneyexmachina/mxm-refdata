"""Integration tests for application-level reference-data diagnostics.

These tests exercise ``run_refdata_diagnostics`` against real PostgreSQL
states using the normal migration, materialisation, SQL-diagnostic, and Reader
boundaries.

They prove that diagnostics correctly distinguishes an uninitialised schema,
a migrated but empty schema, a healthy materialised reference-data state, and
a deliberately degraded materialised state.

Detailed diagnostic policy branches and error-message construction are tested
separately by the diagnostics unit tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from psycopg import sql

from mxm.config import MXMConfig
from mxm.refdata.diagnostics import (
    DiagnosticResult,
    run_refdata_diagnostics,
)
from mxm.refdata.materialisation import build_refdata
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sql.diagnostics import RefDataRowCounts
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres

_FIXTURE_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "futures_products"
)

_EXPECTED_HEALTHY_COUNTS = RefDataRowCounts(
    products=1,
    product_sources=1,
    periods=17,
    contracts=4,
    cycles=2,
    memberships=16,
)

_EXPECTED_DIAGNOSTIC_NAMES = {
    "migration initialised",
    "migration current",
    "core reference data populated",
    "product provenance complete",
    "period cycles populated",
    "canonical cycle CALENDAR_MONTHS",
    "canonical cycle CALENDAR_QUARTERS",
}


def _config() -> MXMConfig:
    """Return the controlled configuration for diagnostic integration."""

    return cast(
        MXMConfig,
        {
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(_FIXTURE_SOURCE_ROOT),
            "REFDATA_CONTRACT_START_DATE": "2024-01-01",
            "REFDATA_CONTRACT_END_DATE": "2024-12-31",
        },
    )


def _reader(
    database: PostgresDatabase,
) -> RefDataReader:
    """Construct the real Reader for one integration-test database."""

    return RefDataReader(
        database=database,
    )


def _materialise(
    database: PostgresDatabase,
) -> RefDataReader:
    """Materialise the synthetic universe and return its real Reader."""

    build_refdata(
        config=_config(),
        database=database,
    )

    return _reader(database)


def _result_by_name(
    results: tuple[DiagnosticResult, ...],
    name: str,
) -> DiagnosticResult:
    """Return exactly one diagnostic result with the requested stable name."""

    matches = [result for result in results if result.name == name]

    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly one diagnostic result named {name!r}, got {matches!r}."
        )

    return matches[0]


def test_diagnostics_reports_uninitialised_schema_as_not_ready(
    postgres_database: PostgresDatabase,
) -> None:
    """An unmigrated PostgreSQL schema fails the migration readiness gate."""

    database = postgres_database
    reader = _reader(database)

    report = run_refdata_diagnostics(
        database=database,
        reader=reader,
    )

    assert report.migration is not None
    assert report.migration.initialised is False
    assert report.counts is None
    assert report.ready is False

    assert report.results == (
        DiagnosticResult(
            name="migration initialised",
            status="fail",
            message="Reference-data schema has not been initialised.",
        ),
    )


def test_diagnostics_reports_migrated_empty_schema_as_not_ready(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """A current but empty schema is inspectable but not operationally ready."""

    database = migrated_postgres_database
    reader = _reader(database)

    report = run_refdata_diagnostics(
        database=database,
        reader=reader,
    )

    assert report.migration is not None
    assert report.migration.initialised is True
    assert report.migration.current is True

    assert report.counts == RefDataRowCounts(
        products=0,
        product_sources=0,
        periods=0,
        contracts=0,
        cycles=0,
        memberships=0,
    )

    assert report.ready is False

    assert {result.name for result in report.results} == _EXPECTED_DIAGNOSTIC_NAMES

    assert (
        _result_by_name(
            report.results,
            "migration initialised",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "migration current",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "core reference data populated",
        ).status
        == "fail"
    )

    assert (
        _result_by_name(
            report.results,
            "product provenance complete",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "period cycles populated",
        ).status
        == "fail"
    )

    assert (
        _result_by_name(
            report.results,
            "canonical cycle CALENDAR_MONTHS",
        ).status
        == "fail"
    )

    assert (
        _result_by_name(
            report.results,
            "canonical cycle CALENDAR_QUARTERS",
        ).status
        == "fail"
    )


def test_diagnostics_reports_materialised_synthetic_state_as_ready(
    postgres_database: PostgresDatabase,
) -> None:
    """Complete synthetic reference data satisfies all readiness diagnostics."""

    database = postgres_database
    reader = _materialise(database)

    report = run_refdata_diagnostics(
        database=database,
        reader=reader,
    )

    assert report.migration is not None
    assert report.migration.initialised is True
    assert report.migration.current is True

    assert report.counts == _EXPECTED_HEALTHY_COUNTS

    assert {result.name for result in report.results} == _EXPECTED_DIAGNOSTIC_NAMES

    assert all(result.status == "pass" for result in report.results)

    assert report.ready is True


def test_diagnostics_detects_incomplete_product_provenance(
    postgres_database: PostgresDatabase,
) -> None:
    """Diagnostics detects provenance removed from otherwise healthy state."""

    database = postgres_database
    reader = _materialise(database)

    delete_provenance_query = sql.SQL("DELETE FROM {}").format(
        sql.Identifier(
            database.schema,
            "futures_product_sources",
        )
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(delete_provenance_query)

    report = run_refdata_diagnostics(
        database=database,
        reader=reader,
    )

    assert report.migration is not None
    assert report.migration.current is True

    assert report.counts == RefDataRowCounts(
        products=1,
        product_sources=0,
        periods=17,
        contracts=4,
        cycles=2,
        memberships=16,
    )

    assert report.ready is False

    assert (
        _result_by_name(
            report.results,
            "migration initialised",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "migration current",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "core reference data populated",
        ).status
        == "pass"
    )

    provenance_result = _result_by_name(
        report.results,
        "product provenance complete",
    )

    assert provenance_result.status == "fail"
    assert "products=1" in provenance_result.message
    assert "product_sources=0" in provenance_result.message

    assert (
        _result_by_name(
            report.results,
            "period cycles populated",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "canonical cycle CALENDAR_MONTHS",
        ).status
        == "pass"
    )

    assert (
        _result_by_name(
            report.results,
            "canonical cycle CALENDAR_QUARTERS",
        ).status
        == "pass"
    )
