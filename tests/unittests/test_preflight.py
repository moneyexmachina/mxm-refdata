"""Unit tests for MXM reference-data operational preflight."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pytest_mock import MockerFixture

from mxm.config import MXMConfig
from mxm.refdata.preflight import (
    PreflightCheck,
    PreflightReport,
    run_preflight,
)
from mxm.refdata.reader import RefDataReader
from mxm.refdata.runtime import RefData
from mxm.refdata.sql.postgres import PostgresDatabase
from mxm.runtime import RuntimeContext


class FakeDatabase:
    """Minimal database capability used by preflight unit tests."""

    def __init__(
        self,
        *,
        reachable: bool = True,
        error: Exception | None = None,
    ) -> None:
        self.reachable = reachable
        self.error = error
        self.check_connection_calls = 0

    def check_connection(self) -> bool:
        """Return or fail the configured connectivity observation."""

        self.check_connection_calls += 1

        if self.error is not None:
            raise self.error

        return self.reachable


def _make_refdata(
    *,
    source_root: Path,
    database: FakeDatabase,
) -> RefData:
    """Construct the minimal real RefData façade needed by preflight."""

    config = cast(
        MXMConfig,
        {
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(source_root),
        },
    )

    return RefData(
        config=config,
        database=cast(
            PostgresDatabase,
            database,
        ),
        reader=cast(
            RefDataReader,
            object(),
        ),
    )


def test_preflight_passes_when_operational_prerequisites_are_available(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """A composed application with source data and PostgreSQL passes preflight."""

    source_root = tmp_path / "products"
    source_root.mkdir()

    database = FakeDatabase(
        reachable=True,
    )
    refdata = _make_refdata(
        source_root=source_root,
        database=database,
    )

    ctx = mocker.Mock(
        spec=RuntimeContext,
    )
    build_refdata = mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        return_value=refdata,
    )

    report = run_preflight(
        ctx,
    )

    assert report == PreflightReport(
        checks=(
            PreflightCheck(
                name="application composed",
                passed=True,
            ),
            PreflightCheck(
                name="product source root available",
                passed=True,
                message=str(source_root),
            ),
            PreflightCheck(
                name="database reachable",
                passed=True,
            ),
        )
    )

    assert report.passed is True
    assert database.check_connection_calls == 1
    build_refdata.assert_called_once_with(
        ctx,
    )


def test_preflight_stops_when_application_cannot_be_composed(
    mocker: MockerFixture,
) -> None:
    """Composition failure prevents checks that require a RefData instance."""

    ctx = mocker.Mock(
        spec=RuntimeContext,
    )

    mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        side_effect=RuntimeError("database configuration missing"),
    )

    report = run_preflight(
        ctx,
    )

    assert report == PreflightReport(
        checks=(
            PreflightCheck(
                name="application composed",
                passed=False,
                message=("RuntimeError: database configuration missing"),
            ),
        )
    )

    assert report.passed is False


def test_preflight_reports_missing_source_root_and_continues(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Missing source data does not prevent independent database inspection."""

    source_root = tmp_path / "missing-products"

    database = FakeDatabase(
        reachable=True,
    )
    refdata = _make_refdata(
        source_root=source_root,
        database=database,
    )

    mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        return_value=refdata,
    )

    ctx = mocker.Mock(
        spec=RuntimeContext,
    )

    report = run_preflight(
        ctx,
    )

    assert report.checks == (
        PreflightCheck(
            name="application composed",
            passed=True,
        ),
        PreflightCheck(
            name="product source root available",
            passed=False,
            message=str(source_root),
        ),
        PreflightCheck(
            name="database reachable",
            passed=True,
        ),
    )

    assert report.passed is False
    assert database.check_connection_calls == 1


def test_preflight_reports_unsuccessful_database_check(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """A negative connectivity observation fails database preflight."""

    source_root = tmp_path / "products"
    source_root.mkdir()

    database = FakeDatabase(
        reachable=False,
    )
    refdata = _make_refdata(
        source_root=source_root,
        database=database,
    )

    mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        return_value=refdata,
    )

    ctx = mocker.Mock(
        spec=RuntimeContext,
    )

    report = run_preflight(
        ctx,
    )

    assert report.checks[-1] == PreflightCheck(
        name="database reachable",
        passed=False,
    )

    assert report.passed is False
    assert database.check_connection_calls == 1


def test_preflight_reports_database_connection_error(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Database exceptions become operational preflight failures."""

    source_root = tmp_path / "products"
    source_root.mkdir()

    database = FakeDatabase(
        error=ConnectionError("database unavailable"),
    )
    refdata = _make_refdata(
        source_root=source_root,
        database=database,
    )

    mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        return_value=refdata,
    )

    ctx = mocker.Mock(
        spec=RuntimeContext,
    )

    report = run_preflight(
        ctx,
    )

    assert report.checks[-1] == PreflightCheck(
        name="database reachable",
        passed=False,
        message=("ConnectionError: database unavailable"),
    )

    assert report.passed is False
    assert database.check_connection_calls == 1
