"""Unit tests for plain-SQL period persistence operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Self, cast

import pytest
from psycopg import Connection, sql

from mxm.refdata.models import Period, PeriodType
from mxm.refdata.sql.periods import (
    PeriodConflictError,
    PeriodPersistenceError,
    fetch_periods,
    fetch_periods_by_ids,
    fetch_periods_by_types,
    fetch_periods_in_range,
    insert_periods,
)
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed
type ParameterRow = tuple[object, ...]


@dataclass(frozen=True)
class Execution:
    """One SQL operation issued through a fake cursor."""

    operation: Literal["execute", "executemany"]
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

    def executemany(
        self,
        query: ExecutableQuery,
        parameters: list[ParameterRow],
    ) -> None:
        """Record one executemany operation."""

        self._executions.append(
            Execution(
                operation="executemany",
                query=query,
                parameters=list(parameters),
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


def _period(
    period_id: str,
    period_type: PeriodType,
    first_date: date,
    last_date: date,
) -> Period:
    """Construct one period test value."""

    return Period(
        period_id=period_id,
        period_type=period_type,
        first_date=first_date,
        last_date=last_date,
    )


def _month_period(
    *,
    period_id: str = "2024-01",
    first_date: date = date(2024, 1, 1),
    last_date: date = date(2024, 1, 31),
) -> Period:
    """Construct a representative monthly period."""

    return _period(
        period_id,
        PeriodType.MONTH,
        first_date,
        last_date,
    )


def _quarter_period(
    *,
    period_id: str = "2024-Q1",
    first_date: date = date(2024, 1, 1),
    last_date: date = date(2024, 3, 31),
) -> Period:
    """Construct a representative quarterly period."""

    return _period(
        period_id,
        PeriodType.QUARTER,
        first_date,
        last_date,
    )


def _year_period(
    *,
    period_id: str = "2024",
    first_date: date = date(2024, 1, 1),
    last_date: date = date(2024, 12, 31),
) -> Period:
    """Construct a representative yearly period."""

    return _period(
        period_id,
        PeriodType.YEAR,
        first_date,
        last_date,
    )


def _period_row(
    period: Period,
) -> PostgresRow:
    """Encode a period as one PostgreSQL result row."""

    return cast(
        PostgresRow,
        (
            period.period_id,
            period.period_type.name,
            period.first_date,
            period.last_date,
        ),
    )


def _row(
    *values: object,
) -> PostgresRow:
    """Construct an arbitrary PostgreSQL result row."""

    return cast(
        PostgresRow,
        tuple(values),
    )


def _query_text(
    query: ExecutableQuery,
) -> str:
    """Render and normalise one composed SQL query."""

    return " ".join(query.as_string().split())


def _single_execution(
    connection: FakeConnection,
) -> Execution:
    """Return the sole recorded operation."""

    assert len(connection.executions) == 1
    return connection.executions[0]


# ---------------------------------------------------------------------------
# fetch_periods
# ---------------------------------------------------------------------------


def test_fetch_periods_returns_empty_mapping() -> None:
    """An empty periods table produces an empty mapping."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    periods = fetch_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert periods == {}
    assert connection.cursor_calls == 1


def test_fetch_periods_reconstructs_domain_periods() -> None:
    """Persisted rows are reconstructed as domain periods."""

    month = _month_period()
    quarter = _quarter_period()
    year = _year_period()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _period_row(month),
                    _period_row(quarter),
                    _period_row(year),
                ]
            ),
        ]
    )

    periods = fetch_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert periods == {
        month.period_id: month,
        quarter.period_id: quarter,
        year.period_id: year,
    }


def test_fetch_periods_uses_configured_schema() -> None:
    """The periods query uses the caller-provided schema."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert execution.operation == "execute"
    assert '"refdata_test_abc"."periods"' in query_text
    assert '"public"."periods"' not in query_text


def test_fetch_periods_uses_deterministic_ordering() -> None:
    """The all-periods query defines stable result ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert "ORDER BY first_date, last_date, period_id" in query_text


def test_fetch_periods_rejects_duplicate_database_identity() -> None:
    """A query returning one period ID twice is invalid state."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _period_row(period),
                    _period_row(period),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodPersistenceError,
        match=r"duplicate period_id.*2024-01",
    ):
        fetch_periods(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


@pytest.mark.parametrize(
    ("row", "error_match"),
    [
        (
            _row(
                "2024-01",
                "MONTH",
                date(2024, 1, 1),
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                "2024-01",
                "MONTH",
                date(2024, 1, 1),
                date(2024, 1, 31),
                "extra",
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                123,
                "MONTH",
                date(2024, 1, 1),
                date(2024, 1, 31),
            ),
            r"period_id must be text",
        ),
        (
            _row(
                "2024-01",
                123,
                date(2024, 1, 1),
                date(2024, 1, 31),
            ),
            r"period_type must be text",
        ),
        (
            _row(
                "2024-01",
                "MONTH",
                "2024-01-01",
                date(2024, 1, 31),
            ),
            r"first_date must be a date",
        ),
        (
            _row(
                "2024-01",
                "MONTH",
                date(2024, 1, 1),
                "2024-01-31",
            ),
            r"last_date must be a date",
        ),
        (
            _row(
                "2024-01",
                "NOT_A_PERIOD_TYPE",
                date(2024, 1, 1),
                date(2024, 1, 31),
            ),
            r"period_type is not recognised",
        ),
    ],
)
def test_fetch_periods_rejects_invalid_rows(
    row: PostgresRow,
    error_match: str,
) -> None:
    """Malformed persistent rows cannot cross into the domain."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        PeriodPersistenceError,
        match=error_match,
    ):
        fetch_periods(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# fetch_periods_by_ids
# ---------------------------------------------------------------------------


def test_fetch_periods_by_ids_returns_early_for_empty_selection() -> None:
    """An empty period-ID selection performs no database operation."""

    connection = FakeConnection()

    periods = fetch_periods_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_ids=[],
    )

    assert periods == {}
    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_periods_by_ids_collapses_and_orders_ids() -> None:
    """Period-ID query parameters are unique and deterministic."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_ids=[
            "2024-Q1",
            "2024-01",
            "2024",
            "2024-Q1",
        ],
    )

    execution = _single_execution(connection)

    assert execution.operation == "execute"
    assert execution.parameters == (
        [
            "2024",
            "2024-01",
            "2024-Q1",
        ],
    )


def test_fetch_periods_by_ids_uses_expected_filter_and_schema() -> None:
    """Period-ID selection uses the configured table and text-array filter."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_ids=[
            "2024-01",
        ],
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert '"refdata_test_abc"."periods"' in query_text
    assert '"public"."periods"' not in query_text
    assert "period_id = ANY(%s::text[])" in query_text
    assert "ORDER BY period_id" in query_text


def test_fetch_periods_by_ids_reconstructs_matching_rows() -> None:
    """Rows returned by an ID query reconstruct domain periods."""

    month = _month_period()
    quarter = _quarter_period()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _period_row(month),
                    _period_row(quarter),
                ]
            ),
        ]
    )

    periods = fetch_periods_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_ids=[
            quarter.period_id,
            month.period_id,
            "missing-period",
        ],
    )

    assert periods == {
        month.period_id: month,
        quarter.period_id: quarter,
    }


# ---------------------------------------------------------------------------
# fetch_periods_by_types
# ---------------------------------------------------------------------------


def test_fetch_periods_by_types_returns_early_for_empty_selection() -> None:
    """An empty type selection performs no database operation."""

    connection = FakeConnection()

    periods = fetch_periods_by_types(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_types=[],
    )

    assert periods == {}
    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_periods_by_types_encodes_enum_names() -> None:
    """Period types are persisted and queried using enum names."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_by_types(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_types=[
            PeriodType.QUARTER,
            PeriodType.MONTH,
        ],
    )

    execution = _single_execution(connection)

    assert execution.operation == "execute"
    assert execution.parameters == (
        [
            "MONTH",
            "QUARTER",
        ],
    )


def test_fetch_periods_by_types_collapses_duplicates() -> None:
    """Repeated input types appear once in the SQL parameter array."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_by_types(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_types=[
            PeriodType.MONTH,
            PeriodType.MONTH,
            PeriodType.QUARTER,
            PeriodType.MONTH,
        ],
    )

    execution = _single_execution(connection)

    assert execution.parameters == (
        [
            "MONTH",
            "QUARTER",
        ],
    )


def test_fetch_periods_by_types_uses_expected_filter() -> None:
    """The query filters against the supplied PostgreSQL text array."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_by_types(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_types=[
            PeriodType.MONTH,
        ],
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert '"refdata_test_abc"."periods"' in query_text
    assert "period_type = ANY(%s::text[])" in query_text


def test_fetch_periods_by_types_reconstructs_matching_rows() -> None:
    """Rows returned by the type query become domain periods."""

    month = _month_period()
    quarter = _quarter_period()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _period_row(month),
                    _period_row(quarter),
                ]
            ),
        ]
    )

    periods = fetch_periods_by_types(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_types=[
            PeriodType.MONTH,
            PeriodType.QUARTER,
        ],
    )

    assert periods == {
        month.period_id: month,
        quarter.period_id: quarter,
    }


# ---------------------------------------------------------------------------
# fetch_periods_in_range
# ---------------------------------------------------------------------------


def test_fetch_periods_in_range_rejects_reversed_range() -> None:
    """A reversed range fails before contacting the database."""

    connection = FakeConnection()

    with pytest.raises(
        ValueError,
        match=r"start_date must not be after end_date",
    ):
        fetch_periods_in_range(
            _as_connection(connection),
            schema="refdata_test_abc",
            start_date=date(2024, 12, 31),
            end_date=date(2024, 1, 1),
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_periods_in_range_passes_inclusive_boundaries() -> None:
    """The requested boundaries are passed unchanged to PostgreSQL."""

    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 31)

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_in_range(
        _as_connection(connection),
        schema="refdata_test_abc",
        start_date=start_date,
        end_date=end_date,
    )

    execution = _single_execution(connection)

    assert execution.parameters == (
        start_date,
        end_date,
    )


def test_fetch_periods_in_range_uses_containment_semantics() -> None:
    """The SQL selects periods wholly contained inside the range."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_periods_in_range(
        _as_connection(connection),
        schema="refdata_test_abc",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert "first_date >= %s" in query_text
    assert "last_date <= %s" in query_text
    assert '"refdata_test_abc"."periods"' in query_text


def test_fetch_periods_in_range_reconstructs_periods() -> None:
    """Rows inside the requested range become domain periods."""

    month = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _period_row(month),
                ]
            ),
        ]
    )

    periods = fetch_periods_in_range(
        _as_connection(connection),
        schema="refdata_test_abc",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    assert periods == {
        month.period_id: month,
    }


# ---------------------------------------------------------------------------
# insert_periods: input handling and SQL encoding
# ---------------------------------------------------------------------------


def test_insert_periods_returns_early_for_empty_input() -> None:
    """An empty insertion request performs no database work."""

    connection = FakeConnection()

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[],
    )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_periods_collapses_identical_duplicate_input() -> None:
    """Repeated equal periods produce one insert parameter row."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[
            period,
            period,
        ],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.operation == "executemany"
    assert insert_execution.parameters == [
        (
            period.period_id,
            period.period_type.name,
            period.first_date,
            period.last_date,
        )
    ]


def test_insert_periods_rejects_conflicting_duplicate_input() -> None:
    """One ID cannot identify two different requested periods."""

    first = _month_period()
    conflicting = _month_period(
        last_date=date(2024, 2, 1),
    )

    connection = FakeConnection()

    with pytest.raises(
        PeriodConflictError,
        match=r"Input contains conflicting periods.*2024-01",
    ):
        insert_periods(
            _as_connection(connection),
            schema="refdata_test_abc",
            periods=[
                first,
                conflicting,
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_periods_orders_rows_by_period_id() -> None:
    """Bulk insertion parameter ordering is deterministic."""

    year = _year_period()
    quarter = _quarter_period()
    month = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(year),
                    _period_row(quarter),
                    _period_row(month),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[
            quarter,
            month,
            year,
        ],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.operation == "executemany"
    assert insert_execution.parameters == [
        (
            year.period_id,
            year.period_type.name,
            year.first_date,
            year.last_date,
        ),
        (
            month.period_id,
            month.period_type.name,
            month.first_date,
            month.last_date,
        ),
        (
            quarter.period_id,
            quarter.period_type.name,
            quarter.first_date,
            quarter.last_date,
        ),
    ]


def test_insert_periods_uses_configured_schema() -> None:
    """The bulk insert targets the configured periods table."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    insert_execution = connection.executions[0]
    query_text = _query_text(insert_execution.query)

    assert '"refdata_test_abc"."periods"' in query_text
    assert '"public"."periods"' not in query_text


def test_insert_periods_uses_idempotent_conflict_clause() -> None:
    """Insertion tolerates an already-present period identity."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    insert_execution = connection.executions[0]
    query_text = _query_text(insert_execution.query)

    assert "ON CONFLICT (period_id) DO NOTHING" in query_text


def test_insert_periods_encodes_domain_values() -> None:
    """A domain period is encoded into the expected SQL values."""

    period = _quarter_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.parameters == [
        (
            "2024-Q1",
            "QUARTER",
            date(2024, 1, 1),
            date(2024, 3, 31),
        )
    ]


# ---------------------------------------------------------------------------
# insert_periods: persisted-state verification
# ---------------------------------------------------------------------------


def test_insert_periods_accepts_matching_persisted_state() -> None:
    """A matching row after insertion is accepted."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    assert len(connection.executions) == 2
    assert connection.executions[0].operation == "executemany"
    assert connection.executions[1].operation == "execute"


def test_insert_periods_accepts_existing_identical_period() -> None:
    """Idempotent replay accepts an identical existing row."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    assert connection.cursor_calls == 2


def test_insert_periods_rejects_conflicting_persisted_state() -> None:
    """An existing row with different values is rejected."""

    requested = _month_period()
    persisted = _month_period(
        last_date=date(2024, 2, 1),
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(persisted),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodConflictError,
        match=r"Persisted period conflicts.*2024-01",
    ):
        insert_periods(
            _as_connection(connection),
            schema="refdata_test_abc",
            periods=[requested],
        )


def test_insert_periods_rejects_missing_persisted_state() -> None:
    """A requested period must exist after the insert operation."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(rows=[]),
        ]
    )

    with pytest.raises(
        PeriodPersistenceError,
        match=r"Periods were not present after insertion.*2024-01",
    ):
        insert_periods(
            _as_connection(connection),
            schema="refdata_test_abc",
            periods=[period],
        )


def test_insert_periods_validates_all_requested_ids() -> None:
    """The validation query includes every unique requested period ID."""

    year = _year_period()
    month = _month_period()
    quarter = _quarter_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(year),
                    _period_row(month),
                    _period_row(quarter),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[
            year,
            month,
            quarter,
            month,
        ],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert validation_execution.operation == "execute"
    assert "period_id = ANY(%s::text[])" in query_text
    assert validation_execution.parameters == (
        [
            "2024",
            "2024-01",
            "2024-Q1",
        ],
    )


def test_insert_periods_validation_uses_configured_schema() -> None:
    """Post-insert validation reads from the configured schema."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert '"refdata_test_abc"."periods"' in query_text
    assert '"public"."periods"' not in query_text


# ---------------------------------------------------------------------------
# Transaction ownership
# ---------------------------------------------------------------------------


def test_period_operations_do_not_control_transactions() -> None:
    """Period SQL helpers neither commit nor roll back transactions."""

    period = _month_period()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _period_row(period),
                ]
            ),
        ]
    )

    insert_periods(
        _as_connection(connection),
        schema="refdata_test_abc",
        periods=[period],
    )

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
