"""PostgreSQL integration tests for futures-product SQL/schema compatibility.

These tests exercise the real migrated PostgreSQL schema. They prove that the
futures-product SQL adapter matches that schema, including operational product
round-tripping, nested contract-rule JSONB representation, product conflict
semantics, evolving source provenance, and relational source constraints.

Operational ``FuturesProduct`` state and source provenance are deliberately
persisted and tested as separate concerns.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from psycopg.errors import ForeignKeyViolation, UniqueViolation

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
from mxm.refdata.sources.futures_product import (
    FuturesProductSourceMetadata,
)
from mxm.refdata.sql.futures_products import (
    FuturesProductConflictError,
    fetch_futures_product_sources,
    fetch_futures_products,
    fetch_futures_products_by_ids,
    insert_futures_products,
    upsert_futures_product_sources,
)
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres

_SOURCE_REVISION_A = "a" * 40
_SOURCE_REVISION_B = "b" * 40


def _contract_rules(
    *,
    with_weekday: bool = True,
) -> ContractRules:
    """Construct representative contract-generation rules."""

    if with_weekday:
        last_trading_rule = LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
            n_reference=3,
            business_day_offset=0,
            weekday=Weekday.from_str("Friday"),
        )
    else:
        last_trading_rule = LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
            n_reference=-3,
            business_day_offset=0,
        )

    return ContractRules(
        last_trading_rule=last_trading_rule,
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


def _product(
    product_id: str = "TEST_PRODUCT",
    *,
    optional_values: bool = True,
    with_weekday: bool = True,
) -> FuturesProduct:
    """Construct a representative complete operational futures product."""

    return FuturesProduct(
        product_id=product_id,
        asset_class="metals",
        venue="COMEX",
        description=f"{product_id} Futures",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="HMUZ",
        listing_rule="Quarterly contracts",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="Third Friday of delivery month",
        expiry_rule="Delivery month",
        trading_calendar="CME",
        contract_rules=_contract_rules(
            with_weekday=with_weekday,
        ),
        trading_hours=("23:00 - 22:00 UTC" if optional_values else None),
        tick_size=(0.1 if optional_values else None),
        tick_value=(10.0 if optional_values else None),
        initial_margin=(5000.0 if optional_values else None),
        maintenance_margin=(4500.0 if optional_values else None),
    )


def _source_metadata(
    *,
    source_relative_path: str = "metals/test_product.json",
    source_digest: str = "c" * 64,
    notes: tuple[str, ...] = (
        "Curated from exchange specification.",
        "Reviewed manually.",
    ),
) -> FuturesProductSourceMetadata:
    """Construct representative futures-product source metadata."""

    return FuturesProductSourceMetadata(
        schema_version="futures_product.v1",
        source_relative_path=source_relative_path,
        source_digest=source_digest,
        created_at=date(
            2026,
            6,
            1,
        ),
        updated_at=date(
            2026,
            7,
            1,
        ),
        review_status="reviewed",
        curator="mxm",
        source_type="exchange_specification",
        source_url="https://example.test/product",
        source_accessed_at=date(
            2026,
            5,
            31,
        ),
        curation_method="manual",
        assistance="llm-assisted",
        notes=notes,
    )


def test_futures_products_round_trip_and_filter_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Complete operational products round-trip through the real schema."""

    database = migrated_postgres_database

    complete_product = _product(
        "COMPLETE_PRODUCT",
    )
    minimal_product = _product(
        "MINIMAL_PRODUCT",
        optional_values=False,
        with_weekday=False,
    )

    expected_products = {
        complete_product.product_id: complete_product,
        minimal_product.product_id: minimal_product,
    }

    with database.transaction() as connection:
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                minimal_product,
                complete_product,
            ],
        )

    with database.transaction() as connection:
        persisted_products = fetch_futures_products(
            connection,
            schema=database.schema,
        )

        selected_products = fetch_futures_products_by_ids(
            connection,
            schema=database.schema,
            product_ids=[
                "MISSING_PRODUCT",
                complete_product.product_id,
                complete_product.product_id,
            ],
        )

    assert persisted_products == expected_products

    assert selected_products == {
        complete_product.product_id: complete_product,
    }


def test_futures_product_persistence_uses_postgres_conflict_semantics(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Identical product state is idempotent while conflicting state is rejected."""

    database = migrated_postgres_database

    product = _product()

    with database.transaction() as connection:
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product,
            ],
        )

    with database.transaction() as connection:
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product,
                product,
            ],
        )

    conflicting_product = replace(
        product,
        description="Changed operational definition",
    )

    with pytest.raises(
        FuturesProductConflictError,
        match=r"Persisted futures product conflicts.*TEST_PRODUCT",
    ):
        with database.transaction() as connection:
            insert_futures_products(
                connection,
                schema=database.schema,
                products=[
                    conflicting_product,
                ],
            )

    with database.transaction() as connection:
        persisted_products = fetch_futures_products(
            connection,
            schema=database.schema,
        )

    assert persisted_products == {
        product.product_id: product,
    }


def test_futures_product_source_state_round_trips_and_updates_through_postgres(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """Source metadata and repository revision may evolve independently."""

    database = migrated_postgres_database

    product = _product()
    original_metadata = _source_metadata()

    with database.transaction() as connection:
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product,
            ],
        )

        upsert_futures_product_sources(
            connection,
            schema=database.schema,
            sources=[
                (
                    product.product_id,
                    original_metadata,
                    _SOURCE_REVISION_A,
                ),
            ],
        )

    with database.transaction() as connection:
        original_sources = fetch_futures_product_sources(
            connection,
            schema=database.schema,
        )

    assert original_sources == {
        product.product_id: (
            original_metadata,
            _SOURCE_REVISION_A,
        ),
    }

    updated_metadata = replace(
        original_metadata,
        source_digest="d" * 64,
        updated_at=date(
            2026,
            8,
            1,
        ),
        review_status="accepted",
        notes=(
            "Curated from exchange specification.",
            "Reviewed and accepted.",
        ),
    )

    with database.transaction() as connection:
        upsert_futures_product_sources(
            connection,
            schema=database.schema,
            sources=[
                (
                    product.product_id,
                    updated_metadata,
                    _SOURCE_REVISION_B,
                ),
            ],
        )

    with database.transaction() as connection:
        updated_sources = fetch_futures_product_sources(
            connection,
            schema=database.schema,
        )

        persisted_products = fetch_futures_products(
            connection,
            schema=database.schema,
        )

    assert updated_sources == {
        product.product_id: (
            updated_metadata,
            _SOURCE_REVISION_B,
        ),
    }

    assert persisted_products == {
        product.product_id: product,
    }


def test_futures_product_source_relational_constraints_are_enforced(
    migrated_postgres_database: PostgresDatabase,
) -> None:
    """The real schema enforces source ownership and unique source paths."""

    database = migrated_postgres_database

    orphan_metadata = _source_metadata(
        source_relative_path="metals/orphan.json",
    )

    with pytest.raises(ForeignKeyViolation):
        with database.transaction() as connection:
            upsert_futures_product_sources(
                connection,
                schema=database.schema,
                sources=[
                    (
                        "MISSING_PRODUCT",
                        orphan_metadata,
                        _SOURCE_REVISION_A,
                    ),
                ],
            )

    product_a = _product(
        "PRODUCT_A",
    )
    product_b = _product(
        "PRODUCT_B",
    )

    shared_path = "metals/shared_source.json"

    metadata_a = _source_metadata(
        source_relative_path=shared_path,
        source_digest="c" * 64,
    )
    metadata_b = _source_metadata(
        source_relative_path=shared_path,
        source_digest="d" * 64,
    )

    with database.transaction() as connection:
        insert_futures_products(
            connection,
            schema=database.schema,
            products=[
                product_a,
                product_b,
            ],
        )

        upsert_futures_product_sources(
            connection,
            schema=database.schema,
            sources=[
                (
                    product_a.product_id,
                    metadata_a,
                    _SOURCE_REVISION_A,
                ),
            ],
        )

    with pytest.raises(UniqueViolation):
        with database.transaction() as connection:
            upsert_futures_product_sources(
                connection,
                schema=database.schema,
                sources=[
                    (
                        product_b.product_id,
                        metadata_b,
                        _SOURCE_REVISION_B,
                    ),
                ],
            )

    with database.transaction() as connection:
        persisted_sources = fetch_futures_product_sources(
            connection,
            schema=database.schema,
        )

    assert persisted_sources == {
        product_a.product_id: (
            metadata_a,
            _SOURCE_REVISION_A,
        ),
    }
