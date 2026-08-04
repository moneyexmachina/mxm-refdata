"""Tests for mxm-refdata operational preflight checks."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from mxm.config import MXMConfig, make_subconfig
from mxm.refdata.preflight import (
    PreflightCheck,
    PreflightReport,
    run_preflight,
)
from mxm.runtime import RuntimeContext, RuntimePaths
from mxm.secrets import SecretsApi
from mxm.types import RuntimeIdentity


def _make_runtime_context(
    *,
    mocker: MockerFixture,
    paths: RuntimePaths | None,
) -> RuntimeContext:
    """Construct an explicit RuntimeContext for preflight tests."""
    return RuntimeContext(
        identity=RuntimeIdentity(
            app="mxm-refdata",
            environment="dev",
            machine="monolith",
            substrate="local-process",
            role="default",
        ),
        config=make_subconfig({}),
        secrets=cast(SecretsApi, mocker.Mock(spec=SecretsApi)),
        db_configs=cast(MXMConfig, {}),
        paths=paths,
    )


@pytest.fixture
def runtime_paths(tmp_path: Path) -> RuntimePaths:
    """Provide existing runtime filesystem roots."""
    data_root = tmp_path / "data"
    artifact_root = tmp_path / "artifacts"
    export_root = tmp_path / "exports"
    log_root = tmp_path / "logs"

    for path in (
        data_root,
        artifact_root,
        export_root,
        log_root,
    ):
        path.mkdir()

    return RuntimePaths(
        data_root=data_root,
        artifact_root=artifact_root,
        export_root=export_root,
        log_root=log_root,
    )


@pytest.fixture
def runtime_context(
    mocker: MockerFixture,
    runtime_paths: RuntimePaths,
) -> RuntimeContext:
    """Provide a RuntimeContext with valid filesystem roots."""
    return _make_runtime_context(
        mocker=mocker,
        paths=runtime_paths,
    )


def _get_check(
    report: PreflightReport,
    name: str,
) -> PreflightCheck:
    """Retrieve one named check from a preflight report."""
    matches = [check for check in report.checks if check.name == name]

    assert len(matches) == 1
    return matches[0]


def _patch_refdata(
    mocker: MockerFixture,
    *,
    database_reachable: bool = True,
) -> Mock:
    """Patch application composition with a controllable database result."""
    session_manager = Mock()
    session_manager.check_db_connection.return_value = database_reachable

    refdata = Mock()
    refdata.session_manager = session_manager

    mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        return_value=refdata,
    )

    return refdata


def test_report_passes_only_when_every_check_passes() -> None:
    """A preflight report should pass only when all checks pass."""
    passing = PreflightReport(
        checks=(
            PreflightCheck("first", True),
            PreflightCheck("second", True),
        )
    )
    failing = PreflightReport(
        checks=(
            PreflightCheck("first", True),
            PreflightCheck("second", False, "failed"),
        )
    )

    assert passing.passed
    assert not failing.passed


def test_preflight_expands_product_source_tilde(
    runtime_context: RuntimeContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """The configured product source should support user-relative paths."""
    monkeypatch.setenv("HOME", str(tmp_path))

    source_root = tmp_path / "mxm-refdata-source" / "products" / "futures"
    source_root.mkdir(parents=True)

    mocker.patch(
        "mxm.refdata.preflight.make_view",
        return_value=cast(
            MXMConfig,
            {
                "SQL_DB_URL": ("postgresql://mxm_dev_app@example.invalid/mxm_dev"),
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": (
                    "~/mxm-refdata-source/products/futures"
                ),
            },
        ),
    )
    _patch_refdata(mocker)

    report = run_preflight(runtime_context)

    check = _get_check(report, "product source root available")

    assert check.passed
    assert check.message == str(source_root)


def test_preflight_reports_missing_runtime_paths(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Missing RuntimeContext paths should be an explicit preflight failure."""
    source_root = tmp_path / "products" / "futures"
    source_root.mkdir(parents=True)

    runtime_context = _make_runtime_context(
        mocker=mocker,
        paths=None,
    )

    mocker.patch(
        "mxm.refdata.preflight.make_view",
        return_value=cast(
            MXMConfig,
            {
                "SQL_DB_URL": ("postgresql://mxm_dev_app@example.invalid/mxm_dev"),
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(source_root),
            },
        ),
    )

    report = run_preflight(runtime_context)

    check = _get_check(report, "runtime filesystem paths resolved")

    assert not report.passed
    assert not check.passed
    assert check.message == "RuntimeContext.paths is not available"


def test_preflight_reports_application_composition_failure(
    runtime_context: RuntimeContext,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Composition errors should become inspectable failed checks."""
    source_root = tmp_path / "products" / "futures"
    source_root.mkdir(parents=True)

    mocker.patch(
        "mxm.refdata.preflight.make_view",
        return_value=cast(
            MXMConfig,
            {
                "SQL_DB_URL": ("postgresql://mxm_dev_app@example.invalid/mxm_dev"),
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(source_root),
            },
        ),
    )
    mocker.patch(
        "mxm.refdata.preflight.build_refdata",
        side_effect=ValueError("invalid product specification"),
    )

    report = run_preflight(runtime_context)

    check = _get_check(report, "application composed")

    assert not report.passed
    assert not check.passed
    assert check.message == "ValueError: invalid product specification"
    assert not any(item.name == "database reachable" for item in report.checks)


def test_preflight_rejects_sqlite_as_operational_backend(
    runtime_context: RuntimeContext,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """A reachable SQLite database should still fail PostgreSQL selection."""
    source_root = tmp_path / "products" / "futures"
    source_root.mkdir(parents=True)

    sqlite_path = tmp_path / "refdata-dev.db"

    mocker.patch(
        "mxm.refdata.preflight.make_view",
        return_value=cast(
            MXMConfig,
            {
                "SQL_DB_URL": f"sqlite:///{sqlite_path}",
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(source_root),
            },
        ),
    )
    _patch_refdata(
        mocker,
        database_reachable=True,
    )

    report = run_preflight(runtime_context)

    backend_check = _get_check(report, "PostgreSQL selected")
    connectivity_check = _get_check(report, "database reachable")

    assert not report.passed
    assert not backend_check.passed
    assert backend_check.message.startswith("sqlite:///")
    assert connectivity_check.passed


def test_preflight_accepts_postgresql_backend(
    runtime_context: RuntimeContext,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """A reachable PostgreSQL target should pass database preflight checks."""
    source_root = tmp_path / "products" / "futures"
    source_root.mkdir(parents=True)

    mocker.patch(
        "mxm.refdata.preflight.make_view",
        return_value=cast(
            MXMConfig,
            {
                "SQL_DB_URL": (
                    "postgresql://mxm_dev_app:secret"
                    "@postgres.example.invalid:5432/mxm_dev"
                ),
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(source_root),
            },
        ),
    )
    _patch_refdata(
        mocker,
        database_reachable=True,
    )

    report = run_preflight(runtime_context)

    backend_check = _get_check(report, "PostgreSQL selected")
    connectivity_check = _get_check(report, "database reachable")

    assert report.passed
    assert backend_check.passed
    assert connectivity_check.passed
    assert "secret" not in backend_check.message
    assert "***" in backend_check.message


def test_preflight_reports_database_connectivity_failure(
    runtime_context: RuntimeContext,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """An unreachable PostgreSQL target should fail preflight cleanly."""
    source_root = tmp_path / "products" / "futures"
    source_root.mkdir(parents=True)

    mocker.patch(
        "mxm.refdata.preflight.make_view",
        return_value=cast(
            MXMConfig,
            {
                "SQL_DB_URL": (
                    "postgresql://mxm_dev_app:secret"
                    "@postgres.example.invalid:5432/mxm_dev"
                ),
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(source_root),
            },
        ),
    )
    _patch_refdata(
        mocker,
        database_reachable=False,
    )

    report = run_preflight(runtime_context)

    backend_check = _get_check(report, "PostgreSQL selected")
    connectivity_check = _get_check(report, "database reachable")

    assert not report.passed
    assert backend_check.passed
    assert not connectivity_check.passed
    assert "secret" not in connectivity_check.message
