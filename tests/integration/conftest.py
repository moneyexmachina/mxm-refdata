"""Shared fixtures for PostgreSQL integration tests.

These fixtures resolve the accepted MXM development runtime through the normal
mxm-refdata composition root and provide uniquely named disposable PostgreSQL
schemas.

Integration tests may run only against the accepted ``mxm_dev`` database on
``monolith``. Tests never operate on the operational ``refdata`` schema.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from uuid import uuid4

import pytest
from psycopg import sql

from mxm.refdata.composition import build_refdata
from mxm.refdata.sql.migration_runner import MigrationRunner
from mxm.refdata.sql.postgres import PostgresDatabase
from mxm.runtime import (
    RuntimeContext,
    build_runtime_context,
    build_runtime_identity,
)

_TEST_SCHEMA_PATTERN = re.compile(
    r"^refdata_test_[0-9a-f]{12}$",
    flags=re.ASCII,
)


@pytest.fixture(scope="session")
def runtime_context() -> RuntimeContext:
    """Build and validate the accepted MXM development runtime context."""

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


@pytest.fixture(scope="session")
def configured_postgres_database(
    runtime_context: RuntimeContext,
) -> PostgresDatabase:
    """Resolve the accepted PostgreSQL target through normal composition.

    The returned boundary owns the operational ``refdata`` schema but is never
    itself used for integration-test SQL. Individual tests derive isolated
    disposable-schema boundaries from it.
    """

    refdata = build_refdata(runtime_context)

    return refdata.database


@pytest.fixture
def postgres_database(
    configured_postgres_database: PostgresDatabase,
) -> Generator[PostgresDatabase]:
    """Provide an unmigrated database boundary for one disposable schema.

    Each test receives a unique schema on the configured development
    PostgreSQL target. The schema does not need to exist when the fixture is
    yielded, allowing migration tests to prove creation from an empty starting
    point.

    The disposable schema is dropped during fixture teardown, including after
    test failures.
    """

    schema = f"refdata_test_{uuid4().hex[:12]}"

    _require_safe_test_schema(schema)

    database = configured_postgres_database.with_schema(schema)

    try:
        yield database
    finally:
        _drop_test_schema(database)


@pytest.fixture
def migrated_postgres_database(
    postgres_database: PostgresDatabase,
) -> PostgresDatabase:
    """Provide a disposable PostgreSQL schema with all migrations applied."""

    runner = MigrationRunner(postgres_database)

    applied_versions = runner.migrate()

    if "001" not in applied_versions:
        raise RuntimeError(
            "Expected initial refdata migration '001' to be applied to a "
            "new disposable PostgreSQL schema, "
            f"got {applied_versions!r}."
        )

    return postgres_database


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


def _require_safe_test_schema(
    schema: str,
) -> None:
    """Reject any schema name outside the generated test-schema form."""

    if _TEST_SCHEMA_PATTERN.fullmatch(schema) is None:
        raise RuntimeError(
            "Refusing to operate on an unsafe PostgreSQL integration-test "
            f"schema: {schema!r}."
        )

    if schema == "refdata":
        raise RuntimeError("Refusing to operate on the operational refdata schema.")


def _drop_test_schema(
    database: PostgresDatabase,
) -> None:
    """Drop only the validated disposable schema owned by one test."""

    _require_safe_test_schema(database.schema)

    query = sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
        sql.Identifier(database.schema)
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
