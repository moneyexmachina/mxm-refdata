"""Unit tests for futures product specification domain models."""

from __future__ import annotations

from datetime import date

import pytest

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.products.futures_product_spec import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProductProvenance,
    FuturesProductSourceStatus,
    FuturesProductSpec,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday

# ---------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------


@pytest.fixture
def futures_product() -> FuturesProduct:
    """Return a representative exchange-defined futures product."""

    return FuturesProduct(
        product_id="comex_aluminum_futures",
        venue="COMEX",
        description="Aluminum Futures",
        currency=Currency.USD,
        unit=ProductUnit.METRIC_TON,
        contract_size=25.0,
        valid_period_rule="FGHJKMNQUVXZ",
        listing_rule="Monthly contracts listed for 60 consecutive months",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule=(
            "Trading terminates on the third last business day of the contract month."
        ),
        expiry_rule=("Third last business day of the contract month."),
        trading_calendar="CMES",
        trading_hours=(
            "Sunday - Friday 5:00 p.m. - 4:00 p.m. CT "
            "with a 60-minute break each day beginning at 4:00 p.m."
        ),
        tick_size=0.25,
        tick_value=6.25,
        initial_margin=None,
        maintenance_margin=None,
    )


@pytest.fixture
def source_status() -> FuturesProductSourceStatus:
    """Return representative source lifecycle metadata."""

    return FuturesProductSourceStatus(
        created_at=date(2026, 6, 23),
        updated_at=date(2026, 6, 23),
        review_status="draft",
        curator="mxm",
    )


@pytest.fixture
def provenance() -> FuturesProductProvenance:
    """Return representative product provenance."""

    return FuturesProductProvenance(
        source_type="manual_curation",
        source_url=(
            "https://www.cmegroup.com/markets/metals/base/aluminum.contractSpecs.html"
        ),
        source_accessed_at=date(2026, 6, 23),
        curation_method=("human_interpreted_from_exchange_contract_specs"),
        assistance="llm_assisted_drafting",
        notes=(
            "Primary tick size and tick value use the Globex outright "
            "futures increment.",
            "Listing horizon interpreted as 60 consecutive monthly contracts.",
        ),
    )


@pytest.fixture
def last_trading_rule() -> LastTradingRule:
    """Return the aluminum last-trading-day rule."""

    return LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
        n_reference=-3,
        business_day_offset=0,
    )


@pytest.fixture
def first_day_of_interest_rule() -> FirstDayOfInterestRule:
    """Return a representative first-day-of-interest rule."""

    return FirstDayOfInterestRule(
        shift_rule=FirstDayOfInterestShiftRule(
            shift_period_type=PeriodType.MONTH,
            n_shift={
                "Jan": 60,
                "Feb": 60,
                "Mar": 60,
                "Apr": 60,
                "May": 60,
                "Jun": 60,
                "Jul": 60,
                "Aug": 60,
                "Sep": 60,
                "Oct": 60,
                "Nov": 60,
                "Dec": 60,
            },
        ),
        reference_rule="next_b_day_after_period",
    )


@pytest.fixture
def contract_rules(
    last_trading_rule: LastTradingRule,
    first_day_of_interest_rule: FirstDayOfInterestRule,
) -> ContractRules:
    """Return the contract-construction rules for a product."""

    return ContractRules(
        last_trading_rule=last_trading_rule,
        first_day_of_interest_rule=first_day_of_interest_rule,
    )


@pytest.fixture
def futures_product_spec(
    futures_product: FuturesProduct,
    source_status: FuturesProductSourceStatus,
    provenance: FuturesProductProvenance,
    contract_rules: ContractRules,
) -> FuturesProductSpec:
    """Return a complete curated futures product specification."""

    return FuturesProductSpec(
        schema_version="futures_product.v1",
        product_id="comex_aluminum_futures",
        asset_class="futures",
        source_status=source_status,
        provenance=provenance,
        product=futures_product,
        contract_rules=contract_rules,
    )


# ---------------------------------------------------------------------
# SOURCE STATUS
# ---------------------------------------------------------------------


def test_constructs_source_status() -> None:
    status = FuturesProductSourceStatus(
        created_at=date(2026, 6, 23),
        updated_at=date(2026, 7, 1),
        review_status="reviewed",
        curator="mxm",
    )

    assert status.created_at == date(2026, 6, 23)
    assert status.updated_at == date(2026, 7, 1)
    assert status.review_status == "reviewed"
    assert status.curator == "mxm"


def test_source_status_rejects_updated_at_before_created_at() -> None:
    with pytest.raises(
        ValueError,
        match="updated_at cannot precede created_at",
    ):
        FuturesProductSourceStatus(
            created_at=date(2026, 7, 1),
            updated_at=date(2026, 6, 23),
            review_status="draft",
            curator="mxm",
        )


# ---------------------------------------------------------------------
# PROVENANCE
# ---------------------------------------------------------------------


def test_constructs_provenance() -> None:
    provenance = FuturesProductProvenance(
        source_type="manual_curation",
        source_url="https://example.com/product",
        source_accessed_at=date(2026, 6, 23),
        curation_method="human_interpreted",
        assistance="llm_assisted_drafting",
        notes=("First note.", "Second note."),
    )

    assert provenance.source_type == "manual_curation"
    assert provenance.source_url == "https://example.com/product"
    assert provenance.source_accessed_at == date(2026, 6, 23)
    assert provenance.curation_method == "human_interpreted"
    assert provenance.assistance == "llm_assisted_drafting"
    assert provenance.notes == ("First note.", "Second note.")


# ---------------------------------------------------------------------
# LAST TRADING RULES
# ---------------------------------------------------------------------


def test_constructs_business_day_last_trading_rule() -> None:
    rule = LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
        n_reference=-3,
        business_day_offset=0,
    )

    assert rule.period_offset == 0
    assert rule.reference_event is ReferenceEvent.BUSINESS_DAY_OF_PERIOD
    assert rule.n_reference == -3
    assert rule.business_day_offset == 0
    assert rule.weekday is None


def test_constructs_calendar_day_last_trading_rule() -> None:
    rule = LastTradingRule(
        period_offset=-1,
        reference_event=ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
        n_reference=15,
        business_day_offset=-1,
    )

    assert rule.period_offset == -1
    assert rule.reference_event is ReferenceEvent.CALENDAR_DAY_OF_PERIOD
    assert rule.n_reference == 15
    assert rule.business_day_offset == -1
    assert rule.weekday is None


def test_constructs_weekday_last_trading_rule() -> None:
    rule = LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
        n_reference=3,
        business_day_offset=0,
        weekday=Weekday.from_str("FRIDAY"),
    )

    assert rule.reference_event is ReferenceEvent.WEEKDAY_OF_PERIOD
    assert rule.n_reference == 3
    assert rule.weekday is not None
    assert rule.weekday.as_int == 4


def test_weekday_reference_requires_weekday() -> None:
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


def test_non_weekday_reference_does_not_require_weekday() -> None:
    rule = LastTradingRule(
        period_offset=0,
        reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
        n_reference=-1,
        business_day_offset=0,
    )

    assert rule.weekday is None


# ---------------------------------------------------------------------
# FIRST DAY OF INTEREST RULES
# ---------------------------------------------------------------------


def test_constructs_first_day_of_interest_shift_rule() -> None:
    shift_rule = FirstDayOfInterestShiftRule(
        shift_period_type=PeriodType.MONTH,
        n_shift={
            "Jan": 12,
            "Feb": 12,
            "Mar": 12,
        },
    )

    assert shift_rule.shift_period_type is PeriodType.MONTH
    assert shift_rule.n_shift == {
        "Jan": 12,
        "Feb": 12,
        "Mar": 12,
    }


def test_constructs_first_day_of_interest_rule() -> None:
    shift_rule = FirstDayOfInterestShiftRule(
        shift_period_type=PeriodType.MONTH,
        n_shift={"Jan": 60},
    )

    rule = FirstDayOfInterestRule(
        shift_rule=shift_rule,
        reference_rule="next_b_day_after_period",
    )

    assert rule.shift_rule is shift_rule
    assert rule.reference_rule == "next_b_day_after_period"


# ---------------------------------------------------------------------
# CONTRACT RULES
# ---------------------------------------------------------------------


def test_constructs_contract_rules(
    last_trading_rule: LastTradingRule,
    first_day_of_interest_rule: FirstDayOfInterestRule,
) -> None:
    rules = ContractRules(
        last_trading_rule=last_trading_rule,
        first_day_of_interest_rule=first_day_of_interest_rule,
    )

    assert rules.last_trading_rule is last_trading_rule
    assert rules.first_day_of_interest_rule is first_day_of_interest_rule


def test_contract_rules_have_value_equality() -> None:
    left = ContractRules(
        last_trading_rule=LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
            n_reference=-3,
            business_day_offset=0,
        ),
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift={"Jan": 60},
            ),
            reference_rule="next_b_day_after_period",
        ),
    )

    right = ContractRules(
        last_trading_rule=LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
            n_reference=-3,
            business_day_offset=0,
        ),
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift={"Jan": 60},
            ),
            reference_rule="next_b_day_after_period",
        ),
    )

    assert left == right


# ---------------------------------------------------------------------
# COMPLETE PRODUCT SPECIFICATION
# ---------------------------------------------------------------------


def test_constructs_futures_product_spec(
    futures_product_spec: FuturesProductSpec,
    futures_product: FuturesProduct,
    source_status: FuturesProductSourceStatus,
    provenance: FuturesProductProvenance,
    contract_rules: ContractRules,
) -> None:
    assert futures_product_spec.schema_version == "futures_product.v1"
    assert futures_product_spec.product_id == "comex_aluminum_futures"
    assert futures_product_spec.asset_class == "futures"
    assert futures_product_spec.source_status is source_status
    assert futures_product_spec.provenance is provenance
    assert futures_product_spec.product is futures_product
    assert futures_product_spec.contract_rules is contract_rules


def test_product_spec_rejects_mismatched_product_ids(
    futures_product: FuturesProduct,
    source_status: FuturesProductSourceStatus,
    provenance: FuturesProductProvenance,
    contract_rules: ContractRules,
) -> None:
    with pytest.raises(
        ValueError,
        match="product_id does not match",
    ):
        FuturesProductSpec(
            schema_version="futures_product.v1",
            product_id="different_product",
            asset_class="futures",
            source_status=source_status,
            provenance=provenance,
            product=futures_product,
            contract_rules=contract_rules,
        )
