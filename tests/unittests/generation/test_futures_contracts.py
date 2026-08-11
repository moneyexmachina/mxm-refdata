"""Unit tests for pure futures-contract generation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import pytest

from mxm.refdata.generation.futures_contracts import (
    generate_futures_contract,
    generate_futures_contracts,
)
from mxm.refdata.generation.periods import period_from_id
from mxm.refdata.models import (
    Currency,
    FuturesContract,
    FuturesProduct,
    Period,
    PeriodType,
    ProductUnit,
    SettlementMethod,
)
from mxm.refdata.models.products.futures_product import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.weekdays import Weekday

# ---------------------------------------------------------------------
# RULE HELPERS
# ---------------------------------------------------------------------


def _zero_month_shifts() -> dict[str, int]:
    """Return a zero shift for every calendar month."""

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


def _all_months_contract_rules() -> ContractRules:
    """Return rules for a conventional monthly contract series."""

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


def _partial_months_contract_rules() -> ContractRules:
    """Return rules exercising a different lifecycle-date calculation."""

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


def _quarterly_contract_rules() -> ContractRules:
    """Return rules for quarterly-listed monthly contracts."""

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
# PRODUCT FIXTURES
# ---------------------------------------------------------------------


@pytest.fixture
def all_months_product() -> FuturesProduct:
    """Return a product with a contract for every calendar month."""

    return FuturesProduct(
        product_id="ALL_MONTHS",
        asset_class="metals",
        venue="CME",
        description="All Monthly Contracts Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="All monthly contracts listed",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=("Third last business day of the delivery month"),
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        contract_rules=_all_months_contract_rules(),
        trading_hours=None,
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=None,
        maintenance_margin=None,
    )


@pytest.fixture
def partial_months_product() -> FuturesProduct:
    """Return a product with February, April, July, and October contracts."""

    return FuturesProduct(
        product_id="PARTIAL_MONTHS",
        asset_class="metals",
        venue="CME",
        description="Partial Monthly Contracts Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        valid_period_rule="GJNV",
        listing_rule="Limited monthly contracts listed",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=("Business day before the fifteenth calendar day"),
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        contract_rules=_partial_months_contract_rules(),
        trading_hours=None,
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=None,
        maintenance_margin=None,
    )


@pytest.fixture
def quarterly_product() -> FuturesProduct:
    """Return a product with March, June, September, and December contracts."""

    return FuturesProduct(
        product_id="QUARTERLY",
        asset_class="metals",
        venue="CME",
        description="Quarterly Product",
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        contract_size=100,
        valid_period_rule="HMUZ",
        listing_rule="Quarterly contracts listed",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="Third Friday of the delivery month",
        expiry_rule="Last trading day of the month",
        trading_calendar="CME",
        contract_rules=_quarterly_contract_rules(),
        trading_hours=None,
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=None,
        maintenance_margin=None,
    )


# ---------------------------------------------------------------------
# PERIOD FIXTURES
# ---------------------------------------------------------------------


@pytest.fixture
def monthly_periods_2024() -> list[Period]:
    """Return canonical monthly periods for 2024."""

    return [
        period_from_id(
            date(
                2024,
                month,
                1,
            ).strftime("%b-%Y")
        )
        for month in range(
            1,
            13,
        )
    ]


# ---------------------------------------------------------------------
# SINGLE-CONTRACT GENERATION
# ---------------------------------------------------------------------


def test_generate_futures_contract(
    all_months_product: FuturesProduct,
) -> None:
    """Generate a complete contract from product and period."""

    period = period_from_id("Jun-2024")

    contract = generate_futures_contract(
        product=all_months_product,
        period=period,
    )

    assert contract == FuturesContract(
        contract_id="ALL_MONTHS.Jun-2024",
        product_id="ALL_MONTHS",
        period_id="Jun-2024",
        contract_size=100,
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        trading_calendar="CME",
        first_day_of_interest=date(
            2024,
            7,
            1,
        ),
        last_trading_day=date(
            2024,
            6,
            26,
        ),
    )


def test_generate_futures_contract_uses_product_contract_rules(
    partial_months_product: FuturesProduct,
) -> None:
    """Lifecycle dates are derived from rules embedded in the product."""

    contract = generate_futures_contract(
        product=partial_months_product,
        period=period_from_id("Feb-2024"),
    )

    assert contract.last_trading_day == date(
        2024,
        2,
        14,
    )


def test_generate_futures_contract_is_deterministic_without_interning(
    all_months_product: FuturesProduct,
) -> None:
    """Repeated generation returns equal independent values."""

    period = period_from_id("Jun-2024")

    first = generate_futures_contract(
        product=all_months_product,
        period=period,
    )
    second = generate_futures_contract(
        product=all_months_product,
        period=period,
    )

    assert first == second
    assert first is not second


# ---------------------------------------------------------------------
# CONTRACT-SERIES GENERATION
# ---------------------------------------------------------------------


def test_generate_futures_contracts_all_months(
    all_months_product: FuturesProduct,
    monthly_periods_2024: list[Period],
) -> None:
    """Generate one contract for every valid calendar month."""

    contracts = generate_futures_contracts(
        product=all_months_product,
        periods=monthly_periods_2024,
    )

    assert [contract.contract_id for contract in contracts] == [
        f"ALL_MONTHS.{date(2024, month, 1).strftime('%b-%Y')}"
        for month in range(
            1,
            13,
        )
    ]


def test_generate_futures_contracts_partial_months(
    partial_months_product: FuturesProduct,
    monthly_periods_2024: list[Period],
) -> None:
    """Generate contracts only for valid CME month codes."""

    contracts = generate_futures_contracts(
        product=partial_months_product,
        periods=monthly_periods_2024,
    )

    assert [contract.contract_id for contract in contracts] == [
        "PARTIAL_MONTHS.Feb-2024",
        "PARTIAL_MONTHS.Apr-2024",
        "PARTIAL_MONTHS.Jul-2024",
        "PARTIAL_MONTHS.Oct-2024",
    ]


def test_generate_futures_contracts_quarterly_months(
    quarterly_product: FuturesProduct,
    monthly_periods_2024: list[Period],
) -> None:
    """Generate only March, June, September, and December contracts."""

    contracts = generate_futures_contracts(
        product=quarterly_product,
        periods=monthly_periods_2024,
    )

    assert [contract.contract_id for contract in contracts] == [
        "QUARTERLY.Mar-2024",
        "QUARTERLY.Jun-2024",
        "QUARTERLY.Sep-2024",
        "QUARTERLY.Dec-2024",
    ]


def test_generate_futures_contracts_rejects_unsupported_period_types_by_filtering(
    all_months_product: FuturesProduct,
) -> None:
    """Periods not supported by the product do not generate contracts."""

    periods = [
        period_from_id("Jan-2024"),
        period_from_id("2024-Q1"),
        period_from_id("Feb-2024"),
    ]

    contracts = generate_futures_contracts(
        product=all_months_product,
        periods=periods,
    )

    assert [contract.contract_id for contract in contracts] == [
        "ALL_MONTHS.Jan-2024",
        "ALL_MONTHS.Feb-2024",
    ]


def test_generate_futures_contracts_preserves_period_input_order(
    partial_months_product: FuturesProduct,
) -> None:
    """Generated contracts preserve the order of eligible input periods."""

    periods = [
        period_from_id("Oct-2024"),
        period_from_id("Feb-2024"),
        period_from_id("Jul-2024"),
        period_from_id("Apr-2024"),
    ]

    contracts = generate_futures_contracts(
        product=partial_months_product,
        periods=periods,
    )

    assert [contract.period_id for contract in contracts] == [
        "Oct-2024",
        "Feb-2024",
        "Jul-2024",
        "Apr-2024",
    ]


def test_generate_futures_contracts_accepts_general_iterable(
    all_months_product: FuturesProduct,
) -> None:
    """The periods input need not be a concrete collection."""

    periods: Iterable[Period] = (
        period_from_id(period_id)
        for period_id in (
            "Jan-2024",
            "Feb-2024",
            "Mar-2024",
        )
    )

    contracts = generate_futures_contracts(
        product=all_months_product,
        periods=periods,
    )

    assert [contract.period_id for contract in contracts] == [
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
    ]


def test_generate_futures_contracts_returns_empty_for_no_periods(
    all_months_product: FuturesProduct,
) -> None:
    """An empty period collection produces an empty contract collection."""

    assert (
        generate_futures_contracts(
            product=all_months_product,
            periods=(),
        )
        == []
    )


def test_generate_futures_contracts_is_deterministic_without_interning(
    all_months_product: FuturesProduct,
) -> None:
    """Series generation has pure value rather than cache semantics."""

    periods = [
        period_from_id("Jan-2024"),
        period_from_id("Feb-2024"),
    ]

    first = generate_futures_contracts(
        product=all_months_product,
        periods=periods,
    )
    second = generate_futures_contracts(
        product=all_months_product,
        periods=periods,
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
