"""PostgreSQL integration tests for futures-contract SQL/schema compatibility.

These tests exercise the real migrated PostgreSQL schema. They prove that the
futures-contract SQL adapter matches that schema, that its product, period-type,
and active-date selections have the intended PostgreSQL semantics, that
idempotent/conflicting persistence behaves as required, and that the real
product and period foreign keys are enforced.

Generic transaction lifecycle is tested separately by ``PostgresDatabase`` and
at the higher-level materialisation integration boundary.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Literal

import pytest
from psycopg.errors import ForeignKeyViolation

from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import Period, PeriodType
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
from mxm.refdata.sql.futures_contracts import (
    FuturesContractConflictError,
    fetch_active_futures_contracts,
    fetch_futures_contracts,
    fetch_futures_contracts_by_ids,
    fetch_futures_contracts_for_product,
    insert_futures_contracts,
)
from mxm.refdata.sql.futures_products import insert_futures_products
from mxm.refdata.sql.periods import insert_periods
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres


def _period(
    period_id: str,
    period_type: PeriodType,
    first_date: date,
    last_date: date,
) -> Period:
    """Construct one representative delivery period."""

    return Period(
        period_id=period_id,
        period_type=period_type,
        first_date=first_date,
        last_date=last_date,
    )


def _product(
    product_id: str,
) -> FuturesProduct:
    """Construct one valid parent futures product."""

    return FuturesProduct(
        product_id=product_id,
        asset_class="metals",
        venue="COMEX",
        description=f"{product_id} Futures",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="all",
        listing_rule="all",
        period_types=(
            PeriodType.MONTH,
            PeriodType.QUARTER,
        ),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="Representative test rule",
        expiry_rule="Representative test rule",
        trading_calendar="CME",
        contract_rules=ContractRules(
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
                        "Mar": 1,
                        "Jun": 1,
                        "Sep": 1,
                        "Dec": 1,
                    },
                ),
                reference_rule="next_b_day_after_period",
            ),
        ),
    )


def _contract(
    *,
    product_id: str,
    period_id: str,
    first_day_of_interest: date,
    last_trading_day: date,
) -> FuturesContract:
    """Construct one representative futures contract."""

    return FuturesContract(
        contract_id=f"{product_id}.{period_id}",
        product_id=product_id,
        period_id=period_id,
        contract_size=100.0,
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        trading_calendar="CME",
        first_day_of_interest=first_day_of_interest,
        last_trading_day=last_trading_day,
    )


def test_futures_contracts_round_trip_and_filter_by_id_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Contract writes, reads, and ID selection match the real schema."""

    database = migrated_postgres_database

    product = _product("TEST_PRODUCT")

    january = _period(
        "2024-01",
        PeriodType.MONTH,
        date(2024, 1, 1),
        date(2024, 1, 31),
    )
    first_quarter = _period(
        "2024-Q1",
        PeriodType.QUARTER,
        date(2024, 1, 1),
        date(2024, 3, 31),
    )

    january_contract = _contract(
        product_id=product.product_id,
        period_id=january.period_id,
        first_day_of_interest=date(2024, 1, 1),
        last_trading_day=date(2024, 1, 31),
    )
    quarter_contract = _contract(
        product_id=product.product_id,
        period_id=first_quarter.period_id,
        first_day_of_interest=date(2024, 1, 15),
        last_trading_day=date(2024, 3, 28),
    )

    expected_contracts = {
        january_contract.contract_id: january_contract,
        quarter_contract.contract_id: quarter_contract,
    }

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                january,
                first_quarter,
            ],
        )
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product,
            ],
        )
        insert_futures_contracts(
            connection,
            schema=database.schema,
            contracts=[
                quarter_contract,
                january_contract,
            ],
        )

    with database.transaction() as connection:
        persisted_contracts = fetch_futures_contracts(
            connection,
            schema=database.schema,
        )

        selected_contracts = fetch_futures_contracts_by_ids(
            connection,
            schema=database.schema,
            contract_ids=[
                "MISSING_PRODUCT.2024-01",
                january_contract.contract_id,
                january_contract.contract_id,
            ],
        )

    assert persisted_contracts == expected_contracts

    assert selected_contracts == {
        january_contract.contract_id: january_contract,
    }


def test_futures_contract_queries_use_postgres_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Product, period-type, and inclusive active-date queries behave correctly."""

    database = migrated_postgres_database

    product_a = _product("PRODUCT_A")
    product_b = _product("PRODUCT_B")

    january = _period(
        "2024-01",
        PeriodType.MONTH,
        date(2024, 1, 1),
        date(2024, 1, 31),
    )
    february = _period(
        "2024-02",
        PeriodType.MONTH,
        date(2024, 2, 1),
        date(2024, 2, 29),
    )
    first_quarter = _period(
        "2024-Q1",
        PeriodType.QUARTER,
        date(2024, 1, 1),
        date(2024, 3, 31),
    )

    january_a = _contract(
        product_id=product_a.product_id,
        period_id=january.period_id,
        first_day_of_interest=date(2024, 1, 1),
        last_trading_day=date(2024, 1, 31),
    )
    february_a = _contract(
        product_id=product_a.product_id,
        period_id=february.period_id,
        first_day_of_interest=date(2024, 2, 1),
        last_trading_day=date(2024, 2, 29),
    )
    quarter_a = _contract(
        product_id=product_a.product_id,
        period_id=first_quarter.period_id,
        first_day_of_interest=date(2024, 1, 15),
        last_trading_day=date(2024, 3, 28),
    )
    january_b = _contract(
        product_id=product_b.product_id,
        period_id=january.period_id,
        first_day_of_interest=date(2024, 1, 1),
        last_trading_day=date(2024, 1, 31),
    )

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                january,
                february,
                first_quarter,
            ],
        )
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product_a,
                product_b,
            ],
        )
        insert_futures_contracts(
            connection,
            schema=database.schema,
            contracts=[
                january_a,
                february_a,
                quarter_a,
                january_b,
            ],
        )

    with database.transaction() as connection:
        product_a_contracts = fetch_futures_contracts_for_product(
            connection,
            schema=database.schema,
            product_id=product_a.product_id,
        )

        product_a_months = fetch_futures_contracts_for_product(
            connection,
            schema=database.schema,
            product_id=product_a.product_id,
            period_type=PeriodType.MONTH,
        )

        product_a_quarters = fetch_futures_contracts_for_product(
            connection,
            schema=database.schema,
            product_id=product_a.product_id,
            period_type=PeriodType.QUARTER,
        )

        active_on_january_31 = fetch_active_futures_contracts(
            connection,
            schema=database.schema,
            as_of_date=date(
                2024,
                1,
                31,
            ),
        )

        active_product_a_on_january_31 = fetch_active_futures_contracts(
            connection,
            schema=database.schema,
            as_of_date=date(
                2024,
                1,
                31,
            ),
            product_ids=[
                product_a.product_id,
                product_a.product_id,
            ],
        )

        active_on_february_1 = fetch_active_futures_contracts(
            connection,
            schema=database.schema,
            as_of_date=date(
                2024,
                2,
                1,
            ),
        )

    assert product_a_contracts == {
        january_a.contract_id: january_a,
        february_a.contract_id: february_a,
        quarter_a.contract_id: quarter_a,
    }

    assert product_a_months == {
        january_a.contract_id: january_a,
        february_a.contract_id: february_a,
    }

    assert product_a_quarters == {
        quarter_a.contract_id: quarter_a,
    }

    assert active_on_january_31 == {
        january_a.contract_id: january_a,
        quarter_a.contract_id: quarter_a,
        january_b.contract_id: january_b,
    }

    assert active_product_a_on_january_31 == {
        january_a.contract_id: january_a,
        quarter_a.contract_id: quarter_a,
    }

    assert active_on_february_1 == {
        february_a.contract_id: february_a,
        quarter_a.contract_id: quarter_a,
    }


def test_futures_contract_persistence_uses_postgres_conflict_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Identical contract state is idempotent while conflicting state is rejected."""

    database = migrated_postgres_database

    product = _product("TEST_PRODUCT")

    january = _period(
        "2024-01",
        PeriodType.MONTH,
        date(2024, 1, 1),
        date(2024, 1, 31),
    )

    contract = _contract(
        product_id=product.product_id,
        period_id=january.period_id,
        first_day_of_interest=date(2024, 1, 1),
        last_trading_day=date(2024, 1, 31),
    )

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=database.schema,
            periods=[
                january,
            ],
        )
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product,
            ],
        )
        insert_futures_contracts(
            connection,
            schema=database.schema,
            contracts=[
                contract,
            ],
        )

    with database.transaction() as connection:
        insert_futures_contracts(
            connection,
            schema=database.schema,
            contracts=[
                contract,
                contract,
            ],
        )

    conflicting_contract = replace(
        contract,
        contract_size=200.0,
    )

    with pytest.raises(
        FuturesContractConflictError,
        match=r"Persisted futures contract conflicts.*TEST_PRODUCT\.2024-01",
    ):
        with database.transaction() as connection:
            insert_futures_contracts(
                connection,
                schema=database.schema,
                contracts=[
                    conflicting_contract,
                ],
            )

    with database.transaction() as connection:
        persisted_contracts = fetch_futures_contracts(
            connection,
            schema=database.schema,
        )

    assert persisted_contracts == {
        contract.contract_id: contract,
    }


@pytest.mark.parametrize(
    "missing_reference",
    [
        "product",
        "period",
    ],
)
def test_futures_contract_foreign_keys_are_enforced(
    migrated_postgres_database: PostgresDatabase,
    missing_reference: Literal[
        "product",
        "period",
    ],
) -> None:
    """The real schema rejects contracts whose parent records are absent."""

    database = migrated_postgres_database

    product = _product("TEST_PRODUCT")

    january = _period(
        "2024-01",
        PeriodType.MONTH,
        date(2024, 1, 1),
        date(2024, 1, 31),
    )

    contract = _contract(
        product_id=product.product_id,
        period_id=january.period_id,
        first_day_of_interest=date(2024, 1, 1),
        last_trading_day=date(2024, 1, 31),
    )

    with database.transaction() as connection:
        if missing_reference == "product":
            insert_periods(
                connection,
                schema=database.schema,
                periods=[
                    january,
                ],
            )
        else:
            insert_futures_products(
                connection,
                schema=database.schema,
                products=[
                    product,
                ],
            )

    with pytest.raises(ForeignKeyViolation):
        with database.transaction() as connection:
            insert_futures_contracts(
                connection,
                schema=database.schema,
                contracts=[
                    contract,
                ],
            )
