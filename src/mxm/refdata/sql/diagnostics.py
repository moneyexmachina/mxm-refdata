"""Plain-SQL diagnostic observations for materialised MXM reference data.

This module owns PostgreSQL queries that inspect materialised reference-data
state but do not belong naturally to one individual persistence entity.

It returns database facts only. Interpretation of those facts as healthy,
unhealthy, ready, or not ready belongs to ``mxm.refdata.diagnostics``.

All functions operate on a caller-provided Psycopg connection. They do not
open, commit, or roll back transactions.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import Connection, sql

from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed


class RefDataDiagnosticsPersistenceError(RuntimeError):
    """Raised when persisted diagnostic state cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class RefDataRowCounts:
    """Row counts for the materialised reference-data tables."""

    products: int
    product_sources: int
    periods: int
    contracts: int
    cycles: int
    memberships: int


# ---------------------------------------------------------------------
# MATERIALISED STATE OBSERVATIONS
# ---------------------------------------------------------------------


def fetch_refdata_row_counts(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> RefDataRowCounts:
    """Return row counts for the materialised reference-data tables.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the materialised refdata tables.

    Returns:
        Counts for operational products, product provenance, periods,
        futures contracts, cycles, and cycle memberships.

    Raises:
        RefDataDiagnosticsPersistenceError:
            If PostgreSQL returns an unexpected result shape or value type.
    """

    query = sql.SQL(
        """
        SELECT
            (SELECT COUNT(*) FROM {}) AS products,
            (SELECT COUNT(*) FROM {}) AS product_sources,
            (SELECT COUNT(*) FROM {}) AS periods,
            (SELECT COUNT(*) FROM {}) AS contracts,
            (SELECT COUNT(*) FROM {}) AS cycles,
            (SELECT COUNT(*) FROM {}) AS memberships
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_products",
        ),
        sql.Identifier(
            schema,
            "futures_product_sources",
        ),
        sql.Identifier(
            schema,
            "periods",
        ),
        sql.Identifier(
            schema,
            "futures_contracts",
        ),
        sql.Identifier(
            schema,
            "period_cycles",
        ),
        sql.Identifier(
            schema,
            "period_cycle_memberships",
        ),
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    if len(rows) != 1:
        raise RefDataDiagnosticsPersistenceError(
            "Reference-data row-count query returned an unexpected "
            f"number of rows: {rows!r}"
        )

    row = rows[0]

    if len(row) != 6:
        raise RefDataDiagnosticsPersistenceError(
            f"Reference-data row-count query returned an unexpected row shape: {row!r}"
        )

    (
        products,
        product_sources,
        periods,
        contracts,
        cycles,
        memberships,
    ) = row

    return RefDataRowCounts(
        products=_require_count(
            products,
            field="products",
        ),
        product_sources=_require_count(
            product_sources,
            field="product_sources",
        ),
        periods=_require_count(
            periods,
            field="periods",
        ),
        contracts=_require_count(
            contracts,
            field="contracts",
        ),
        cycles=_require_count(
            cycles,
            field="cycles",
        ),
        memberships=_require_count(
            memberships,
            field="memberships",
        ),
    )


# ---------------------------------------------------------------------
# PRIVATE QUERY HELPERS
# ---------------------------------------------------------------------


def _fetch_rows(
    connection: Connection[PostgresRow],
    query: ExecutableQuery,
    parameters: tuple[object, ...] | None = None,
) -> list[PostgresRow]:
    """Execute one query and return all result rows."""

    with connection.cursor() as cursor:
        if parameters is None:
            cursor.execute(query)
        else:
            cursor.execute(
                query,
                parameters,
            )

        return cursor.fetchall()


def _require_count(
    value: object,
    *,
    field: str,
) -> int:
    """Return one validated non-negative PostgreSQL count."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise RefDataDiagnosticsPersistenceError(
            f"Reference-data count {field!r} must be an integer, got {value!r}"
        )

    if value < 0:
        raise RefDataDiagnosticsPersistenceError(
            f"Reference-data count {field!r} cannot be negative, got {value!r}"
        )

    return value
