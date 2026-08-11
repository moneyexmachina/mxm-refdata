"""Unit tests for the mxm-refdata CLI boundary."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from mxm.refdata.cli import _runtime_context, app
from mxm.refdata.diagnostics import (
    DiagnosticResult,
    RefDataDiagnosticReport,
)
from mxm.refdata.preflight import (
    PreflightCheck,
    PreflightReport,
)
from mxm.refdata.sql.diagnostics import RefDataRowCounts
from mxm.refdata.sql.migration_runner import MigrationInspection

runner = CliRunner()


def _ready_diagnostic_report() -> RefDataDiagnosticReport:
    """Construct one healthy diagnostic report for CLI tests."""

    return RefDataDiagnosticReport(
        migration=MigrationInspection(
            initialised=True,
            packaged_versions=("001_initial_refdata.sql",),
            applied_versions=("001_initial_refdata.sql",),
            pending_versions=(),
        ),
        counts=RefDataRowCounts(
            products=86,
            product_sources=86,
            periods=799,
            contracts=31_447,
            cycles=2,
            memberships=752,
        ),
        results=(
            DiagnosticResult(
                name="reference data materialised",
                status="pass",
            ),
        ),
    )


# ---------------------------------------------------------------------
# RUNTIME SELECTION
# ---------------------------------------------------------------------


def test_runtime_context_uses_environment_and_role(
    mocker: MockerFixture,
) -> None:
    """CLI runtime selection is translated into the MXM runtime identity."""

    identity = Mock(
        name="identity",
    )
    context = Mock(
        name="context",
    )

    build_identity = mocker.patch(
        "mxm.refdata.cli.build_runtime_identity",
        return_value=identity,
    )
    build_context = mocker.patch(
        "mxm.refdata.cli.build_runtime_context",
        return_value=context,
    )

    result = _runtime_context(
        environment="prod",
        role="admin",
    )

    assert result is context

    build_identity.assert_called_once_with(
        app="mxm-refdata",
        environment="prod",
        role="admin",
    )
    build_context.assert_called_once_with(
        identity=identity,
    )


# ---------------------------------------------------------------------
# MATERIALISATION COMMANDS
# ---------------------------------------------------------------------


def test_build_invokes_refdata_build(
    mocker: MockerFixture,
) -> None:
    """The build command invokes non-destructive materialisation."""

    refdata = Mock(
        name="refdata",
    )
    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["build"],
    )

    assert result.exit_code == 0
    refdata.build.assert_called_once_with()


def test_rebuild_invokes_refdata_rebuild(
    mocker: MockerFixture,
) -> None:
    """The rebuild command invokes destructive rematerialisation."""

    refdata = Mock(
        name="refdata",
    )
    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["rebuild"],
    )

    assert result.exit_code == 0
    refdata.rebuild.assert_called_once_with()


# ---------------------------------------------------------------------
# READ COMMANDS
# ---------------------------------------------------------------------


def test_products_uses_reader(
    mocker: MockerFixture,
) -> None:
    """The products command reads products through RefDataReader."""

    reader = Mock(
        name="reader",
    )
    reader.get_products.return_value = []

    refdata = Mock(
        name="refdata",
    )
    refdata.reader = reader

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["products"],
    )

    assert result.exit_code == 0
    reader.get_products.assert_called_once_with()


def test_product_uses_reader_lookup(
    mocker: MockerFixture,
) -> None:
    """The product command resolves one product through RefDataReader."""

    product_obj = Mock(
        name="product",
    )
    product_obj.product_id = "cme_test_futures"
    product_obj.venue = "CME"
    product_obj.description = "Test Futures"
    product_obj.currency.value = "USD"
    product_obj.unit.value = "index_points"
    product_obj.contract_size = 50.0
    product_obj.listing_rule = "Quarterly"
    product_obj.period_types = ()
    product_obj.settlement.value = "cash"
    product_obj.last_trading_rule = "last trading rule"
    product_obj.expiry_rule = "expiry rule"
    product_obj.trading_calendar = "CME"
    product_obj.tick_size = 0.25
    product_obj.tick_value = 12.5
    product_obj.valid_period_rule = "HMUZ"

    reader = Mock(
        name="reader",
    )
    reader.get_product_by_id.return_value = product_obj

    refdata = Mock(
        name="refdata",
    )
    refdata.reader = reader

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        [
            "product",
            "cme_test_futures",
        ],
    )

    assert result.exit_code == 0
    reader.get_product_by_id.assert_called_once_with("cme_test_futures")


def test_contracts_uses_reader_lookup(
    mocker: MockerFixture,
) -> None:
    """The contracts command reads product contracts through RefDataReader."""

    contract = Mock(
        name="contract",
    )
    contract.contract_id = "cme_test_futures.Mar-2025"
    contract.period_id = "Mar-2025"
    contract.first_day_of_interest = date(
        2024,
        1,
        1,
    )
    contract.last_trading_day = date(
        2025,
        3,
        20,
    )

    reader = Mock(
        name="reader",
    )
    reader.get_contracts_for_product.return_value = [
        contract,
    ]

    refdata = Mock(
        name="refdata",
    )
    refdata.reader = reader

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        [
            "contracts",
            "cme_test_futures",
        ],
    )

    assert result.exit_code == 0
    reader.get_contracts_for_product.assert_called_once_with("cme_test_futures")


def test_active_uses_parsed_date_and_optional_product_id(
    mocker: MockerFixture,
) -> None:
    """The active command parses its date and forwards product selection."""

    reader = Mock(
        name="reader",
    )
    reader.get_active_contracts.return_value = []

    refdata = Mock(
        name="refdata",
    )
    refdata.reader = reader

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        [
            "active",
            "2025-06-18",
            "--product-id",
            "cme_test_futures",
        ],
    )

    assert result.exit_code == 0
    reader.get_active_contracts.assert_called_once_with(
        date(
            2025,
            6,
            18,
        ),
        product_id="cme_test_futures",
    )


def test_active_rejects_invalid_date(
    mocker: MockerFixture,
) -> None:
    """An invalid active-contract date is rejected at the CLI boundary."""

    refdata = Mock(
        name="refdata",
    )

    refdata_builder = mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        [
            "active",
            "bad-date",
        ],
    )

    assert result.exit_code != 0
    assert "Expected date in YYYY-MM-DD format." in result.output
    refdata_builder.assert_not_called()


def test_coverage_uses_reader(
    mocker: MockerFixture,
) -> None:
    """The coverage command projects product contract coverage through Reader."""

    product_obj = Mock(
        name="product",
    )
    product_obj.product_id = "test_fut"
    product_obj.venue = "CME"

    contract_a = Mock(
        name="contract_a",
    )
    contract_a.contract_id = "test_fut.Jan-2025"

    contract_b = Mock(
        name="contract_b",
    )
    contract_b.contract_id = "test_fut.Feb-2025"

    reader = Mock(
        name="reader",
    )
    reader.get_products.return_value = [
        product_obj,
    ]
    reader.get_contracts_for_product.return_value = [
        contract_a,
        contract_b,
    ]

    refdata = Mock(
        name="refdata",
    )
    refdata.reader = reader

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["coverage"],
    )

    assert result.exit_code == 0

    reader.get_products.assert_called_once_with()
    reader.get_contracts_for_product.assert_called_once_with("test_fut")


def test_environment_and_role_are_passed_to_refdata(
    mocker: MockerFixture,
) -> None:
    """Normal commands forward runtime selection to the RefData helper."""

    reader = Mock(
        name="reader",
    )
    reader.get_products.return_value = []

    refdata = Mock(
        name="refdata",
    )
    refdata.reader = reader

    build_refdata = mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        [
            "products",
            "--environment",
            "prod",
            "--role",
            "admin",
        ],
    )

    assert result.exit_code == 0

    build_refdata.assert_called_once_with(
        environment="prod",
        role="admin",
    )


# ---------------------------------------------------------------------
# SMOKECHECK
# ---------------------------------------------------------------------


def test_smokecheck_exits_successfully_when_diagnostics_are_ready(
    mocker: MockerFixture,
) -> None:
    """Healthy diagnostics render successfully and produce exit code zero."""

    report = _ready_diagnostic_report()

    refdata = Mock(
        name="refdata",
    )
    refdata.diagnostics.return_value = report

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["smokecheck"],
    )

    assert result.exit_code == 0
    refdata.diagnostics.assert_called_once_with()

    assert "Migrations:" in result.output
    assert "Counts:" in result.output
    assert "products=86" in result.output


def test_smokecheck_exits_unsuccessfully_when_diagnostics_are_not_ready(
    mocker: MockerFixture,
) -> None:
    """A non-ready diagnostic report produces a failing process exit."""

    report = RefDataDiagnosticReport(
        migration=MigrationInspection(
            initialised=True,
            packaged_versions=("001_initial_refdata.sql",),
            applied_versions=("001_initial_refdata.sql",),
            pending_versions=(),
        ),
        counts=RefDataRowCounts(
            products=0,
            product_sources=0,
            periods=0,
            contracts=0,
            cycles=0,
            memberships=0,
        ),
        results=(
            DiagnosticResult(
                name="products populated",
                status="fail",
                message="No products are materialised.",
            ),
        ),
    )

    refdata = Mock(
        name="refdata",
    )
    refdata.diagnostics.return_value = report

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["smokecheck"],
    )

    assert result.exit_code == 1
    refdata.diagnostics.assert_called_once_with()
    assert "FAIL" in result.output


def test_smokecheck_handles_unavailable_diagnostic_observations(
    mocker: MockerFixture,
) -> None:
    """Unavailable migration and row-count observations render without crashing."""

    report = RefDataDiagnosticReport(
        migration=None,
        counts=None,
        results=(
            DiagnosticResult(
                name="migration inspection",
                status="fail",
                message="PostgreSQL unavailable.",
            ),
        ),
    )

    refdata = Mock(
        name="refdata",
    )
    refdata.diagnostics.return_value = report

    mocker.patch(
        "mxm.refdata.cli._refdata",
        return_value=refdata,
    )

    result = runner.invoke(
        app,
        ["smokecheck"],
    )

    assert result.exit_code == 1
    assert "Migrations: unavailable" in result.output
    assert "Counts: unavailable" in result.output


# ---------------------------------------------------------------------
# PREFLIGHT
# ---------------------------------------------------------------------


def test_preflight_exits_successfully_when_report_passes(
    mocker: MockerFixture,
) -> None:
    """A passing preflight report produces exit code zero."""

    context = Mock(
        name="runtime_context",
    )

    report = PreflightReport(
        checks=(
            PreflightCheck(
                name="application composed",
                passed=True,
            ),
            PreflightCheck(
                name="product source root available",
                passed=True,
                message="/tmp/products",
            ),
            PreflightCheck(
                name="database reachable",
                passed=True,
            ),
        )
    )

    runtime_context = mocker.patch(
        "mxm.refdata.cli._runtime_context",
        return_value=context,
    )
    run_preflight = mocker.patch(
        "mxm.refdata.cli.run_preflight",
        return_value=report,
    )

    result = runner.invoke(
        app,
        ["preflight"],
    )

    assert result.exit_code == 0

    runtime_context.assert_called_once_with(
        environment="dev",
        role="default",
    )
    run_preflight.assert_called_once_with(context)


def test_preflight_exits_unsuccessfully_when_report_fails(
    mocker: MockerFixture,
) -> None:
    """A failing preflight report produces a failing process exit."""

    context = Mock(
        name="runtime_context",
    )

    report = PreflightReport(
        checks=(
            PreflightCheck(
                name="application composed",
                passed=True,
            ),
            PreflightCheck(
                name="product source root available",
                passed=True,
                message="/tmp/products",
            ),
            PreflightCheck(
                name="database reachable",
                passed=False,
                message="ConnectionError: database unavailable",
            ),
        )
    )

    mocker.patch(
        "mxm.refdata.cli._runtime_context",
        return_value=context,
    )
    run_preflight = mocker.patch(
        "mxm.refdata.cli.run_preflight",
        return_value=report,
    )

    result = runner.invoke(
        app,
        ["preflight"],
    )

    assert result.exit_code == 1
    run_preflight.assert_called_once_with(context)
    assert "FAIL" in result.output
    assert "database reachable" in result.output
