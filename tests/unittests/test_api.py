"""Tests for the read-only RefDataAPI façade."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from pytest_mock import MockerFixture

from mxm.refdata.api import RefDataAPI


def test_from_runtime_context_builds_refdata_api(mocker: MockerFixture) -> None:
    """from_runtime_context should compose RefData and wrap it."""
    ctx = Mock()
    refdata = Mock()

    build_refdata = mocker.patch(
        "mxm.refdata.api.build_refdata",
        return_value=refdata,
    )

    api = RefDataAPI.from_runtime_context(ctx)

    assert isinstance(api, RefDataAPI)
    build_refdata.assert_called_once_with(ctx)


def test_check_ready_delegates_to_refdata() -> None:
    refdata = Mock()
    api = RefDataAPI(refdata)

    api.check_ready()

    refdata.check_ready.assert_called_once_with()


def test_maybe_get_contract_by_id_delegates_to_refdata() -> None:
    refdata = Mock()
    refdata.maybe_get_contract_by_id.return_value = None
    api = RefDataAPI(refdata)

    assert api.maybe_get_contract_by_id("missing") is None
    refdata.maybe_get_contract_by_id.assert_called_once_with("missing")


def test_get_contract_by_id_delegates_to_refdata() -> None:
    contract = Mock()
    refdata = Mock()
    refdata.get_contract_by_id.return_value = contract
    api = RefDataAPI(refdata)

    assert api.get_contract_by_id("contract_id") is contract
    refdata.get_contract_by_id.assert_called_once_with("contract_id")


def test_get_contracts_by_id_delegates_to_refdata() -> None:
    contracts = [Mock()]
    refdata = Mock()
    refdata.get_contracts_by_id.return_value = contracts
    api = RefDataAPI(refdata)

    assert api.get_contracts_by_id(["b", "a"]) == contracts
    refdata.get_contracts_by_id.assert_called_once_with(["b", "a"])


def test_get_active_contracts_delegates_to_refdata() -> None:
    refdata = Mock()
    refdata.get_active_contracts.return_value = []
    api = RefDataAPI(refdata)
    as_of = date(2025, 6, 18)

    assert api.get_active_contracts(as_of, product_id="gold_fut") == []
    refdata.get_active_contracts.assert_called_once_with(
        as_of,
        product_id="gold_fut",
        product_ids=None,
    )


def test_get_all_products_delegates_to_refdata() -> None:
    products = [Mock()]
    refdata = Mock()
    refdata.get_all_products.return_value = products
    api = RefDataAPI(refdata)

    assert api.get_all_products() == products
    refdata.get_all_products.assert_called_once_with()


def test_get_product_by_id_delegates_to_refdata() -> None:
    product = Mock()
    refdata = Mock()
    refdata.get_product_by_id.return_value = product
    api = RefDataAPI(refdata)

    assert api.get_product_by_id("gold_fut") is product
    refdata.get_product_by_id.assert_called_once_with("gold_fut")


def test_get_contracts_for_product_delegates_to_refdata() -> None:
    contracts = [Mock()]
    refdata = Mock()
    refdata.get_contracts_for_product.return_value = contracts
    api = RefDataAPI(refdata)

    assert api.get_contracts_for_product("gold_fut", period_type="MONTH") == contracts
    refdata.get_contracts_for_product.assert_called_once_with(
        "gold_fut",
        period_type="MONTH",
    )


def test_get_contracts_for_date_delegates_to_refdata() -> None:
    contracts = [Mock()]
    refdata = Mock()
    refdata.get_contracts_for_date.return_value = contracts
    api = RefDataAPI(refdata)
    target = date(2025, 1, 15)

    assert api.get_contracts_for_date(target) == contracts
    refdata.get_contracts_for_date.assert_called_once_with(target)


def test_get_periods_delegates_to_refdata() -> None:
    periods = [Mock()]
    refdata = Mock()
    refdata.get_periods.return_value = periods
    api = RefDataAPI(refdata)

    assert api.get_periods() == periods
    refdata.get_periods.assert_called_once_with()


def test_get_period_by_id_delegates_to_refdata() -> None:
    period = Mock()
    refdata = Mock()
    refdata.get_period_by_id.return_value = period
    api = RefDataAPI(refdata)

    assert api.get_period_by_id("Jan-2025") is period
    refdata.get_period_by_id.assert_called_once_with("Jan-2025")


def test_get_periods_by_id_delegates_to_refdata() -> None:
    periods = [Mock()]
    refdata = Mock()
    refdata.get_periods_by_id.return_value = periods
    api = RefDataAPI(refdata)

    assert api.get_periods_by_id(["Feb-2025", "Jan-2025"]) == periods
    refdata.get_periods_by_id.assert_called_once_with(["Feb-2025", "Jan-2025"])


def test_get_cycles_delegates_to_refdata() -> None:
    cycles = [Mock()]
    refdata = Mock()
    refdata.get_cycles.return_value = cycles
    api = RefDataAPI(refdata)

    assert api.get_cycles() == cycles
    refdata.get_cycles.assert_called_once_with()


def test_get_cycle_by_id_delegates_to_refdata() -> None:
    cycle = Mock()
    refdata = Mock()
    refdata.get_cycle_by_id.return_value = cycle
    api = RefDataAPI(refdata)

    assert api.get_cycle_by_id("CALENDAR_MONTHS") is cycle
    refdata.get_cycle_by_id.assert_called_once_with("CALENDAR_MONTHS")


def test_get_cycle_memberships_delegates_to_refdata() -> None:
    memberships = [Mock()]
    refdata = Mock()
    refdata.get_cycle_memberships.return_value = memberships
    api = RefDataAPI(refdata)

    assert api.get_cycle_memberships("CALENDAR_MONTHS") == memberships
    refdata.get_cycle_memberships.assert_called_once_with("CALENDAR_MONTHS")


def test_get_cycle_elements_delegates_to_refdata() -> None:
    elements = {"Jan-2025": 1}
    refdata = Mock()
    refdata.get_cycle_elements.return_value = elements
    api = RefDataAPI(refdata)

    assert api.get_cycle_elements(["Jan-2025"], cycle_id="CALENDAR_MONTHS") == elements
    refdata.get_cycle_elements.assert_called_once_with(
        ["Jan-2025"],
        cycle_id="CALENDAR_MONTHS",
    )


def test_get_cycle_element_delegates_to_refdata() -> None:
    refdata = Mock()
    refdata.get_cycle_element.return_value = 1
    api = RefDataAPI(refdata)

    assert api.get_cycle_element("Jan-2025", cycle_id="CALENDAR_MONTHS") == 1
    refdata.get_cycle_element.assert_called_once_with(
        "Jan-2025",
        cycle_id="CALENDAR_MONTHS",
    )
