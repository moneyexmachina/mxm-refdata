"""Plain-SQL persistence operations for reference periods.

This module owns the PostgreSQL representation of ``Period`` objects.

All functions operate on a caller-provided Psycopg connection. They do not
open, commit, or roll back transactions. Transaction ownership belongs to the
higher-level materialisation or query operation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from psycopg import Connection, sql

from mxm.refdata.models import Period, PeriodType
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed


class PeriodPersistenceError(RuntimeError):
    """Base error for invalid or inconsistent persisted period state."""


class PeriodConflictError(PeriodPersistenceError):
    """Raised when one period ID identifies different period values."""


def fetch_periods(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> dict[str, Period]:
    """Return all persisted periods keyed by period ID.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``periods`` table.

    Returns:
        Persisted periods keyed by their stable period identifiers.
    """

    query = sql.SQL(
        """
        SELECT
            period_id,
            period_type,
            first_date,
            last_date
        FROM {}
        ORDER BY
            first_date,
            last_date,
            period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "periods",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    return _periods_from_rows(rows)


def fetch_periods_by_ids(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    period_ids: Sequence[str],
) -> dict[str, Period]:
    """Return requested persisted periods keyed by period ID.

    Missing requested IDs are absent from the returned mapping.

    Duplicate requested IDs are collapsed before querying, and the SQL
    parameter array is deterministically ordered.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``periods`` table.
        period_ids:
            Period identifiers to retrieve.

    Returns:
        Matching persisted periods keyed by their stable period identifiers.
    """

    unique_period_ids = sorted(set(period_ids))

    if not unique_period_ids:
        return {}

    query = sql.SQL(
        """
        SELECT
            period_id,
            period_type,
            first_date,
            last_date
        FROM {}
        WHERE period_id = ANY(%s::text[])
        ORDER BY period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "periods",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (unique_period_ids,),
    )

    return _periods_from_rows(rows)


def fetch_periods_by_types(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    period_types: Sequence[PeriodType],
) -> dict[str, Period]:
    """Return persisted periods having one of the requested period types.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``periods`` table.
        period_types:
            Period types to include.

    Returns:
        Matching periods keyed by their stable period identifiers.
    """

    encoded_period_types = sorted({period_type.name for period_type in period_types})

    if not encoded_period_types:
        return {}

    query = sql.SQL(
        """
        SELECT
            period_id,
            period_type,
            first_date,
            last_date
        FROM {}
        WHERE period_type = ANY(%s::text[])
        ORDER BY
            first_date,
            last_date,
            period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "periods",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (encoded_period_types,),
    )

    return _periods_from_rows(rows)


def fetch_periods_in_range(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    start_date: date,
    end_date: date,
) -> dict[str, Period]:
    """Return periods wholly contained in the requested date range.

    This preserves the current materialisation semantics:

    - ``period.first_date >= start_date``
    - ``period.last_date <= end_date``

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``periods`` table.
        start_date:
            Inclusive lower bound for period start dates.
        end_date:
            Inclusive upper bound for period end dates.

    Returns:
        Matching periods keyed by their stable period identifiers.

    Raises:
        ValueError:
            If ``start_date`` is after ``end_date``.
    """

    if start_date > end_date:
        raise ValueError(
            f"start_date must not be after end_date: {start_date!r} > {end_date!r}"
        )

    query = sql.SQL(
        """
        SELECT
            period_id,
            period_type,
            first_date,
            last_date
        FROM {}
        WHERE first_date >= %s
          AND last_date <= %s
        ORDER BY
            first_date,
            last_date,
            period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "periods",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (
            start_date,
            end_date,
        ),
    )

    return _periods_from_rows(rows)


def insert_periods(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    periods: Sequence[Period],
) -> None:
    """Persist periods idempotently while rejecting identity conflicts.

    A period absent from the database is inserted.

    A period already present with identical values is accepted as an
    idempotent no-op.

    A period already present with different values raises
    ``PeriodConflictError``. The caller should allow that exception to leave
    the enclosing transaction so that the complete materialisation operation
    rolls back.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``periods`` table.
        periods:
            Domain periods to persist.

    Raises:
        PeriodConflictError:
            If duplicate input or persisted state assigns different values to
            the same period ID.
        PeriodPersistenceError:
            If an expected row is absent after insertion.
    """

    periods_by_id = _normalise_periods(periods)

    if not periods_by_id:
        return

    query = sql.SQL(
        """
        INSERT INTO {} (
            period_id,
            period_type,
            first_date,
            last_date
        )
        VALUES (
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (period_id) DO NOTHING
        """
    ).format(
        sql.Identifier(
            schema,
            "periods",
        )
    )

    parameters = [
        (
            period.period_id,
            period.period_type.name,
            period.first_date,
            period.last_date,
        )
        for period in sorted(
            periods_by_id.values(),
            key=lambda item: item.period_id,
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            parameters,
        )

    persisted_periods = fetch_periods_by_ids(
        connection,
        schema=schema,
        period_ids=tuple(periods_by_id),
    )

    missing_period_ids = periods_by_id.keys() - persisted_periods.keys()

    if missing_period_ids:
        raise PeriodPersistenceError(
            f"Periods were not present after insertion: {sorted(missing_period_ids)!r}"
        )

    for period_id, expected_period in periods_by_id.items():
        persisted_period = persisted_periods[period_id]

        if persisted_period != expected_period:
            raise PeriodConflictError(
                "Persisted period conflicts with requested period for "
                f"period_id {period_id!r}: "
                f"persisted={persisted_period!r}, "
                f"requested={expected_period!r}"
            )


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


def _normalise_periods(
    periods: Sequence[Period],
) -> dict[str, Period]:
    """Return periods keyed by ID while rejecting conflicting input."""

    periods_by_id: dict[str, Period] = {}

    for period in periods:
        existing_period = periods_by_id.get(period.period_id)

        if existing_period is None:
            periods_by_id[period.period_id] = period
            continue

        if existing_period != period:
            raise PeriodConflictError(
                "Input contains conflicting periods for "
                f"period_id {period.period_id!r}: "
                f"first={existing_period!r}, "
                f"second={period!r}"
            )

    return periods_by_id


def _periods_from_rows(
    rows: Sequence[PostgresRow],
) -> dict[str, Period]:
    """Reconstruct periods and reject duplicate database identities."""

    periods: dict[str, Period] = {}

    for row in rows:
        period = _period_from_row(row)

        if period.period_id in periods:
            raise PeriodPersistenceError(
                f"Period query returned duplicate period_id {period.period_id!r}"
            )

        periods[period.period_id] = period

    return periods


def _period_from_row(
    row: PostgresRow,
) -> Period:
    """Reconstruct one validated domain period from a database row."""

    if len(row) != 4:
        raise PeriodPersistenceError(
            f"Period query returned an unexpected row shape: {row!r}"
        )

    period_id = row[0]
    period_type_text = row[1]
    first_date = row[2]
    last_date = row[3]

    if not isinstance(period_id, str):
        raise PeriodPersistenceError(
            f"Persisted period_id must be text, got {period_id!r}"
        )

    if not isinstance(period_type_text, str):
        raise PeriodPersistenceError(
            f"Persisted period_type must be text, got {period_type_text!r}"
        )

    if not isinstance(first_date, date):
        raise PeriodPersistenceError(
            f"Persisted first_date must be a date, got {first_date!r}"
        )

    if not isinstance(last_date, date):
        raise PeriodPersistenceError(
            f"Persisted last_date must be a date, got {last_date!r}"
        )

    try:
        period_type = PeriodType[period_type_text]
    except KeyError as err:
        raise PeriodPersistenceError(
            f"Persisted period_type is not recognised: {period_type_text!r}"
        ) from err

    return Period(
        period_id=period_id,
        period_type=period_type,
        first_date=first_date,
        last_date=last_date,
    )
