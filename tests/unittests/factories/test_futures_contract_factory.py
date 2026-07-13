"""Unit tests for FuturesContractFactory."""

from __future__ import annotations

from datetime import date

import pytest

from mxm.refdata.factories import FuturesContractFactory, PeriodFactory
from mxm.refdata.models import (
    Currency,
    FuturesProduct,
    Period,
    PeriodType,
    ProductUnit,
    SettlementMethod,
)
from mxm.refdata.models.products.futures_product_spec import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.weekdays import Weekday

# ---------------------------------------------------------------------
# FACTORY AND PERIOD FIXTURES
# ---------------------------------------------------------------------


@pytest.fixture
def contract_factory() -> FuturesContractFactory:
    """Create an empty FuturesContractFactory."""

    return FuturesContractFactory()


@pytest.fixture
def mock_periods() -> dict[str, Period]:
    """Create canonical monthly periods for 2024."""

    periods = [
        PeriodFactory.get_period(
            period_id=date(2024, month, 1).strftime("%b-%Y"),
        )
        for month in range(1, 13)
    ]

    return {period.period_id: period for period in periods}


# ---------------------------------------------------------------------
# PRODUCT FIXTURES
# ---------------------------------------------------------------------


@pytest.fixture
def all_months_product() -> FuturesProduct:
    """Return a product with contracts for every calendar month."""

    return FuturesProduct(
        product_id="ALL_MONTHS",
        venue="CME",
        description="All Monthly Contracts Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        listing_rule="All monthly contracts listed",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=("Third last business day of the delivery month"),
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="FGHJKMNQUVXZ",
    )


@pytest.fixture
def partial_months_product() -> FuturesProduct:
    """Return a product with February, April, July, and October contracts."""

    return FuturesProduct(
        product_id="PARTIAL_MONTHS",
        venue="CME",
        description="Partial Monthly Contracts Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        listing_rule="Limited monthly contracts listed",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=("Business day before the fifteenth calendar day"),
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="GJNV",
    )


@pytest.fixture
def quarterly_product() -> FuturesProduct:
    """Return a product with March, June, September, and December contracts."""

    return FuturesProduct(
        product_id="QUARTERLY",
        venue="CME",
        description="Quarterly Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        listing_rule="Quarterly contracts listed",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="Third Friday of the delivery month",
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        tick_size=0.1,
        tick_value=10.0,
        valid_period_rule="HMUZ",
    )


# ---------------------------------------------------------------------
# CONTRACT-RULE FIXTURES
# ---------------------------------------------------------------------


def _zero_month_shifts() -> dict[str, int]:
    """Return a zero shift for every contract month."""

    return {
        "Jan": 0,
        "Feb": 0,
        "Mar": 0,
        "Apr": 0,
        "May": 0,
        "Jun": 0,
        "Jul": 0,
        "Aug": 0,
        "Sep": 0,
        "Oct": 0,
        "Nov": 0,
        "Dec": 0,
    }


@pytest.fixture
def all_months_contract_rules() -> ContractRules:
    """Return contract rules for the all-months product."""

    return ContractRules(
        last_trading_rule=LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
            n_reference=-3,
            business_day_offset=0,
        ),
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift=_zero_month_shifts(),
            ),
            reference_rule="next_b_day_after_period",
        ),
    )


@pytest.fixture
def partial_months_contract_rules() -> ContractRules:
    """Return contract rules for the partial-months product."""

    return ContractRules(
        last_trading_rule=LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
            n_reference=15,
            business_day_offset=-1,
        ),
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift=_zero_month_shifts(),
            ),
            reference_rule=("next_b_day_after_last_trading_day_of_december"),
        ),
    )


@pytest.fixture
def quarterly_contract_rules() -> ContractRules:
    """Return contract rules for the quarterly product."""

    return ContractRules(
        last_trading_rule=LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
            n_reference=3,
            business_day_offset=0,
            weekday=Weekday.from_str("Friday"),
        ),
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift={
                    "Mar": 63,
                    "Jun": 63,
                    "Sep": 63,
                    "Dec": 63,
                },
            ),
            reference_rule="next_b_day_after_period",
        ),
    )


# ---------------------------------------------------------------------
# CONTRACT-SERIES CREATION
# ---------------------------------------------------------------------


def test_create_contracts_for_product_all_months(
    contract_factory: FuturesContractFactory,
    all_months_product: FuturesProduct,
    all_months_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Create one contract for each calendar month."""

    contracts = contract_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )

    expected_ids = {
        (f"{all_months_product.product_id}.{date(2024, month, 1).strftime('%b-%Y')}")
        for month in range(1, 13)
    }

    assert len(contracts) == 12
    assert {contract.contract_id for contract in contracts} == expected_ids


def test_create_contracts_for_product_partial_months(
    contract_factory: FuturesContractFactory,
    partial_months_product: FuturesProduct,
    partial_months_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Create contracts only for the product's valid month codes."""

    contracts = contract_factory.create_contracts_for_product(
        product=partial_months_product,
        contract_rules=partial_months_contract_rules,
        available_periods=mock_periods,
    )

    expected_ids = {
        (
            f"{partial_months_product.product_id}."
            f"{date(2024, month, 1).strftime('%b-%Y')}"
        )
        for month in (2, 4, 7, 10)
    }

    assert len(contracts) == 4
    assert {contract.contract_id for contract in contracts} == expected_ids


def test_create_contracts_for_product_quarterly(
    contract_factory: FuturesContractFactory,
    quarterly_product: FuturesProduct,
    quarterly_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Create contracts only for March, June, September, and December."""

    contracts = contract_factory.create_contracts_for_product(
        product=quarterly_product,
        contract_rules=quarterly_contract_rules,
        available_periods=mock_periods,
    )

    expected_ids = {
        (f"{quarterly_product.product_id}.{date(2024, month, 1).strftime('%b-%Y')}")
        for month in (3, 6, 9, 12)
    }

    assert len(contracts) == 4
    assert {contract.contract_id for contract in contracts} == expected_ids


# ---------------------------------------------------------------------
# CONTRACT CONSTRUCTION
# ---------------------------------------------------------------------


def test_create_contract_uses_explicit_product_and_rules(
    contract_factory: FuturesContractFactory,
    all_months_product: FuturesProduct,
    all_months_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Construct a contract entirely from explicitly supplied inputs."""

    period = mock_periods["Jun-2024"]

    contract = contract_factory.create_contract(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        period=period,
    )

    assert contract.contract_id == "ALL_MONTHS.Jun-2024"
    assert contract.product_id == "ALL_MONTHS"
    assert contract.period_id == "Jun-2024"
    assert contract.contract_size == 100
    assert contract.currency is Currency.USD
    assert contract.unit is ProductUnit.TROY_OUNCE
    assert contract.trading_calendar == "CME"
    assert contract.first_day_of_interest == date(2024, 7, 1)
    assert contract.last_trading_day == date(2024, 6, 26)


# ---------------------------------------------------------------------
# INTERNING AND CACHE ISOLATION
# ---------------------------------------------------------------------


def test_create_contracts_for_product_reuses_cached_contracts(
    contract_factory: FuturesContractFactory,
    all_months_product: FuturesProduct,
    all_months_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Repeated creation should return canonical cached instances."""

    first = contract_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )
    second = contract_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )

    assert len(first) == len(second)
    assert all(
        first_contract is second_contract
        for first_contract, second_contract in zip(
            first,
            second,
            strict=True,
        )
    )


def test_factory_instances_have_independent_caches(
    contract_factory: FuturesContractFactory,
    all_months_product: FuturesProduct,
    all_months_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Separate factory instances should not share contract instances."""

    other_factory = FuturesContractFactory()

    first = contract_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )
    second = other_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )

    assert first == second
    assert all(
        first_contract is not second_contract
        for first_contract, second_contract in zip(
            first,
            second,
            strict=True,
        )
    )


def test_clear_cache_removes_canonical_contracts(
    contract_factory: FuturesContractFactory,
    all_months_product: FuturesProduct,
    all_months_contract_rules: ContractRules,
    mock_periods: dict[str, Period],
) -> None:
    """Clearing the cache should cause contracts to be reconstructed."""

    first = contract_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )

    contract_factory.clear_cache()

    second = contract_factory.create_contracts_for_product(
        product=all_months_product,
        contract_rules=all_months_contract_rules,
        available_periods=mock_periods,
    )

    assert first == second
    assert all(
        first_contract is not second_contract
        for first_contract, second_contract in zip(
            first,
            second,
            strict=True,
        )
    )
