"""Unit tests for the mxm-refdata CLI boundary."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from mxm.refdata.cli import app

runner = CliRunner()


def test_build_rejects_invalid_contract_start_date() -> None:
    result = runner.invoke(
        app,
        [
            "build",
            "--db-url",
            "sqlite:///:memory:",
            "--contract-start-date",
            "bad-date",
        ],
    )

    assert result.exit_code != 0
    assert "Expected date in YYYY-MM-DD format" in result.output


def test_build_invokes_build_refdata(mocker: MockerFixture) -> None:
    mocked_build = mocker.patch("mxm.refdata.cli.build_refdata")
    mocked_from_db_url = mocker.patch("mxm.refdata.cli.SQLSessionManager.from_db_url")

    result = runner.invoke(
        app,
        [
            "build",
            "--db-url",
            "sqlite:///:memory:",
            "--contract-start-date",
            "2024-01-01",
            "--contract-end-date",
            "2024-12-31",
        ],
    )

    assert result.exit_code == 0
    mocked_from_db_url.assert_called_once_with("sqlite:///:memory:")

    assert mocked_build.call_count == 1
    kwargs = mocked_build.call_args.kwargs
    assert kwargs["config"]["SQL_DB_URL"] == "sqlite:///:memory:"
    assert kwargs["config"]["REFDATA_CONTRACT_START_DATE"] == "2024-01-01"
    assert kwargs["config"]["REFDATA_CONTRACT_END_DATE"] == "2024-12-31"
    assert kwargs["session_manager"] == mocked_from_db_url.return_value


def test_rebuild_invokes_rebuild_refdata(mocker: MockerFixture) -> None:
    mocked_rebuild = mocker.patch("mxm.refdata.cli.rebuild_refdata")
    mocked_from_db_url = mocker.patch("mxm.refdata.cli.SQLSessionManager.from_db_url")

    result = runner.invoke(
        app,
        [
            "rebuild",
            "--db-url",
            "sqlite:///:memory:",
            "--contract-start-date",
            "2025-01-01",
            "--contract-end-date",
            "2025-12-31",
        ],
    )

    assert result.exit_code == 0
    mocked_from_db_url.assert_called_once_with("sqlite:///:memory:")

    assert mocked_rebuild.call_count == 1
    kwargs = mocked_rebuild.call_args.kwargs
    assert kwargs["config"]["SQL_DB_URL"] == "sqlite:///:memory:"
    assert kwargs["config"]["REFDATA_CONTRACT_START_DATE"] == "2025-01-01"
    assert kwargs["config"]["REFDATA_CONTRACT_END_DATE"] == "2025-12-31"
    assert kwargs["session_manager"] == mocked_from_db_url.return_value


def test_products_uses_api_from_config_data(mocker: MockerFixture) -> None:
    api = Mock()
    api.get_all_products.return_value = []

    mocked_factory = mocker.patch(
        "mxm.refdata.cli.RefDataAPI.from_config_data",
        return_value=api,
    )

    result = runner.invoke(
        app,
        ["products", "--db-url", "sqlite:///:memory:"],
    )

    assert result.exit_code == 0
    mocked_factory.assert_called_once_with({"SQL_DB_URL": "sqlite:///:memory:"})
    api.get_all_products.assert_called_once_with()


def test_product_uses_api_lookup(mocker: MockerFixture) -> None:
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

    api = Mock()
    api.get_product_by_id.return_value = product
    mocker.patch("mxm.refdata.cli.RefDataAPI.from_config_data", return_value=api)

    result = runner.invoke(
        app,
        ["product", "cme_test_futures", "--db-url", "sqlite:///:memory:"],
    )

    assert result.exit_code == 0
    api.get_product_by_id.assert_called_once_with("cme_test_futures")


def test_contracts_uses_api_lookup(mocker: MockerFixture) -> None:
    contract = Mock()
    contract.contract_id = "cme_test_futures.Mar-2025"
    contract.period_id = "Mar-2025"
    contract.first_day_of_interest = date(2024, 1, 1)
    contract.last_trading_day = date(2025, 3, 20)

    api = Mock()
    api.get_contracts_for_product.return_value = [contract]
    mocker.patch("mxm.refdata.cli.RefDataAPI.from_config_data", return_value=api)

    result = runner.invoke(
        app,
        ["contracts", "cme_test_futures", "--db-url", "sqlite:///:memory:"],
    )

    assert result.exit_code == 0
    api.get_contracts_for_product.assert_called_once_with("cme_test_futures")


def test_active_uses_parsed_date_and_optional_product_id(
    mocker: MockerFixture,
) -> None:
    api = Mock()
    api.get_active_contracts.return_value = []
    mocker.patch("mxm.refdata.cli.RefDataAPI.from_config_data", return_value=api)

    result = runner.invoke(
        app,
        [
            "active",
            "2025-06-18",
            "--db-url",
            "sqlite:///:memory:",
            "--product-id",
            "cme_test_futures",
        ],
    )

    assert result.exit_code == 0
    api.get_active_contracts.assert_called_once_with(
        date(2025, 6, 18),
        product_id="cme_test_futures",
    )


def test_smokecheck_invokes_run_smokechecks(mocker: MockerFixture) -> None:
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

    mocked_smokecheck = mocker.patch(
        "mxm.refdata.cli.run_smokechecks",
        return_value=report,
    )
    mocked_from_db_url = mocker.patch("mxm.refdata.cli.SQLSessionManager.from_db_url")

    result = runner.invoke(
        app,
        ["smokecheck", "--db-url", "sqlite:///:memory:"],
    )

    assert result.exit_code == 0
    mocked_from_db_url.assert_called_once_with("sqlite:///:memory:")
    mocked_smokecheck.assert_called_once_with(
        session_manager=mocked_from_db_url.return_value
    )
