"""PostgreSQL integration tests for packaged reference-data migrations.

The shared integration fixtures provide an accepted MXM development runtime
and a uniquely named disposable PostgreSQL schema.

This module deliberately uses the unmigrated ``postgres_database`` fixture so
that it can prove schema creation, migration application, ledger state, and
idempotent replay from an empty starting point.
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
    """Execute a query in its own transaction and return all rows."""

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


def test_packaged_migrations_create_versioned_postgres_schema(
    postgres_database: PostgresDatabase,
) -> None:
    """Apply, inspect, and replay the packaged PostgreSQL migrations."""

    database = postgres_database
    runner = MigrationRunner(database)

    assert database.schema.startswith("refdata_test_")
    assert database.schema != "refdata"
    assert database.check_connection() is True

    discovered = {migration.version: migration for migration in runner.discover()}

    assert "000" in discovered
    assert "001" in discovered

    initial_migration = discovered["001"]

    first_applied_versions = runner.migrate()

    assert first_applied_versions == ["001"]

    table_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
            ORDER BY tablename
            """
        ),
        (database.schema,),
    )

    actual_tables = {row[0] for row in table_rows if isinstance(row[0], str)}

    assert actual_tables == _EXPECTED_TABLES

    ledger_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT version, checksum
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
        )
    ]

    canonical_specification_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'futures_products'
              AND column_name = 'canonical_specification'
            """
        ),
        (database.schema,),
    )

    assert canonical_specification_rows == [("jsonb",)]

    futures_contract_foreign_key_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT referenced_table.relname
            FROM pg_catalog.pg_constraint AS constraint_definition
            JOIN pg_catalog.pg_class AS source_table
              ON source_table.oid = constraint_definition.conrelid
            JOIN pg_catalog.pg_namespace AS source_schema
              ON source_schema.oid = source_table.relnamespace
            JOIN pg_catalog.pg_class AS referenced_table
              ON referenced_table.oid = constraint_definition.confrelid
            WHERE source_schema.nspname = %s
              AND source_table.relname = 'futures_contracts'
              AND constraint_definition.contype = 'f'
            ORDER BY referenced_table.relname
            """
        ),
        (database.schema,),
    )

    referenced_tables = {
        row[0] for row in futures_contract_foreign_key_rows if isinstance(row[0], str)
    }

    assert referenced_tables == {
        "futures_products",
        "periods",
    }

    membership_primary_key_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT array_agg(
                attribute.attname
                ORDER BY key_column.ordinality
            )
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
              AND constrained_table.relname =
                  'period_cycle_memberships'
              AND constraint_definition.contype = 'p'
            GROUP BY constraint_definition.oid
            """
        ),
        (database.schema,),
    )

    assert membership_primary_key_rows == [
        (
            [
                "cycle_id",
                "period_id",
            ],
        )
    ]

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

    actual_indexes = {row[0] for row in index_rows if isinstance(row[0], str)}

    assert _EXPECTED_INDEXES <= actual_indexes

    public_table_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        ),
    )

    public_tables = {row[0] for row in public_table_rows if isinstance(row[0], str)}

    assert public_tables.isdisjoint(_EXPECTED_TABLES)

    replay_applied_versions = runner.migrate()

    assert replay_applied_versions == []

    replay_ledger_rows = _fetch_rows(
        database,
        sql.SQL(
            """
            SELECT version, checksum
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
