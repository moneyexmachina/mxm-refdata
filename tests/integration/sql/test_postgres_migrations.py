"""PostgreSQL integration tests for packaged reference-data migrations.

These tests execute the packaged migrations against a real PostgreSQL database
using one disposable schema per test.

They prove the schema contract relied on by the plain-SQL adapters: expected
tables and PostgreSQL representations, important relational constraints and
indexes, migration-ledger state, non-mutating inspection, idempotent replay,
and isolation from the public schema.

Entity-specific persistence and query semantics are tested separately by the
SQL/schema integration tests for periods, period cycles, futures products, and
futures contracts.
"""

from __future__ import annotations

import pytest
from psycopg import sql

from mxm.refdata.sql.migration_runner import MigrationRunner
from mxm.refdata.sql.postgres import PostgresDatabase, PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed

pytestmark = pytest.mark.postgres

_EXPECTED_TABLES = frozenset(
    {
        "schema_migrations",
        "periods",
        "period_cycles",
        "period_cycle_memberships",
        "futures_products",
        "futures_product_sources",
        "futures_contracts",
    }
)

_EXPECTED_INDEXES = frozenset(
    {
        "futures_contracts_product_id_index",
        "futures_contracts_period_id_index",
        "futures_contracts_active_range_index",
        "periods_date_range_index",
    }
)


def _fetch_rows(
    database: PostgresDatabase,
    query: ExecutableQuery,
    parameters: tuple[object, ...] | None = None,
) -> list[PostgresRow]:
    """Execute one inspection query and return all rows."""

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            if parameters is None:
                cursor.execute(query)
            else:
                cursor.execute(
                    query,
                    parameters,
                )

            return cursor.fetchall()


def _table_names(
    database: PostgresDatabase,
    *,
    schema: str,
) -> set[str]:
    """Return table names present in one PostgreSQL schema."""

    rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
            ORDER BY tablename
            """
        ),
        (schema,),
    )

    return {
        row[0]
        for row in rows
        if isinstance(
            row[0],
            str,
        )
    }


def _constraint_columns(
    database: PostgresDatabase,
    *,
    table: str,
    constraint_type: str,
) -> set[tuple[str, ...]]:
    """Return constrained column tuples for one table and constraint type."""

    rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT
                constraint_definition.oid,
                key_column.ordinality,
                attribute.attname
            FROM pg_catalog.pg_constraint AS constraint_definition
            JOIN pg_catalog.pg_class AS constrained_table
              ON constrained_table.oid = constraint_definition.conrelid
            JOIN pg_catalog.pg_namespace AS constrained_schema
              ON constrained_schema.oid = constrained_table.relnamespace
            JOIN unnest(constraint_definition.conkey)
                 WITH ORDINALITY
                 AS key_column(attnum, ordinality)
              ON TRUE
            JOIN pg_catalog.pg_attribute AS attribute
              ON attribute.attrelid = constrained_table.oid
             AND attribute.attnum = key_column.attnum
            WHERE constrained_schema.nspname = %s
              AND constrained_table.relname = %s
              AND constraint_definition.contype = %s
            ORDER BY
                constraint_definition.oid,
                key_column.ordinality
            """
        ),
        (
            database.schema,
            table,
            constraint_type,
        ),
    )

    columns_by_constraint: dict[
        int,
        list[str],
    ] = {}

    for row in rows:
        constraint_oid = row[0]
        ordinality = row[1]
        column = row[2]

        if isinstance(constraint_oid, bool) or not isinstance(constraint_oid, int):
            raise AssertionError(
                f"PostgreSQL returned an invalid constraint OID: {constraint_oid!r}"
            )

        if isinstance(ordinality, bool) or not isinstance(ordinality, int):
            raise AssertionError(
                f"PostgreSQL returned an invalid constraint ordinality: {ordinality!r}"
            )

        if not isinstance(column, str):
            raise AssertionError(
                f"PostgreSQL returned a non-text constraint column: {column!r}"
            )

        columns_by_constraint.setdefault(
            constraint_oid,
            [],
        ).append(column)

    return {tuple(columns) for columns in columns_by_constraint.values()}


def _foreign_keys(
    database: PostgresDatabase,
    *,
    table: str,
) -> set[tuple[str, str]]:
    """Return source-column to referenced-table foreign-key relationships."""

    rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT
                source_attribute.attname,
                referenced_table.relname
            FROM pg_catalog.pg_constraint AS constraint_definition
            JOIN pg_catalog.pg_class AS source_table
              ON source_table.oid = constraint_definition.conrelid
            JOIN pg_catalog.pg_namespace AS source_schema
              ON source_schema.oid = source_table.relnamespace
            JOIN pg_catalog.pg_class AS referenced_table
              ON referenced_table.oid = constraint_definition.confrelid
            JOIN unnest(constraint_definition.conkey)
                 WITH ORDINALITY
                 AS source_key(attnum, ordinality)
              ON TRUE
            JOIN pg_catalog.pg_attribute AS source_attribute
              ON source_attribute.attrelid = source_table.oid
             AND source_attribute.attnum = source_key.attnum
            WHERE source_schema.nspname = %s
              AND source_table.relname = %s
              AND constraint_definition.contype = 'f'
            ORDER BY
                source_attribute.attname,
                referenced_table.relname
            """
        ),
        (
            database.schema,
            table,
        ),
    )

    relationships: set[tuple[str, str]] = set()

    for row in rows:
        source_column = row[0]
        referenced_table = row[1]

        if not isinstance(
            source_column,
            str,
        ) or not isinstance(
            referenced_table,
            str,
        ):
            raise AssertionError(
                f"PostgreSQL returned an unexpected foreign-key row: {row!r}"
            )

        relationships.add(
            (
                source_column,
                referenced_table,
            )
        )

    return relationships


def test_packaged_migrations_create_expected_refdata_schema(
    postgres_database: PostgresDatabase,
) -> None:
    """Packaged migrations create the complete current refdata schema."""

    database = postgres_database
    runner = MigrationRunner(database)

    assert database.schema.startswith("refdata_test_")
    assert database.schema != "refdata"

    applied_versions = runner.migrate()

    assert applied_versions == ["001"]

    assert (
        _table_names(
            database,
            schema=database.schema,
        )
        == _EXPECTED_TABLES
    )

    jsonb_columns = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT
                table_name,
                column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND data_type = 'jsonb'
            ORDER BY
                table_name,
                column_name
            """
        ),
        (database.schema,),
    )

    assert jsonb_columns == [
        (
            "futures_product_sources",
            "notes",
        ),
        (
            "futures_products",
            "contract_rules",
        ),
    ]

    obsolete_columns = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'futures_products'
              AND column_name = 'canonical_specification'
            """
        ),
        (database.schema,),
    )

    assert obsolete_columns == []


def test_packaged_migrations_create_expected_relational_constraints(
    postgres_database: PostgresDatabase,
) -> None:
    """The migrated schema contains the relationships relied on by adapters."""

    database = postgres_database

    MigrationRunner(database).migrate()

    assert _constraint_columns(
        database,
        table="period_cycle_memberships",
        constraint_type="p",
    ) == {
        (
            "cycle_id",
            "period_id",
        ),
    }

    assert (
        "cycle_id",
        "cycle_instance",
        "cycle_element",
    ) in _constraint_columns(
        database,
        table="period_cycle_memberships",
        constraint_type="u",
    )

    assert ("source_relative_path",) in _constraint_columns(
        database,
        table="futures_product_sources",
        constraint_type="u",
    )

    assert (
        "product_id",
        "period_id",
    ) in _constraint_columns(
        database,
        table="futures_contracts",
        constraint_type="u",
    )

    assert _foreign_keys(
        database,
        table="period_cycle_memberships",
    ) == {
        (
            "cycle_id",
            "period_cycles",
        ),
        (
            "period_id",
            "periods",
        ),
    }

    assert _foreign_keys(
        database,
        table="futures_product_sources",
    ) == {
        (
            "product_id",
            "futures_products",
        ),
    }

    assert _foreign_keys(
        database,
        table="futures_contracts",
    ) == {
        (
            "period_id",
            "periods",
        ),
        (
            "product_id",
            "futures_products",
        ),
    }

    index_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT indexname
            FROM pg_catalog.pg_indexes
            WHERE schemaname = %s
            ORDER BY indexname
            """
        ),
        (database.schema,),
    )

    actual_indexes = {
        row[0]
        for row in index_rows
        if isinstance(
            row[0],
            str,
        )
    }

    assert _EXPECTED_INDEXES <= actual_indexes


def test_migration_state_is_versioned_current_and_idempotent(
    postgres_database: PostgresDatabase,
) -> None:
    """Migration ledger, inspection, replay, and schema isolation are correct."""

    database = postgres_database
    runner = MigrationRunner(database)

    discovered = {migration.version: migration for migration in runner.discover()}

    assert set(discovered) == {
        "000",
        "001",
    }

    initial_migration = discovered["001"]

    first_applied_versions = runner.migrate()

    assert first_applied_versions == ["001"]

    ledger_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT
                version,
                checksum
            FROM {}
            ORDER BY version
            """
        ).format(
            sql.Identifier(
                database.schema,
                "schema_migrations",
            )
        ),
    )

    assert ledger_rows == [
        (
            "001",
            initial_migration.checksum,
        ),
    ]

    inspection = runner.inspect()

    assert inspection.initialised is True
    assert inspection.applied_versions == ("001",)
    assert inspection.pending_versions == ()
    assert inspection.current is True

    replay_applied_versions = runner.migrate()

    assert replay_applied_versions == []

    replay_ledger_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT
                version,
                checksum
            FROM {}
            ORDER BY version
            """
        ).format(
            sql.Identifier(
                database.schema,
                "schema_migrations",
            )
        ),
    )

    assert replay_ledger_rows == ledger_rows

    public_tables = _table_names(
        database,
        schema="public",
    )

    assert public_tables.isdisjoint(_EXPECTED_TABLES)
