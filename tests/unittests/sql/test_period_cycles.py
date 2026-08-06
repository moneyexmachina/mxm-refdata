"""Unit tests for plain-SQL period-cycle persistence operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self, cast

import pytest
from psycopg import Connection, sql

from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.sql.period_cycles import (
    PeriodCycleConflictError,
    PeriodCyclePersistenceError,
    fetch_period_cycle_memberships,
    fetch_period_cycles,
    insert_period_cycle_memberships,
    insert_period_cycles,
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
    ) -> None:
        self._rows = list(rows or [])
        self._executions: list[Execution] = []
        self.fetchall_calls = 0

    def bind_executions(
        self,
        executions: list[Execution],
    ) -> None:
        """Bind this cursor to its connection's execution log."""

        self._executions = executions

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

        self.fetchall_calls += 1
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
            cursor.bind_executions(self.executions)

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
    """Cast a fake connection to the production connection type."""

    return cast(
        Connection[PostgresRow],
        connection,
    )


def _calendar_months_cycle(
    *,
    cycle_id: str = "CALENDAR_MONTHS",
    name: str = "Calendar Months",
    period_type: PeriodType = PeriodType.MONTH,
    cycle_size: int = 12,
    instance_kind: CycleInstanceKind = CycleInstanceKind.YEAR,
) -> PeriodCycle:
    """Construct the calendar-months cycle."""

    return PeriodCycle(
        cycle_id=cycle_id,
        name=name,
        period_type=period_type,
        cycle_size=cycle_size,
        instance_kind=instance_kind,
    )


def _calendar_quarters_cycle(
    *,
    cycle_id: str = "CALENDAR_QUARTERS",
    name: str = "Calendar Quarters",
    period_type: PeriodType = PeriodType.QUARTER,
    cycle_size: int = 4,
    instance_kind: CycleInstanceKind = CycleInstanceKind.YEAR,
) -> PeriodCycle:
    """Construct the calendar-quarters cycle."""

    return PeriodCycle(
        cycle_id=cycle_id,
        name=name,
        period_type=period_type,
        cycle_size=cycle_size,
        instance_kind=instance_kind,
    )


def _membership(
    *,
    cycle_id: str = "CALENDAR_MONTHS",
    period_id: str = "2024-01",
    cycle_instance: int = 2024,
    cycle_element: int = 1,
) -> PeriodCycleMembership:
    """Construct a representative cycle membership."""

    return PeriodCycleMembership(
        cycle_id=cycle_id,
        period_id=period_id,
        cycle_instance=cycle_instance,
        cycle_element=cycle_element,
    )


def _cycle_row(
    cycle: PeriodCycle,
) -> PostgresRow:
    """Encode a period cycle as one PostgreSQL result row."""

    return cast(
        PostgresRow,
        (
            cycle.cycle_id,
            cycle.name,
            cycle.period_type.name,
            cycle.instance_kind.value,
            cycle.cycle_size,
        ),
    )


def _membership_row(
    membership: PeriodCycleMembership,
) -> PostgresRow:
    """Encode a membership as one PostgreSQL result row."""

    return cast(
        PostgresRow,
        (
            membership.cycle_id,
            membership.period_id,
            membership.cycle_instance,
            membership.cycle_element,
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
    """Render and normalise a composed SQL query."""

    return " ".join(query.as_string().split())


def _single_execution(
    connection: FakeConnection,
) -> Execution:
    """Return the sole recorded SQL operation."""

    assert len(connection.executions) == 1
    return connection.executions[0]


# ---------------------------------------------------------------------------
# fetch_period_cycles
# ---------------------------------------------------------------------------


def test_fetch_period_cycles_returns_empty_mapping() -> None:
    """An empty cycle table produces an empty mapping."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    cycles = fetch_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert cycles == {}
    assert connection.cursor_calls == 1


def test_fetch_period_cycles_reconstructs_domain_cycles() -> None:
    """Persisted rows are reconstructed as domain cycles."""

    months = _calendar_months_cycle()
    quarters = _calendar_quarters_cycle()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _cycle_row(months),
                    _cycle_row(quarters),
                ]
            ),
        ]
    )

    cycles = fetch_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert cycles == {
        months.cycle_id: months,
        quarters.cycle_id: quarters,
    }


def test_fetch_period_cycles_uses_configured_schema() -> None:
    """The cycle query uses the caller-provided schema."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert execution.operation == "execute"
    assert '"refdata_test_abc"."period_cycles"' in query_text
    assert '"public"."period_cycles"' not in query_text


def test_fetch_period_cycles_uses_deterministic_ordering() -> None:
    """The cycle query defines stable result ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)

    assert "ORDER BY cycle_id" in _query_text(execution.query)


def test_fetch_period_cycles_rejects_duplicate_identity() -> None:
    """A query returning one cycle ID twice is invalid state."""

    cycle = _calendar_months_cycle()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _cycle_row(cycle),
                    _cycle_row(cycle),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=r"duplicate cycle_id.*CALENDAR_MONTHS",
    ):
        fetch_period_cycles(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


@pytest.mark.parametrize(
    ("row", "error_match"),
    [
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                "YEAR",
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                "YEAR",
                12,
                "extra",
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                123,
                "Calendar Months",
                "MONTH",
                "YEAR",
                12,
            ),
            r"cycle_id must be text",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                123,
                "MONTH",
                "YEAR",
                12,
            ),
            r"cycle name must be text",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                123,
                "YEAR",
                12,
            ),
            r"period_type must be text",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "NOT_A_PERIOD_TYPE",
                "YEAR",
                12,
            ),
            r"period_type is not recognised",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                123,
                12,
            ),
            r"instance_kind must be text",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                "NOT_AN_INSTANCE_KIND",
                12,
            ),
            r"instance_kind is not recognised",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                "YEAR",
                "12",
            ),
            r"cycle_size must be an integer",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                "YEAR",
                True,
            ),
            r"cycle_size must be an integer",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "Calendar Months",
                "MONTH",
                "YEAR",
                0,
            ),
            r"period cycle is invalid",
        ),
    ],
)
def test_fetch_period_cycles_rejects_invalid_rows(
    row: PostgresRow,
    error_match: str,
) -> None:
    """Malformed persisted cycle rows cannot enter the domain."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=error_match,
    ):
        fetch_period_cycles(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# insert_period_cycles
# ---------------------------------------------------------------------------


def test_insert_period_cycles_returns_early_for_empty_input() -> None:
    """An empty cycle insertion performs no database work."""

    connection = FakeConnection()

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[],
    )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_period_cycles_collapses_identical_duplicates() -> None:
    """Repeated identical cycles produce one insert row."""

    cycle = _calendar_months_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(cycle),
                ]
            ),
        ]
    )

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[
            cycle,
            cycle,
        ],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.operation == "executemany"
    assert insert_execution.parameters == [
        (
            cycle.cycle_id,
            cycle.name,
            cycle.period_type.name,
            cycle.instance_kind.value,
            cycle.cycle_size,
        )
    ]


def test_insert_period_cycles_rejects_conflicting_input() -> None:
    """One cycle ID cannot identify two different cycles."""

    first = _calendar_months_cycle()
    conflicting = _calendar_months_cycle(
        name="Different Name",
    )

    connection = FakeConnection()

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"conflicting period cycles.*CALENDAR_MONTHS",
    ):
        insert_period_cycles(
            _as_connection(connection),
            schema="refdata_test_abc",
            period_cycles=[
                first,
                conflicting,
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_period_cycles_orders_rows_by_cycle_id() -> None:
    """Cycle insertion parameter ordering is deterministic."""

    months = _calendar_months_cycle()
    quarters = _calendar_quarters_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(quarters),
                    _cycle_row(months),
                ]
            ),
        ]
    )

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[
            quarters,
            months,
        ],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.parameters == [
        (
            months.cycle_id,
            months.name,
            months.period_type.name,
            months.instance_kind.value,
            months.cycle_size,
        ),
        (
            quarters.cycle_id,
            quarters.name,
            quarters.period_type.name,
            quarters.instance_kind.value,
            quarters.cycle_size,
        ),
    ]


def test_insert_period_cycles_uses_configured_schema() -> None:
    """Cycle insertion targets the configured schema."""

    cycle = _calendar_months_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(cycle),
                ]
            ),
        ]
    )

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[cycle],
    )

    query_text = _query_text(connection.executions[0].query)

    assert '"refdata_test_abc"."period_cycles"' in query_text
    assert '"public"."period_cycles"' not in query_text


def test_insert_period_cycles_uses_identity_conflict_clause() -> None:
    """Cycle insertion handles replay by cycle identity."""

    cycle = _calendar_months_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(cycle),
                ]
            ),
        ]
    )

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[cycle],
    )

    query_text = _query_text(connection.executions[0].query)

    assert "ON CONFLICT (cycle_id) DO NOTHING" in query_text


def test_insert_period_cycles_accepts_matching_persisted_state() -> None:
    """A matching persisted cycle is accepted."""

    cycle = _calendar_months_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(cycle),
                ]
            ),
        ]
    )

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[cycle],
    )

    assert len(connection.executions) == 2
    assert connection.executions[0].operation == "executemany"
    assert connection.executions[1].operation == "execute"


def test_insert_period_cycles_rejects_conflicting_persisted_state() -> None:
    """A persisted cycle with changed values is rejected."""

    requested = _calendar_months_cycle()
    persisted = _calendar_months_cycle(
        cycle_size=11,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(persisted),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"Persisted period cycle conflicts.*CALENDAR_MONTHS",
    ):
        insert_period_cycles(
            _as_connection(connection),
            schema="refdata_test_abc",
            period_cycles=[requested],
        )


def test_insert_period_cycles_rejects_missing_persisted_state() -> None:
    """A requested cycle must exist after insertion."""

    cycle = _calendar_months_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(rows=[]),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=r"Period cycles were not present after insertion",
    ):
        insert_period_cycles(
            _as_connection(connection),
            schema="refdata_test_abc",
            period_cycles=[cycle],
        )


def test_insert_period_cycles_validates_all_unique_ids() -> None:
    """The validation query receives all unique cycle IDs."""

    months = _calendar_months_cycle()
    quarters = _calendar_quarters_cycle()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(months),
                    _cycle_row(quarters),
                ]
            ),
        ]
    )

    insert_period_cycles(
        _as_connection(connection),
        schema="refdata_test_abc",
        period_cycles=[
            quarters,
            months,
            months,
        ],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert "cycle_id = ANY(%s::text[])" in query_text
    assert validation_execution.parameters == (
        [
            "CALENDAR_MONTHS",
            "CALENDAR_QUARTERS",
        ],
    )


# ---------------------------------------------------------------------------
# fetch_period_cycle_memberships
# ---------------------------------------------------------------------------


def test_fetch_memberships_returns_empty_mapping() -> None:
    """An empty membership table produces an empty mapping."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    memberships = fetch_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert memberships == {}


def test_fetch_memberships_reconstructs_domain_values() -> None:
    """Persisted membership rows reconstruct domain objects."""

    january = _membership()
    february = _membership(
        period_id="2024-02",
        cycle_element=2,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _membership_row(january),
                    _membership_row(february),
                ]
            ),
        ]
    )

    memberships = fetch_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert memberships == {
        (
            january.cycle_id,
            january.period_id,
        ): january,
        (
            february.cycle_id,
            february.period_id,
        ): february,
    }


def test_fetch_memberships_uses_configured_schema() -> None:
    """The membership query uses the configured schema."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    query_text = _query_text(_single_execution(connection).query)

    assert '"refdata_test_abc"."period_cycle_memberships"' in query_text
    assert '"public"."period_cycle_memberships"' not in query_text


def test_fetch_memberships_uses_semantic_ordering() -> None:
    """Membership rows use stable cycle-position ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    query_text = _query_text(_single_execution(connection).query)

    assert "ORDER BY cycle_id, cycle_instance, cycle_element, period_id" in query_text


def test_fetch_memberships_rejects_duplicate_identity() -> None:
    """A membership identity may appear only once."""

    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _membership_row(membership),
                    _membership_row(membership),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=r"duplicate identity",
    ):
        fetch_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


def test_fetch_memberships_rejects_duplicate_position() -> None:
    """A cycle position may be occupied by only one period."""

    first = _membership(
        period_id="2024-01",
    )
    second = _membership(
        period_id="different-period",
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _membership_row(first),
                    _membership_row(second),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=r"duplicate position",
    ):
        fetch_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


@pytest.mark.parametrize(
    ("row", "error_match"),
    [
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                2024,
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                2024,
                1,
                "extra",
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                123,
                "2024-01",
                2024,
                1,
            ),
            r"membership cycle_id must be text",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                123,
                2024,
                1,
            ),
            r"membership period_id must be text",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                "2024",
                1,
            ),
            r"cycle_instance must be an integer",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                True,
                1,
            ),
            r"cycle_instance must be an integer",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                2024,
                "1",
            ),
            r"cycle_element must be an integer",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                2024,
                True,
            ),
            r"cycle_element must be an integer",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                0,
                1,
            ),
            r"period-cycle membership is invalid",
        ),
        (
            _row(
                "CALENDAR_MONTHS",
                "2024-01",
                2024,
                0,
            ),
            r"period-cycle membership is invalid",
        ),
    ],
)
def test_fetch_memberships_rejects_invalid_rows(
    row: PostgresRow,
    error_match: str,
) -> None:
    """Malformed membership rows cannot enter the domain."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=error_match,
    ):
        fetch_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# insert_period_cycle_memberships: input validation
# ---------------------------------------------------------------------------


def test_insert_memberships_returns_early_for_empty_input() -> None:
    """An empty membership insertion performs no database work."""

    connection = FakeConnection()

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[],
    )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_memberships_collapses_identical_duplicates() -> None:
    """Repeated identical memberships produce one insert row."""

    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(membership),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[
            membership,
            membership,
        ],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.parameters == [
        (
            membership.cycle_id,
            membership.period_id,
            membership.cycle_instance,
            membership.cycle_element,
        )
    ]


def test_insert_memberships_rejects_conflicting_identity_input() -> None:
    """One membership identity cannot have two cycle positions."""

    first = _membership()
    conflicting = _membership(
        cycle_element=2,
    )

    connection = FakeConnection()

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"conflicting period-cycle memberships for identity",
    ):
        insert_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
            memberships=[
                first,
                conflicting,
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_memberships_rejects_conflicting_position_input() -> None:
    """One cycle position cannot contain two different periods."""

    first = _membership(
        period_id="2024-01",
    )
    conflicting = _membership(
        period_id="2024-02",
    )

    connection = FakeConnection()

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"conflicting period-cycle memberships for position",
    ):
        insert_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
            memberships=[
                first,
                conflicting,
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_memberships_allows_same_element_in_different_cycles() -> None:
    """Position identity includes the cycle ID."""

    month = _membership(
        cycle_id="CALENDAR_MONTHS",
        period_id="2024-01",
        cycle_instance=2024,
        cycle_element=1,
    )
    quarter = _membership(
        cycle_id="CALENDAR_QUARTERS",
        period_id="2024-Q1",
        cycle_instance=2024,
        cycle_element=1,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(month),
                    _membership_row(quarter),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[
            quarter,
            month,
        ],
    )

    assert len(connection.executions) == 2


# ---------------------------------------------------------------------------
# insert_period_cycle_memberships: SQL encoding
# ---------------------------------------------------------------------------


def test_insert_memberships_uses_semantic_parameter_order() -> None:
    """Membership bulk rows use deterministic cycle-position ordering."""

    february = _membership(
        period_id="2024-02",
        cycle_element=2,
    )
    january = _membership(
        period_id="2024-01",
        cycle_element=1,
    )
    quarter = _membership(
        cycle_id="CALENDAR_QUARTERS",
        period_id="2024-Q1",
        cycle_element=1,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(quarter),
                    _membership_row(february),
                    _membership_row(january),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[
            quarter,
            february,
            january,
        ],
    )

    insert_execution = connection.executions[0]

    assert insert_execution.parameters == [
        (
            january.cycle_id,
            january.period_id,
            january.cycle_instance,
            january.cycle_element,
        ),
        (
            february.cycle_id,
            february.period_id,
            february.cycle_instance,
            february.cycle_element,
        ),
        (
            quarter.cycle_id,
            quarter.period_id,
            quarter.cycle_instance,
            quarter.cycle_element,
        ),
    ]


def test_insert_memberships_uses_configured_schema() -> None:
    """Membership insertion targets the configured schema."""

    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(membership),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[membership],
    )

    query_text = _query_text(connection.executions[0].query)

    assert '"refdata_test_abc"."period_cycle_memberships"' in query_text
    assert '"public"."period_cycle_memberships"' not in query_text


def test_insert_memberships_uses_untargeted_conflict_clause() -> None:
    """Either database uniqueness rule can produce an idempotent conflict."""

    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(membership),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[membership],
    )

    query_text = _query_text(connection.executions[0].query)

    assert "ON CONFLICT DO NOTHING" in query_text
    assert "ON CONFLICT (cycle_id, period_id)" not in query_text


def test_insert_memberships_validates_all_affected_cycle_ids() -> None:
    """Post-insert validation queries every affected cycle once."""

    month = _membership(
        cycle_id="CALENDAR_MONTHS",
        period_id="2024-01",
    )
    quarter = _membership(
        cycle_id="CALENDAR_QUARTERS",
        period_id="2024-Q1",
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(month),
                    _membership_row(quarter),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[
            quarter,
            month,
        ],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert "cycle_id = ANY(%s::text[])" in query_text
    assert validation_execution.parameters == (
        [
            "CALENDAR_MONTHS",
            "CALENDAR_QUARTERS",
        ],
    )


# ---------------------------------------------------------------------------
# insert_period_cycle_memberships: persisted-state validation
# ---------------------------------------------------------------------------


def test_insert_memberships_accepts_matching_persisted_state() -> None:
    """An identical persisted membership is accepted."""

    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(membership),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[membership],
    )

    assert len(connection.executions) == 2
    assert connection.executions[0].operation == "executemany"
    assert connection.executions[1].operation == "execute"


def test_insert_memberships_rejects_persisted_identity_conflict() -> None:
    """A persisted identity at another position is rejected."""

    requested = _membership(
        cycle_element=1,
    )
    persisted = _membership(
        cycle_element=2,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(persisted),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"membership conflicts.*identity",
    ):
        insert_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
            memberships=[requested],
        )


def test_insert_memberships_rejects_occupied_persisted_position() -> None:
    """A requested position occupied by another period is rejected."""

    requested = _membership(
        period_id="2024-01",
    )
    occupying = _membership(
        period_id="different-period",
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(occupying),
                ]
            ),
        ]
    )

    with pytest.raises(
        PeriodCycleConflictError,
        match=r"position is occupied by a different membership",
    ):
        insert_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
            memberships=[requested],
        )


def test_insert_memberships_rejects_missing_persisted_state() -> None:
    """A requested membership must exist after insertion."""

    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(rows=[]),
        ]
    )

    with pytest.raises(
        PeriodCyclePersistenceError,
        match=r"membership was not present after insertion",
    ):
        insert_period_cycle_memberships(
            _as_connection(connection),
            schema="refdata_test_abc",
            memberships=[membership],
        )


def test_insert_memberships_tolerates_unrelated_rows_in_affected_cycle() -> None:
    """Unrequested memberships in the same cycle do not cause failure."""

    requested = _membership(
        period_id="2024-01",
        cycle_element=1,
    )
    unrelated = _membership(
        period_id="2024-02",
        cycle_element=2,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(unrelated),
                    _membership_row(requested),
                ]
            ),
        ]
    )

    insert_period_cycle_memberships(
        _as_connection(connection),
        schema="refdata_test_abc",
        memberships=[requested],
    )

    assert len(connection.executions) == 2


# ---------------------------------------------------------------------------
# Transaction ownership
# ---------------------------------------------------------------------------


def test_period_cycle_operations_do_not_control_transactions() -> None:
    """Cycle SQL helpers neither commit nor roll back transactions."""

    cycle = _calendar_months_cycle()
    membership = _membership()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _cycle_row(cycle),
                ]
            ),
            FakeCursor(),
            FakeCursor(
                rows=[
                    _membership_row(membership),
                ]
            ),
        ]
    )

    typed_connection = _as_connection(connection)

    insert_period_cycles(
        typed_connection,
        schema="refdata_test_abc",
        period_cycles=[cycle],
    )

    insert_period_cycle_memberships(
        typed_connection,
        schema="refdata_test_abc",
        memberships=[membership],
    )

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
