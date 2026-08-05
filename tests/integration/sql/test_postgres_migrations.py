"""PostgreSQL integration tests for packaged reference-data migrations.

These tests resolve the accepted MXM development runtime through
``mxm-runtime`` and operate only inside uniquely named disposable PostgreSQL
schemas.

They may run only against the accepted ``mxm_dev`` database on ``monolith``.
They never operate against the operational ``refdata`` schema.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from psycopg import sql

from mxm.config import make_view
from mxm.refdata.composition import resolve_database_url
from mxm.refdata.sql.migration_runner import MigrationRunner
from mxm.refdata.sql.postgres import PostgresDatabase, PostgresRow
from mxm.runtime import (
    RuntimeContext,
    build_runtime_context,
    build_runtime_identity,
)

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


@pytest.fixture
def runtime_context() -> RuntimeContext:
    """Build the accepted MXM development runtime context."""

    identity = build_runtime_identity(
        app="mxm-refdata",
        environment="dev",
        role="default",
    )

    context = build_runtime_context(
        identity=identity,
    )

    _require_safe_test_context(context)

    return context


@pytest.fixture
def postgres_database(
    runtime_context: RuntimeContext,
) -> Generator[PostgresDatabase]:
    """Provide a PostgreSQL boundary using a unique disposable schema."""

    config = make_view(
        runtime_context.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )

    connection_url = resolve_database_url(
        ctx=runtime_context,
        config=config,
    )

    schema = f"refdata_test_{uuid4().hex[:12]}"

    if not schema.startswith("refdata_test_"):
        raise RuntimeError(
            "Refusing to use an unsafe PostgreSQL integration-test schema."
        )

    database = PostgresDatabase(
        connection_url,
        schema=schema,
    )

    try:
        yield database
    finally:
        _drop_schema(database)


def _require_safe_test_context(
    context: RuntimeContext,
) -> None:
    """Reject integration-test execution outside the accepted dev runtime."""

    identity = context.identity

    expected_identity = {
        "app": "mxm-refdata",
        "environment": "dev",
        "machine": "monolith",
        "substrate": "local-process",
        "role": "default",
    }

    actual_identity = {
        "app": identity.app,
        "environment": identity.environment,
        "machine": identity.machine,
        "substrate": identity.substrate,
        "role": identity.role,
    }

    if actual_identity != expected_identity:
        raise RuntimeError(
            "PostgreSQL integration tests require the accepted monolith "
            f"development identity. Expected {expected_identity!r}, "
            f"got {actual_identity!r}."
        )

    db_configs = context.db_configs

    if db_configs is None:
        raise RuntimeError("RuntimeContext does not contain database configuration.")

    try:
        db_config = db_configs["operational_state"]
    except KeyError as err:
        raise RuntimeError(
            "Database configuration 'operational_state' is missing."
        ) from err

    expected_database = {
        "driver": "postgresql",
        "host": "localhost",
        "port": 5432,
        "name": "mxm_dev",
        "user": "mxm_dev_app",
    }

    actual_database = {
        "driver": str(db_config["driver"]),
        "host": str(db_config["host"]),
        "port": int(db_config["port"]),
        "name": str(db_config["name"]),
        "user": str(db_config["user"]),
    }

    if actual_database != expected_database:
        raise RuntimeError(
            "PostgreSQL integration tests require the accepted mxm_dev "
            f"database target. Expected {expected_database!r}, "
            f"got {actual_database!r}."
        )


def _fetch_rows(
    database: PostgresDatabase,
    query: ExecutableQuery,
    parameters: tuple[object, ...] | None = None,
) -> list[PostgresRow]:
    """Execute a query and return all result rows."""

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


def _drop_schema(
    database: PostgresDatabase,
) -> None:
    """Drop only the validated disposable schema owned by the test."""

    if not database.schema.startswith("refdata_test_"):
        raise RuntimeError(
            f"Refusing to drop a non-test PostgreSQL schema: {database.schema!r}."
        )

    if database.schema == "refdata":
        raise RuntimeError("Refusing to drop the operational refdata schema.")

    query = sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
        sql.Identifier(database.schema)
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)


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
