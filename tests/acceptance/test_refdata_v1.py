"""Acceptance test for the complete configured MXM V1 reference-data universe.

This test requires the private MXM development deployment: the real
``mxm-config-store``, secrets configuration, ``mxm-refdata-source`` repository,
and local PostgreSQL instance on monolith.

It resolves the application through the normal runtime composition root, then
derives only a disposable PostgreSQL schema from the configured operational
database boundary. The complete configured V1 product universe is materialised
through the real application and inspected through the real Reader and
diagnostics capabilities.

The test never operates on the operational ``refdata`` schema.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from uuid import uuid4

import pytest
from psycopg import sql

from mxm.refdata.composition import build_refdata as compose_refdata
from mxm.refdata.reader import RefDataReader
from mxm.refdata.runtime import RefData
from mxm.refdata.sql.diagnostics import RefDataRowCounts
from mxm.refdata.sql.postgres import PostgresDatabase
from mxm.runtime import (
    RuntimeContext,
    build_runtime_context,
    build_runtime_identity,
)

pytestmark = [
    pytest.mark.acceptance,
]

_ACCEPTANCE_SCHEMA_PATTERN = re.compile(
    r"^refdata_acceptance_[0-9a-f]{12}$",
    flags=re.ASCII,
)

_EXPECTED_COUNTS = RefDataRowCounts(
    products=86,
    product_sources=86,
    periods=799,
    contracts=31_490,
    cycles=2,
    memberships=752,
)

_REPRESENTATIVE_PRODUCT_IDS = {
    "cbot_10_year_us_treasury_note_futures",
    "cbot_30_day_federal_funds_futures",
    "cbot_bloomberg_hy_credit_futures",
    "cme_3_month_sofr_futures",
    "cme_emini_snp500_futures",
    "cme_eurusd_futures",
    "comex_gold_futures",
    "nymex_wti_crude_oil_futures",
}


@pytest.fixture
def v1_refdata() -> Generator[RefData]:
    """Provide the real V1 application on one disposable PostgreSQL schema."""

    identity = build_runtime_identity(
        app="mxm-refdata",
        environment="dev",
        role="default",
    )

    context = build_runtime_context(
        identity=identity,
    )

    _require_acceptance_context(context)

    operational_refdata = compose_refdata(context)

    schema = f"refdata_acceptance_{uuid4().hex[:12]}"

    _require_safe_acceptance_schema(schema)

    database = operational_refdata.database.with_schema(schema)

    reader = RefDataReader(
        database=database,
    )

    refdata = RefData(
        config=operational_refdata.config,
        database=database,
        reader=reader,
    )

    try:
        yield refdata
    finally:
        _drop_acceptance_schema(database)


def _require_acceptance_context(
    context: RuntimeContext,
) -> None:
    """Reject acceptance execution outside the accepted monolith dev runtime."""

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
            "V1 reference-data acceptance requires the accepted monolith "
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
            "V1 reference-data acceptance requires the accepted mxm_dev "
            f"database target. Expected {expected_database!r}, "
            f"got {actual_database!r}."
        )


def _require_safe_acceptance_schema(
    schema: str,
) -> None:
    """Reject any schema outside the generated acceptance-schema form."""

    if _ACCEPTANCE_SCHEMA_PATTERN.fullmatch(schema) is None:
        raise RuntimeError(
            f"Refusing to operate on an unsafe V1 acceptance schema: {schema!r}."
        )

    if schema == "refdata":
        raise RuntimeError("Refusing to operate on the operational refdata schema.")


def _drop_acceptance_schema(
    database: PostgresDatabase,
) -> None:
    """Drop only the validated disposable schema owned by the acceptance test."""

    _require_safe_acceptance_schema(database.schema)

    query = sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
        sql.Identifier(database.schema)
    )

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)


def test_complete_configured_v1_refdata_is_operationally_ready(
    v1_refdata: RefData,
) -> None:
    """The private configured V1 universe materialises completely and is ready."""

    refdata = v1_refdata

    refdata.build()

    report = refdata.diagnostics()

    assert report.migration is not None
    assert report.migration.initialised is True
    assert report.migration.current is True

    assert report.counts == _EXPECTED_COUNTS

    assert all(result.status == "pass" for result in report.results)

    assert report.ready is True

    products = refdata.reader.get_products()

    assert len(products) == 86

    product_ids = {product.product_id for product in products}

    assert _REPRESENTATIVE_PRODUCT_IDS <= product_ids

    for product_id in sorted(_REPRESENTATIVE_PRODUCT_IDS):
        product = refdata.reader.get_product_by_id(product_id)

        assert product.product_id == product_id

        contracts = refdata.reader.get_contracts_for_product(product_id)

        assert contracts, (
            "Expected the configured V1 product to materialise at least one "
            f"futures contract: {product_id!r}."
        )

        assert all(contract.product_id == product_id for contract in contracts)
