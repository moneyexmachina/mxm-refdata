"""Integration tests for reference-data materialisation lifecycle behaviour.

These tests exercise repeated build, transactional failure, and destructive
rebuild against a real disposable PostgreSQL schema.

They prove that the complete materialisation capability is idempotent, that a
late persistence conflict rolls back earlier mutations in the same persistence
transaction, and that rebuild replaces incompatible owned-schema state with
the configured desired state.

Detailed lifecycle control flow, protected-schema validation, and individual
SQL conflict semantics are tested separately by unit tests and SQL/schema
integration tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from psycopg import sql

from mxm.config import MXMConfig
from mxm.refdata.materialisation import (
    build_refdata,
    rebuild_refdata,
)
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sources.futures_product import (
    FuturesProductSourceMetadata,
)
from mxm.refdata.sql.diagnostics import (
    RefDataRowCounts,
    fetch_refdata_row_counts,
)
from mxm.refdata.sql.futures_contracts import (
    FuturesContractConflictError,
)
from mxm.refdata.sql.futures_products import (
    fetch_futures_product_sources,
)
from mxm.refdata.sql.postgres import PostgresDatabase

pytestmark = pytest.mark.postgres

_FIXTURE_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "futures_products"
)

_PRODUCT_ID = "test_quarterly_futures"
_CONTRACT_ID = f"{_PRODUCT_ID}.Jun-2024"

_DEGRADED_REVIEW_STATUS = "deliberately_degraded"
_CONFLICTING_CONTRACT_SIZE = 2000.0

_SENTINEL_TABLE = "lifecycle_rebuild_sentinel"

_EXPECTED_COUNTS = RefDataRowCounts(
    products=1,
    product_sources=1,
    periods=17,
    contracts=4,
    cycles=2,
    memberships=16,
)


def _config() -> MXMConfig:
    """Return the controlled configuration for lifecycle integration."""

    return cast(
        MXMConfig,
        {
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": str(_FIXTURE_SOURCE_ROOT),
            "REFDATA_CONTRACT_START_DATE": "2024-01-01",
            "REFDATA_CONTRACT_END_DATE": "2024-12-31",
        },
    )


def _reader(
    database: PostgresDatabase,
) -> RefDataReader:
    """Construct the real Reader for one integration-test database."""

    return RefDataReader(
        database=database,
    )


def _fetch_product_source_state(
    database: PostgresDatabase,
) -> tuple[
    FuturesProductSourceMetadata,
    str,
]:
    """Return persisted provenance and revision for the synthetic product."""

    with database.transaction() as connection:
        sources = fetch_futures_product_sources(
            connection,
            schema=database.schema,
        )

    try:
        return sources[_PRODUCT_ID]
    except KeyError as err:
        raise AssertionError(
            f"Expected persisted product source for {_PRODUCT_ID!r}."
        ) from err


def _fetch_counts(
    database: PostgresDatabase,
) -> RefDataRowCounts:
    """Return aggregate persisted reference-data row counts."""

    with database.transaction() as connection:
        return fetch_refdata_row_counts(
            connection,
            schema=database.schema,
        )


def _set_product_source_review_status(
    database: PostgresDatabase,
    review_status: str,
) -> None:
    """Deliberately alter persisted source provenance for lifecycle testing."""

    query = sql.SQL(
        """
        UPDATE {}
        SET review_status = %s
        WHERE product_id = %s
        """
    ).format(
        sql.Identifier(
            database.schema,
            "futures_product_sources",
        )
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    review_status,
                    _PRODUCT_ID,
                ),
            )

            if cursor.rowcount != 1:
                raise AssertionError(
                    "Expected exactly one futures-product provenance row "
                    f"to be updated, got {cursor.rowcount}."
                )


def _set_contract_size(
    database: PostgresDatabase,
    contract_size: float,
) -> None:
    """Deliberately alter one persisted contract for lifecycle testing."""

    query = sql.SQL(
        """
        UPDATE {}
        SET contract_size = %s
        WHERE contract_id = %s
        """
    ).format(
        sql.Identifier(
            database.schema,
            "futures_contracts",
        )
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    contract_size,
                    _CONTRACT_ID,
                ),
            )

            if cursor.rowcount != 1:
                raise AssertionError(
                    "Expected exactly one futures contract to be updated, "
                    f"got {cursor.rowcount}."
                )


def _create_sentinel_table(
    database: PostgresDatabase,
) -> None:
    """Create a table that can survive only if rebuild does not drop schema."""

    query = sql.SQL(
        """
        CREATE TABLE {} (
            sentinel_id integer PRIMARY KEY
        )
        """
    ).format(
        sql.Identifier(
            database.schema,
            _SENTINEL_TABLE,
        )
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)


def _table_exists(
    database: PostgresDatabase,
    table_name: str,
) -> bool:
    """Return whether one table exists in the database boundary's schema."""

    query = sql.SQL(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
              AND tablename = %s
        )
        """
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    database.schema,
                    table_name,
                ),
            )

            row = cursor.fetchone()

    if row is None or not isinstance(
        row[0],
        bool,
    ):
        raise AssertionError(
            f"PostgreSQL returned an unexpected table-existence result: {row!r}."
        )

    return row[0]


def test_repeated_build_is_idempotent(
    postgres_database: PostgresDatabase,
) -> None:
    """Running the complete build twice leaves identical materialised state."""

    database = postgres_database
    reader = _reader(database)

    build_refdata(
        config=_config(),
        database=database,
    )

    counts_before = _fetch_counts(database)
    products_before = reader.get_products()
    periods_before = reader.get_periods()
    cycles_before = reader.get_cycles()
    month_memberships_before = reader.get_cycle_memberships("CALENDAR_MONTHS")
    quarter_memberships_before = reader.get_cycle_memberships("CALENDAR_QUARTERS")
    contracts_before = reader.get_contracts_for_product(_PRODUCT_ID)
    source_before = _fetch_product_source_state(database)

    assert counts_before == _EXPECTED_COUNTS

    build_refdata(
        config=_config(),
        database=database,
    )

    assert _fetch_counts(database) == counts_before

    assert reader.get_products() == products_before
    assert reader.get_periods() == periods_before
    assert reader.get_cycles() == cycles_before

    assert reader.get_cycle_memberships("CALENDAR_MONTHS") == month_memberships_before

    assert (
        reader.get_cycle_memberships("CALENDAR_QUARTERS") == quarter_memberships_before
    )

    assert reader.get_contracts_for_product(_PRODUCT_ID) == contracts_before

    assert _fetch_product_source_state(database) == source_before


def test_failed_build_rolls_back_complete_persistence_transaction(
    postgres_database: PostgresDatabase,
) -> None:
    """A late contract conflict rolls back an earlier provenance mutation."""

    database = postgres_database
    reader = _reader(database)

    build_refdata(
        config=_config(),
        database=database,
    )

    desired_metadata, desired_revision = _fetch_product_source_state(database)

    desired_contract = reader.get_contract_by_id(_CONTRACT_ID)

    assert desired_metadata.review_status != _DEGRADED_REVIEW_STATUS
    assert desired_contract.contract_size != _CONFLICTING_CONTRACT_SIZE

    _set_product_source_review_status(
        database,
        _DEGRADED_REVIEW_STATUS,
    )
    _set_contract_size(
        database,
        _CONFLICTING_CONTRACT_SIZE,
    )

    degraded_metadata, degraded_revision = _fetch_product_source_state(database)
    degraded_contract = reader.get_contract_by_id(_CONTRACT_ID)

    assert degraded_metadata.review_status == _DEGRADED_REVIEW_STATUS
    assert degraded_revision == desired_revision
    assert degraded_contract.contract_size == _CONFLICTING_CONTRACT_SIZE

    with pytest.raises(FuturesContractConflictError):
        build_refdata(
            config=_config(),
            database=database,
        )

    metadata_after_failure, revision_after_failure = _fetch_product_source_state(
        database
    )
    contract_after_failure = reader.get_contract_by_id(_CONTRACT_ID)

    assert metadata_after_failure.review_status == (_DEGRADED_REVIEW_STATUS)
    assert revision_after_failure == degraded_revision

    assert contract_after_failure.contract_size == (_CONFLICTING_CONTRACT_SIZE)

    assert _fetch_counts(database) == _EXPECTED_COUNTS


def test_rebuild_replaces_existing_schema_with_desired_state(
    postgres_database: PostgresDatabase,
) -> None:
    """Rebuild destroys incompatible owned state and rematerialises desired state."""

    database = postgres_database
    reader = _reader(database)

    build_refdata(
        config=_config(),
        database=database,
    )

    desired_metadata, desired_revision = _fetch_product_source_state(database)

    desired_contract = reader.get_contract_by_id(_CONTRACT_ID)

    _set_contract_size(
        database,
        _CONFLICTING_CONTRACT_SIZE,
    )
    _create_sentinel_table(database)

    corrupted_contract = reader.get_contract_by_id(_CONTRACT_ID)

    assert corrupted_contract.contract_size == (_CONFLICTING_CONTRACT_SIZE)
    assert _table_exists(
        database,
        _SENTINEL_TABLE,
    )

    rebuild_refdata(
        config=_config(),
        database=database,
    )

    assert not _table_exists(
        database,
        _SENTINEL_TABLE,
    )

    assert _fetch_counts(database) == _EXPECTED_COUNTS

    restored_contract = reader.get_contract_by_id(_CONTRACT_ID)

    assert restored_contract == desired_contract

    restored_metadata, restored_revision = _fetch_product_source_state(database)

    assert restored_metadata == desired_metadata
    assert restored_revision == desired_revision

    assert [
        contract.period_id for contract in reader.get_contracts_for_product(_PRODUCT_ID)
    ] == [
        "Mar-2024",
        "Jun-2024",
        "Sep-2024",
        "Dec-2024",
    ]
