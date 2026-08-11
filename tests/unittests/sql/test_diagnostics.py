"""Unit tests for plain-SQL reference-data diagnostic observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self, cast

import pytest
from psycopg import Connection, sql

from mxm.refdata.sql.diagnostics import (
    RefDataDiagnosticsPersistenceError,
    RefDataRowCounts,
    fetch_refdata_row_counts,
)
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed


@dataclass(frozen=True)
class Execution:
    """One SQL operation issued through a fake cursor."""

    operation: Literal["execute"]
    query: ExecutableQuery
    parameters: object | None


class FakeCursor:
    """Scripted cursor recording SQL operations and returning fixed rows."""

    def __init__(
        self,
        *,
        rows: list[PostgresRow] | None = None,
        executions: list[Execution] | None = None,
    ) -> None:
        """Initialise scripted rows and the shared execution log."""

        self._rows = list(rows or [])
        self._executions = executions if executions is not None else []
        self.fetch_all_calls = 0

    def __enter__(self) -> Self:
        """Enter the fake cursor context."""

        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Exit the fake cursor context."""

        del exc_type, exc_value, traceback

    def execute(
        self,
        query: ExecutableQuery,
        parameters: object | None = None,
    ) -> None:
        """Record one execute operation."""

        self._executions.append(
            Execution(
                operation="execute",
                query=query,
                parameters=parameters,
            )
        )

    def fetchall(self) -> list[PostgresRow]:
        """Return the scripted result rows."""

        self.fetch_all_calls += 1
        return list(self._rows)


class FakeConnection:
    """Connection returning scripted cursors in invocation order."""

    def __init__(
        self,
        cursors: list[FakeCursor] | None = None,
    ) -> None:
        """Initialise scripted cursors and transaction counters."""

        self._cursors = list(cursors or [])
        self.executions: list[Execution] = []
        self.cursor_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

        for cursor in self._cursors:
            cursor._executions = self.executions

    def cursor(self) -> FakeCursor:
        """Return the next scripted cursor."""

        self.cursor_calls += 1

        if not self._cursors:
            raise AssertionError(
                "Unexpected cursor request: no scripted cursor remains"
            )

        return self._cursors.pop(0)

    def commit(self) -> None:
        """Record an unexpected commit request."""

        self.commit_calls += 1

    def rollback(self) -> None:
        """Record an unexpected rollback request."""

        self.rollback_calls += 1


def _as_connection(
    connection: FakeConnection,
) -> Connection[PostgresRow]:
    """Cast a fake connection to the production connection protocol."""

    return cast(
        Connection[PostgresRow],
        connection,
    )


def _row(
    *values: object,
) -> PostgresRow:
    """Construct an arbitrary PostgreSQL result row."""

    return cast(
        PostgresRow,
        tuple(values),
    )


def _valid_count_row() -> PostgresRow:
    """Construct representative materialised reference-data counts."""

    return _row(
        86,
        86,
        799,
        31_447,
        2,
        752,
    )


def _row_with_value(
    row: PostgresRow,
    index: int,
    value: object,
) -> PostgresRow:
    """Return a row with one selected value replaced."""

    values = list(row)

    if index < 0 or index >= len(values):
        raise AssertionError(
            "Test row replacement index is out of range: "
            f"index={index}, row_length={len(values)}"
        )

    values[index] = value

    return _row(*values)


def _query_text(
    query: ExecutableQuery,
) -> str:
    """Render and normalise one composed SQL query."""

    return " ".join(query.as_string().split())


def _single_execution(
    connection: FakeConnection,
) -> Execution:
    """Return the sole recorded SQL operation."""

    assert len(connection.executions) == 1

    return connection.executions[0]


# ---------------------------------------------------------------------------
# SQL observation
# ---------------------------------------------------------------------------


def test_fetch_refdata_row_counts_queries_all_materialised_tables() -> None:
    """One aggregate observation counts every materialised refdata table."""

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _valid_count_row(),
                ]
            ),
        ]
    )

    fetch_refdata_row_counts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert execution.operation == "execute"
    assert execution.parameters is None

    assert query_text.count("COUNT(*)") == 6

    assert '"refdata_test_abc"."futures_products"' in query_text
    assert '"refdata_test_abc"."futures_product_sources"' in query_text
    assert '"refdata_test_abc"."periods"' in query_text
    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert '"refdata_test_abc"."period_cycles"' in query_text
    assert '"refdata_test_abc"."period_cycle_memberships"' in query_text

    assert "AS products" in query_text
    assert "AS product_sources" in query_text
    assert "AS periods" in query_text
    assert "AS contracts" in query_text
    assert "AS cycles" in query_text
    assert "AS memberships" in query_text

    assert connection.cursor_calls == 1


# ---------------------------------------------------------------------------
# Result decoding
# ---------------------------------------------------------------------------


def test_fetch_refdata_row_counts_reconstructs_counts() -> None:
    """The aggregate result row maps to the diagnostic count value."""

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _valid_count_row(),
                ]
            ),
        ]
    )

    counts = fetch_refdata_row_counts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert counts == RefDataRowCounts(
        products=86,
        product_sources=86,
        periods=799,
        contracts=31_447,
        cycles=2,
        memberships=752,
    )


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [
            _valid_count_row(),
            _valid_count_row(),
        ],
    ],
)
def test_fetch_refdata_row_counts_rejects_unexpected_result_count(
    rows: list[PostgresRow],
) -> None:
    """The aggregate observation must return exactly one PostgreSQL row."""

    connection = FakeConnection(
        [
            FakeCursor(
                rows=rows,
            ),
        ]
    )

    with pytest.raises(
        RefDataDiagnosticsPersistenceError,
        match=r"unexpected number of rows",
    ):
        fetch_refdata_row_counts(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


def test_fetch_refdata_row_counts_rejects_unexpected_row_shape() -> None:
    """The aggregate observation must contain exactly six count values."""

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _row(
                        86,
                        86,
                        799,
                        31_447,
                        2,
                    ),
                ]
            ),
        ]
    )

    with pytest.raises(
        RefDataDiagnosticsPersistenceError,
        match=r"unexpected row shape",
    ):
        fetch_refdata_row_counts(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


@pytest.mark.parametrize(
    ("index", "value"),
    [
        (0, "86"),
        (1, 86.0),
        (2, None),
        (3, True),
        (4, False),
        (5, "752"),
    ],
)
def test_fetch_refdata_row_counts_rejects_non_integer_counts(
    index: int,
    value: object,
) -> None:
    """Every diagnostic count must be a genuine PostgreSQL integer value."""

    row = _row_with_value(
        _valid_count_row(),
        index,
        value,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    row,
                ]
            ),
        ]
    )

    with pytest.raises(
        RefDataDiagnosticsPersistenceError,
        match=r"must be an integer",
    ):
        fetch_refdata_row_counts(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


@pytest.mark.parametrize(
    "index",
    [
        0,
        1,
        2,
        3,
        4,
        5,
    ],
)
def test_fetch_refdata_row_counts_rejects_negative_counts(
    index: int,
) -> None:
    """Persisted table counts cannot be negative."""

    row = _row_with_value(
        _valid_count_row(),
        index,
        -1,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    row,
                ]
            ),
        ]
    )

    with pytest.raises(
        RefDataDiagnosticsPersistenceError,
        match=r"cannot be negative",
    ):
        fetch_refdata_row_counts(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# Transaction ownership
# ---------------------------------------------------------------------------


def test_diagnostic_sql_does_not_control_transactions() -> None:
    """Diagnostic SQL helpers neither commit nor roll back transactions."""

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _valid_count_row(),
                ]
            ),
        ]
    )

    fetch_refdata_row_counts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
