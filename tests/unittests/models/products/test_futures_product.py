"""Unit tests for futures-product domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProduct,
    LastTradingRule,
)
from mxm.refdata.models.products.settlement import SettlementMethod
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday


def _make_contract_rules() -> ContractRules:
    """Return representative contract-construction rules."""

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
                n_shift={
                    "Jan": 24,
                    "Feb": 24,
                    "Mar": 24,
                    "Apr": 24,
                    "May": 24,
                    "Jun": 24,
                    "Jul": 24,
                    "Aug": 24,
                    "Sep": 24,
                    "Oct": 24,
                    "Nov": 24,
                    "Dec": 24,
                },
            ),
            reference_rule="next_b_day_after_period",
        ),
    )


def _make_product(
    *,
    contract_rules: ContractRules | None = None,
) -> FuturesProduct:
    """Return a representative complete futures product."""

    return FuturesProduct(
        product_id="GC",
        asset_class="futures",
        venue="COMEX",
        description="Gold Futures",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="monthly for all months",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=(
            "Trading terminates on the third last business day of the delivery month."
        ),
        expiry_rule="Third last business day of the delivery month.",
        trading_calendar="CMES",
        contract_rules=contract_rules or _make_contract_rules(),
    )


# ---------------------------------------------------------------------
# FUTURES PRODUCT
# ---------------------------------------------------------------------


def test_futures_product_initialises_complete_operational_definition() -> None:
    """A product contains all state required for contract construction."""

    contract_rules = _make_contract_rules()

    product = _make_product(
        contract_rules=contract_rules,
    )

    assert product.product_id == "GC"
    assert product.asset_class == "futures"
    assert product.venue == "COMEX"
    assert product.description == "Gold Futures"

    assert product.currency is Currency.USD
    assert product.unit is ProductUnit.TROY_OUNCE
    assert product.contract_size == 100.0

    assert product.valid_period_rule == "FGHJKMNQUVXZ"
    assert product.listing_rule == "monthly for all months"
    assert product.period_types == (PeriodType.MONTH,)

    assert product.settlement is SettlementMethod.PHYSICAL
    assert product.last_trading_rule == (
        "Trading terminates on the third last business day of the delivery month."
    )
    assert product.expiry_rule == ("Third last business day of the delivery month.")

    assert product.trading_calendar == "CMES"
    assert product.contract_rules is contract_rules


def test_futures_product_optional_fields_default_to_none() -> None:
    """Optional exchange and margin fields default to None."""

    product = _make_product()

    assert product.trading_hours is None
    assert product.tick_size is None
    assert product.tick_value is None
    assert product.initial_margin is None
    assert product.maintenance_margin is None


def test_futures_product_accepts_optional_fields() -> None:
    """Optional exchange and margin fields are retained."""

    product = replace(
        _make_product(),
        trading_hours="23:00 - 22:00 UTC",
        tick_size=0.1,
        tick_value=10.0,
        initial_margin=5000.0,
        maintenance_margin=4500.0,
    )

    assert product.trading_hours == "23:00 - 22:00 UTC"
    assert product.tick_size == 0.1
    assert product.tick_value == 10.0
    assert product.initial_margin == 5000.0
    assert product.maintenance_margin == 4500.0


def test_futures_product_equality_includes_contract_rules() -> None:
    """Contract-construction rules form part of product equality."""

    original = _make_product()

    changed_rules = replace(
        original.contract_rules,
        last_trading_rule=replace(
            original.contract_rules.last_trading_rule,
            business_day_offset=-1,
        ),
    )

    changed = replace(
        original,
        contract_rules=changed_rules,
    )

    assert changed != original


def test_futures_product_is_immutable() -> None:
    """Operational product definitions cannot be mutated in place."""

    product = _make_product()

    with pytest.raises(FrozenInstanceError):
        product.description = "Changed description"  # type: ignore[misc]


# ---------------------------------------------------------------------
# CONTRACT RULE VALUE OBJECTS
# ---------------------------------------------------------------------


def test_last_trading_rule_accepts_business_day_reference() -> None:
    """Business-day rules do not require a weekday."""

    rule = LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
        n_reference=-3,
        business_day_offset=0,
    )

    assert rule.weekday is None


def test_last_trading_rule_accepts_weekday_reference() -> None:
    """Weekday-based rules retain their required weekday."""

    rule = LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
        n_reference=3,
        business_day_offset=0,
        weekday=Weekday(4),
    )

    assert rule.reference_event is ReferenceEvent.WEEKDAY_OF_PERIOD
    assert rule.weekday == Weekday(4)


def test_last_trading_rule_rejects_missing_weekday() -> None:
    """A weekday reference event requires a weekday value."""

    with pytest.raises(
        ValueError,
        match="weekday is required",
    ):
        LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
            n_reference=3,
            business_day_offset=0,
        )


def test_contract_rules_compose_complete_generation_rules() -> None:
    """ContractRules combines both required contract-generation rules."""

    rules = _make_contract_rules()

    assert (
        rules.last_trading_rule.reference_event is ReferenceEvent.BUSINESS_DAY_OF_PERIOD
    )

    first_day_rule = rules.first_day_of_interest_rule

    assert first_day_rule.shift_rule.shift_period_type is PeriodType.MONTH
    assert first_day_rule.shift_rule.n_shift["Jan"] == 24
    assert first_day_rule.shift_rule.n_shift["Dec"] == 24
    assert first_day_rule.reference_rule == "next_b_day_after_period"
