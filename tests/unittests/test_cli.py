"""Unit tests for the mxm-refdata CLI boundary."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from mxm.refdata.cli import app

runner = CliRunner()


def test_build_invokes_refdata_build(mocker: MockerFixture) -> None:
    refdata = Mock()
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["build", "--environment", "dev", "--role", "default"])

    assert result.exit_code == 0
    refdata.build.assert_called_once_with()


def test_rebuild_invokes_refdata_rebuild(mocker: MockerFixture) -> None:
    refdata = Mock()
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(
        app, ["rebuild", "--environment", "dev", "--role", "default"]
    )

    assert result.exit_code == 0
    refdata.rebuild.assert_called_once_with()


def test_refdata_helper_builds_runtime_identity_context_and_refdata(
    mocker: MockerFixture,
) -> None:
    identity = Mock()
    ctx = Mock()
    refdata = Mock()

    build_identity = mocker.patch(
        "mxm.refdata.cli.build_runtime_identity",
        return_value=identity,
    )
    build_context = mocker.patch(
        "mxm.refdata.cli.build_runtime_context",
        return_value=ctx,
    )
    build_refdata = mocker.patch(
        "mxm.refdata.cli.build_refdata",
        return_value=refdata,
    )

    from mxm.refdata.cli import _refdata

    result = _refdata(environment="prod", role="admin")

    assert result is refdata
    build_identity.assert_called_once_with(
        app="mxm-refdata",
        environment="prod",
        role="admin",
    )
    build_context.assert_called_once_with(identity=identity)
    build_refdata.assert_called_once_with(ctx)


def test_products_uses_refdata_runtime(mocker: MockerFixture) -> None:
    refdata = Mock()
    refdata.get_all_products.return_value = []
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["products"])

    assert result.exit_code == 0
    refdata.get_all_products.assert_called_once_with()


def test_product_uses_refdata_lookup(mocker: MockerFixture) -> None:
    product = Mock()
    product.product_id = "cme_test_futures"
    product.venue = "CME"
    product.description = "Test Futures"
    product.currency.value = "USD"
    product.unit.value = "index_points"
    product.contract_size = 50.0
    product.listing_rule = "Quarterly"
    product.period_types = []
    product.settlement.value = "cash"
    product.last_trading_rule = "rule"
    product.expiry_rule = "rule"
    product.trading_calendar = "CME"
    product.tick_size = 0.25
    product.tick_value = 12.5
    product.valid_period_rule = "HMUZ"

    refdata = Mock()
    refdata.get_product_by_id.return_value = product
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["product", "cme_test_futures"])

    assert result.exit_code == 0
    refdata.get_product_by_id.assert_called_once_with("cme_test_futures")


def test_contracts_uses_refdata_lookup(mocker: MockerFixture) -> None:
    contract = Mock()
    contract.contract_id = "cme_test_futures.Mar-2025"
    contract.period_id = "Mar-2025"
    contract.first_day_of_interest = date(2024, 1, 1)
    contract.last_trading_day = date(2025, 3, 20)

    refdata = Mock()
    refdata.get_contracts_for_product.return_value = [contract]
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["contracts", "cme_test_futures"])

    assert result.exit_code == 0
    refdata.get_contracts_for_product.assert_called_once_with("cme_test_futures")


def test_active_uses_parsed_date_and_optional_product_id(
    mocker: MockerFixture,
) -> None:
    refdata = Mock()
    refdata.get_active_contracts.return_value = []
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

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
    refdata.get_active_contracts.assert_called_once_with(
        date(2025, 6, 18),
        product_id="cme_test_futures",
    )


def test_active_rejects_invalid_date(mocker: MockerFixture) -> None:
    refdata = Mock()
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["active", "bad-date"])

    assert result.exit_code != 0
    assert "Expected date in YYYY-MM-DD format" in result.output
    refdata.get_active_contracts.assert_not_called()


def test_coverage_uses_refdata_runtime(mocker: MockerFixture) -> None:
    product = Mock()
    product.product_id = "test_fut"
    product.venue = "CME"

    contract_a = Mock()
    contract_a.contract_id = "test_fut.Jan-2025"
    contract_b = Mock()
    contract_b.contract_id = "test_fut.Feb-2025"

    refdata = Mock()
    refdata.get_all_products.return_value = [product]
    refdata.get_contracts_for_product.return_value = [contract_a, contract_b]
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["coverage"])

    assert result.exit_code == 0
    refdata.get_all_products.assert_called_once_with()
    refdata.get_contracts_for_product.assert_called_once_with("test_fut")


def test_smokecheck_invokes_refdata_smokecheck(mocker: MockerFixture) -> None:
    counts = Mock()
    counts.products = 1
    counts.periods = 2
    counts.contracts = 3
    counts.cycles = 4
    counts.memberships = 5

    report = Mock()
    report.counts = counts
    report.results = []
    report.passed = True

    refdata = Mock()
    refdata.smokecheck.return_value = report
    mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(app, ["smokecheck"])

    assert result.exit_code == 0
    refdata.smokecheck.assert_called_once_with()


def test_environment_and_role_are_passed_to_refdata_helper(
    mocker: MockerFixture,
) -> None:
    refdata = Mock()
    refdata.get_all_products.return_value = []
    mocked_refdata = mocker.patch("mxm.refdata.cli._refdata", return_value=refdata)

    result = runner.invoke(
        app,
        ["products", "--environment", "prod", "--role", "admin"],
    )

    assert result.exit_code == 0
    mocked_refdata.assert_called_once_with(environment="prod", role="admin")
