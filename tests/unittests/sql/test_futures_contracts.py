"""Unit tests for plain-SQL futures-contract persistence operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal, Self, cast

import pytest
from psycopg import Connection, sql

from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.sql.futures_contracts import (
    FuturesContractConflictError,
    FuturesContractPersistenceError,
    fetch_active_futures_contracts,
    fetch_futures_contracts,
    fetch_futures_contracts_by_ids,
    fetch_futures_contracts_for_product,
    insert_futures_contracts,
)
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed
type ParameterRow = tuple[object, ...]


# ---------------------------------------------------------------------------
# Fake PostgreSQL boundary
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _contract(
    *,
    product_id: str = "PRODUCT_A",
    period_id: str = "2026-09",
    contract_id: str | None = None,
    contract_size: float = 100.0,
    currency: Currency = Currency.USD,
    unit: ProductUnit = ProductUnit.TROY_OUNCE,
    trading_calendar: str = "CME",
    first_day_of_interest: date = date(
        2026,
        6,
        1,
    ),
    last_trading_day: date = date(
        2026,
        9,
        18,
    ),
) -> FuturesContract:
    """Construct a representative futures contract."""

    resolved_contract_id = (
        contract_id if contract_id is not None else f"{product_id}.{period_id}"
    )

    return FuturesContract(
        contract_id=resolved_contract_id,
        product_id=product_id,
        period_id=period_id,
        contract_size=contract_size,
        unit=unit,
        currency=currency,
        trading_calendar=trading_calendar,
        first_day_of_interest=first_day_of_interest,
        last_trading_day=last_trading_day,
    )


def _contract_row(
    contract: FuturesContract,
) -> PostgresRow:
    """Encode a futures contract as one PostgreSQL result row."""

    return (
        contract.contract_id,
        contract.product_id,
        contract.period_id,
        contract.contract_size,
        contract.currency.name,
        contract.unit.name,
        contract.trading_calendar,
        contract.first_day_of_interest,
        contract.last_trading_day,
    )


# ---------------------------------------------------------------------------
# PostgreSQL row and execution helpers
# ---------------------------------------------------------------------------


def _row(
    *values: object,
) -> PostgresRow:
    """Construct an arbitrary PostgreSQL result row."""

    return tuple(values)


def _row_with_values(
    row: PostgresRow,
    replacements: dict[int, object],
) -> PostgresRow:
    """Return a PostgreSQL row with selected values replaced."""

    values: list[object] = list(row)

    for index, value in replacements.items():
        if index < 0 or index >= len(values):
            raise AssertionError(
                "Test row replacement index is out of range: "
                f"index={index}, row_length={len(values)}"
            )

        values[index] = value

    return _row(*values)


def _row_with_value(
    row: PostgresRow,
    index: int,
    value: object,
) -> PostgresRow:
    """Return a PostgreSQL row with one value replaced."""

    return _row_with_values(
        row,
        {
            index: value,
        },
    )


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


def _executemany_parameters(
    execution: Execution,
) -> list[ParameterRow]:
    """Return typed parameter rows from an executemany execution."""

    assert execution.operation == "executemany"

    parameters: object | None = execution.parameters

    assert isinstance(
        parameters,
        list,
    )

    raw_parameters = cast(
        list[object],
        parameters,
    )

    return cast(
        list[ParameterRow],
        raw_parameters,
    )


# ---------------------------------------------------------------------------
# fetch_futures_contracts
# ---------------------------------------------------------------------------


def test_fetch_futures_contracts_returns_empty_mapping() -> None:
    """An empty futures-contracts table produces an empty mapping."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    contracts = fetch_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert contracts == {}
    assert connection.cursor_calls == 1


def test_fetch_futures_contracts_reconstructs_domain_contracts() -> None:
    """Persisted rows reconstruct complete futures contracts."""

    first = _contract(
        product_id="PRODUCT_A",
        period_id="2026-09",
    )
    second = _contract(
        product_id="PRODUCT_B",
        period_id="2026-12",
        contract_size=50.0,
        first_day_of_interest=date(
            2026,
            7,
            1,
        ),
        last_trading_day=date(
            2026,
            12,
            18,
        ),
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _contract_row(first),
                    _contract_row(second),
                ]
            ),
        ]
    )

    contracts = fetch_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert contracts == {
        first.contract_id: first,
        second.contract_id: second,
    }


def test_fetch_futures_contracts_uses_configured_schema() -> None:
    """The contracts query uses the caller-provided schema."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert execution.operation == "execute"
    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert '"public"."futures_contracts"' not in query_text


def test_fetch_futures_contracts_uses_semantic_ordering() -> None:
    """The all-contracts query defines stable semantic ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    query_text = _query_text(_single_execution(connection).query)

    assert "ORDER BY product_id, last_trading_day, contract_id" in query_text


def test_fetch_futures_contracts_rejects_duplicate_database_identity() -> None:
    """A query returning one contract ID twice is invalid state."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _contract_row(contract),
                    _contract_row(contract),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesContractPersistenceError,
        match=r"duplicate contract_id.*PRODUCT_A\.2026-09",
    ):
        fetch_futures_contracts(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


_CONTRACT_ROW = _contract_row(_contract())


@pytest.mark.parametrize(
    (
        "row",
        "error_match",
    ),
    [
        (
            _row(
                *_CONTRACT_ROW[:-1],
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                *_CONTRACT_ROW,
                "extra",
            ),
            r"unexpected row shape",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                0,
                123,
            ),
            r"contract_id must be non-empty text",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                1,
                123,
            ),
            r"product_id must be non-empty text",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                2,
                123,
            ),
            r"period_id must be non-empty text",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                3,
                "100",
            ),
            r"contract_size must be numeric",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                4,
                "NOT_A_CURRENCY",
            ),
            r"currency is not recognised",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                5,
                "NOT_A_UNIT",
            ),
            r"unit is not recognised",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                6,
                123,
            ),
            r"trading_calendar must be non-empty text",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                7,
                "2026-06-01",
            ),
            r"first_day_of_interest must be a date",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                8,
                "2026-09-18",
            ),
            r"last_trading_day must be a date",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                3,
                0.0,
            ),
            r"contract_size must be positive",
        ),
        (
            _row_with_value(
                _CONTRACT_ROW,
                0,
                "DIFFERENT_ID",
            ),
            r"identity is inconsistent",
        ),
        (
            _row_with_values(
                _CONTRACT_ROW,
                {
                    7: date(
                        2026,
                        10,
                        1,
                    ),
                    8: date(
                        2026,
                        9,
                        18,
                    ),
                },
            ),
            r"lifecycle is invalid",
        ),
    ],
)
def test_fetch_futures_contracts_rejects_invalid_rows(
    row: PostgresRow,
    error_match: str,
) -> None:
    """Malformed persisted contract rows cannot enter the domain."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        FuturesContractPersistenceError,
        match=error_match,
    ):
        fetch_futures_contracts(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# fetch_futures_contracts_by_ids
# ---------------------------------------------------------------------------


def test_fetch_futures_contracts_by_ids_returns_early_for_empty_selection() -> None:
    """An empty contract-ID selection performs no database operation."""

    connection = FakeConnection()

    contracts = fetch_futures_contracts_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        contract_ids=[],
    )

    assert contracts == {}
    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_futures_contracts_by_ids_collapses_and_orders_ids() -> None:
    """Contract-ID query parameters are unique and deterministic."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        contract_ids=[
            "PRODUCT_B.2026-12",
            "PRODUCT_A.2026-09",
            "PRODUCT_B.2026-12",
        ],
    )

    execution = _single_execution(connection)

    assert execution.parameters == (
        [
            "PRODUCT_A.2026-09",
            "PRODUCT_B.2026-12",
        ],
    )


def test_fetch_futures_contracts_by_ids_uses_expected_filter() -> None:
    """Contract-ID selection uses a PostgreSQL text-array predicate."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        contract_ids=[
            "PRODUCT_A.2026-09",
        ],
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert "contract_id = ANY(%s::text[])" in query_text
    assert "ORDER BY contract_id" in query_text


def test_fetch_futures_contracts_by_ids_reconstructs_matching_rows() -> None:
    """Rows returned by an ID query reconstruct domain contracts."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    contracts = fetch_futures_contracts_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        contract_ids=[
            contract.contract_id,
        ],
    )

    assert contracts == {
        contract.contract_id: contract,
    }


def test_fetch_futures_contracts_by_ids_rejects_invalid_identifier() -> None:
    """Invalid requested contract identities fail before database access."""

    connection = FakeConnection()

    with pytest.raises(
        FuturesContractPersistenceError,
        match=r"contract_id must be non-empty text",
    ):
        fetch_futures_contracts_by_ids(
            _as_connection(connection),
            schema="refdata_test_abc",
            contract_ids=[
                "",
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


# ---------------------------------------------------------------------------
# fetch_futures_contracts_for_product
# ---------------------------------------------------------------------------


def test_fetch_futures_contracts_for_product_passes_product_id() -> None:
    """Product selection passes the requested product ID unchanged."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
    )

    execution = _single_execution(connection)

    assert execution.parameters == ("PRODUCT_A",)


def test_fetch_futures_contracts_for_product_uses_expected_filter_and_ordering() -> (
    None
):
    """Product selection uses product identity and semantic contract ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert "WHERE product_id = %s" in query_text
    assert "ORDER BY contract_id" in query_text


def test_fetch_futures_contracts_for_product_reconstructs_rows() -> None:
    """Product-filtered rows reconstruct domain contracts."""

    september = _contract(
        period_id="2026-09",
    )
    december = _contract(
        period_id="2026-12",
        first_day_of_interest=date(
            2026,
            7,
            1,
        ),
        last_trading_day=date(
            2026,
            12,
            18,
        ),
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _contract_row(september),
                    _contract_row(december),
                ]
            ),
        ]
    )

    contracts = fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
    )

    assert contracts == {
        september.contract_id: september,
        december.contract_id: december,
    }


def test_fetch_futures_contracts_for_product_rejects_invalid_product_id() -> None:
    """Invalid product identity fails before database access."""

    connection = FakeConnection()

    with pytest.raises(
        FuturesContractPersistenceError,
        match=r"product_id must be non-empty text",
    ):
        fetch_futures_contracts_for_product(
            _as_connection(connection),
            schema="refdata_test_abc",
            product_id="",
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_futures_contracts_for_product_with_period_type_passes_parameters() -> (
    None
):
    """Period-type filtering passes product ID and encoded period type."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
        period_type=PeriodType.MONTH,
    )

    execution = _single_execution(connection)

    assert execution.operation == "execute"
    assert execution.parameters == (
        "PRODUCT_A",
        "MONTH",
    )


def test_fetch_futures_contracts_for_product_with_period_type_joins_periods() -> None:
    """Period-type filtering is performed relationally in PostgreSQL."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
        period_type=PeriodType.MONTH,
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert '"refdata_test_abc"."periods"' in query_text
    assert "JOIN" in query_text
    assert "periods.period_id = contracts.period_id" in query_text
    assert "contracts.product_id = %s" in query_text
    assert "periods.period_type = %s" in query_text


def test_fetch_futures_contracts_for_product_with_period_type_uses_deterministic_ordering() -> (
    None
):
    """Filtered SQL results use deterministic persistence ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
        period_type=PeriodType.MONTH,
    )

    execution = _single_execution(connection)

    assert "ORDER BY contracts.contract_id" in _query_text(execution.query)


def test_fetch_futures_contracts_for_product_with_period_type_reconstructs_contracts() -> (
    None
):
    """Rows from the period-filtered query reconstruct futures contracts."""

    first = _contract(
        product_id="PRODUCT_A",
        period_id="2026-09",
    )
    second = _contract(
        product_id="PRODUCT_A",
        period_id="2026-12",
        first_day_of_interest=date(2026, 9, 1),
        last_trading_day=date(2026, 12, 18),
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _contract_row(first),
                    _contract_row(second),
                ]
            ),
        ]
    )

    contracts = fetch_futures_contracts_for_product(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_id="PRODUCT_A",
        period_type=PeriodType.MONTH,
    )

    assert contracts == {
        first.contract_id: first,
        second.contract_id: second,
    }


# ---------------------------------------------------------------------------
# fetch_active_futures_contracts
# ---------------------------------------------------------------------------


def test_fetch_active_futures_contracts_uses_inclusive_lifecycle_boundaries() -> None:
    """Active selection includes both lifecycle boundary dates."""

    as_of_date = date(
        2026,
        9,
        18,
    )

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=as_of_date,
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert "first_day_of_interest <= %s" in query_text
    assert "last_trading_day >= %s" in query_text
    assert execution.parameters == (
        as_of_date,
        as_of_date,
    )


def test_fetch_active_futures_contracts_without_product_filter() -> None:
    """Omitting product IDs searches across all products."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=date(
            2026,
            8,
            9,
        ),
    )

    query_text = _query_text(_single_execution(connection).query)

    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert "product_id = ANY(%s::text[])" not in query_text


def test_fetch_active_futures_contracts_returns_early_for_empty_product_selection() -> (
    None
):
    """An explicit empty product selection performs no database operation."""

    connection = FakeConnection()

    contracts = fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=date(
            2026,
            8,
            9,
        ),
        product_ids=[],
    )

    assert contracts == {}
    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_active_futures_contracts_collapses_and_orders_product_ids() -> None:
    """Active-contract product filters are unique and deterministic."""

    as_of_date = date(
        2026,
        8,
        9,
    )

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=as_of_date,
        product_ids=[
            "PRODUCT_B",
            "PRODUCT_A",
            "PRODUCT_B",
        ],
    )

    execution = _single_execution(connection)

    assert execution.parameters == (
        as_of_date,
        as_of_date,
        [
            "PRODUCT_A",
            "PRODUCT_B",
        ],
    )


def test_fetch_active_futures_contracts_uses_product_filter() -> None:
    """An explicit product selection adds the expected SQL predicate."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=date(
            2026,
            8,
            9,
        ),
        product_ids=[
            "PRODUCT_A",
        ],
    )

    query_text = _query_text(_single_execution(connection).query)

    assert "product_id = ANY(%s::text[])" in query_text


def test_fetch_active_futures_contracts_uses_semantic_ordering() -> None:
    """Active contracts use stable product and lifecycle ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=date(
            2026,
            8,
            9,
        ),
    )

    query_text = _query_text(_single_execution(connection).query)

    assert "ORDER BY product_id, contract_id" in query_text


def test_fetch_active_futures_contracts_reconstructs_rows() -> None:
    """Rows returned by the active query reconstruct domain contracts."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    contracts = fetch_active_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        as_of_date=date(
            2026,
            8,
            9,
        ),
    )

    assert contracts == {
        contract.contract_id: contract,
    }


# ---------------------------------------------------------------------------
# insert_futures_contracts: input handling and SQL encoding
# ---------------------------------------------------------------------------


def test_insert_futures_contracts_returns_early_for_empty_input() -> None:
    """An empty contract insertion performs no database work."""

    connection = FakeConnection()

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[],
    )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_futures_contracts_collapses_identical_duplicates() -> None:
    """Repeated identical contracts produce one insert parameter row."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[
            contract,
            contract,
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert len(parameters) == 1
    assert parameters[0][0] == contract.contract_id


def test_insert_futures_contracts_rejects_conflicting_duplicate_input() -> None:
    """One contract ID cannot identify two requested contract values."""

    contract = _contract()
    conflicting = replace(
        contract,
        last_trading_day=date(
            2026,
            9,
            17,
        ),
    )

    connection = FakeConnection()

    with pytest.raises(
        FuturesContractConflictError,
        match=r"conflicting futures contracts.*PRODUCT_A\.2026-09",
    ):
        insert_futures_contracts(
            _as_connection(connection),
            schema="refdata_test_abc",
            contracts=[
                contract,
                conflicting,
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


@pytest.mark.parametrize(
    (
        "contract",
        "error_match",
    ),
    [
        (
            replace(
                _contract(),
                contract_id="DIFFERENT_ID",
            ),
            r"identity is inconsistent",
        ),
        (
            replace(
                _contract(),
                contract_size=0.0,
            ),
            r"contract_size must be positive",
        ),
        (
            replace(
                _contract(),
                trading_calendar="",
            ),
            r"trading_calendar must be non-empty text",
        ),
        (
            replace(
                _contract(),
                first_day_of_interest=date(
                    2026,
                    10,
                    1,
                ),
            ),
            r"lifecycle is invalid",
        ),
    ],
)
def test_insert_futures_contracts_rejects_invalid_domain_state_before_sql(
    contract: FuturesContract,
    error_match: str,
) -> None:
    """Invalid persistence invariants fail before database access."""

    connection = FakeConnection()

    with pytest.raises(
        FuturesContractPersistenceError,
        match=error_match,
    ):
        insert_futures_contracts(
            _as_connection(connection),
            schema="refdata_test_abc",
            contracts=[contract],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_futures_contracts_orders_rows_by_contract_id() -> None:
    """Bulk insertion parameter ordering is deterministic."""

    contract_b = _contract(
        product_id="PRODUCT_B",
        period_id="2026-12",
        first_day_of_interest=date(
            2026,
            7,
            1,
        ),
        last_trading_day=date(
            2026,
            12,
            18,
        ),
    )
    contract_a_december = _contract(
        product_id="PRODUCT_A",
        period_id="2026-12",
        first_day_of_interest=date(
            2026,
            7,
            1,
        ),
        last_trading_day=date(
            2026,
            12,
            18,
        ),
    )
    contract_a_september = _contract(
        product_id="PRODUCT_A",
        period_id="2026-09",
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract_a_december),
                    _contract_row(contract_a_september),
                    _contract_row(contract_b),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[
            contract_b,
            contract_a_september,
            contract_a_december,
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert [row[0] for row in parameters] == [
        "PRODUCT_A.2026-09",
        "PRODUCT_A.2026-12",
        "PRODUCT_B.2026-12",
    ]


def test_insert_futures_contracts_uses_configured_schema() -> None:
    """Contract insertion targets the configured schema."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[contract],
    )

    query_text = _query_text(connection.executions[0].query)

    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert '"public"."futures_contracts"' not in query_text


def test_insert_futures_contracts_uses_identity_conflict_clause() -> None:
    """Contract replay is handled by stable contract identity."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[contract],
    )

    query_text = _query_text(connection.executions[0].query)

    assert "ON CONFLICT (contract_id) DO NOTHING" in query_text


def test_insert_futures_contracts_encodes_complete_domain_values() -> None:
    """A domain contract is encoded into the expected SQL values."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[contract],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert parameters == [
        (
            contract.contract_id,
            contract.product_id,
            contract.period_id,
            contract.contract_size,
            contract.currency.name,
            contract.unit.name,
            contract.trading_calendar,
            contract.first_day_of_interest,
            contract.last_trading_day,
        )
    ]


# ---------------------------------------------------------------------------
# insert_futures_contracts: persisted-state verification
# ---------------------------------------------------------------------------


def test_insert_futures_contracts_accepts_matching_persisted_state() -> None:
    """Matching persisted state after insertion is accepted."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[contract],
    )

    assert len(connection.executions) == 2

    assert connection.executions[0].operation == "executemany"
    assert connection.executions[1].operation == "execute"


def test_insert_futures_contracts_rejects_conflicting_persisted_state() -> None:
    """An existing contract with different values is rejected."""

    requested = _contract()
    persisted = replace(
        requested,
        contract_size=50.0,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(persisted),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesContractConflictError,
        match=(r"Persisted futures contract conflicts.*" r"PRODUCT_A\.2026-09"),
    ):
        insert_futures_contracts(
            _as_connection(connection),
            schema="refdata_test_abc",
            contracts=[requested],
        )


def test_insert_futures_contracts_rejects_missing_persisted_state() -> None:
    """A requested contract must exist after insertion."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(rows=[]),
        ]
    )

    with pytest.raises(
        FuturesContractPersistenceError,
        match=(
            r"Futures contracts were not present after insertion.*"
            r"PRODUCT_A\.2026-09"
        ),
    ):
        insert_futures_contracts(
            _as_connection(connection),
            schema="refdata_test_abc",
            contracts=[contract],
        )


def test_insert_futures_contracts_validates_all_unique_ids() -> None:
    """Post-insert validation queries every unique requested contract ID."""

    contract_c = _contract(
        product_id="PRODUCT_C",
        period_id="2027-03",
        first_day_of_interest=date(
            2026,
            10,
            1,
        ),
        last_trading_day=date(
            2027,
            3,
            19,
        ),
    )
    contract_a = _contract(
        product_id="PRODUCT_A",
        period_id="2026-09",
    )
    contract_b = _contract(
        product_id="PRODUCT_B",
        period_id="2026-12",
        first_day_of_interest=date(
            2026,
            7,
            1,
        ),
        last_trading_day=date(
            2026,
            12,
            18,
        ),
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract_a),
                    _contract_row(contract_b),
                    _contract_row(contract_c),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[
            contract_c,
            contract_a,
            contract_b,
            contract_a,
        ],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert "contract_id = ANY(%s::text[])" in query_text
    assert validation_execution.parameters == (
        [
            "PRODUCT_A.2026-09",
            "PRODUCT_B.2026-12",
            "PRODUCT_C.2027-03",
        ],
    )


def test_insert_futures_contracts_validation_uses_configured_schema() -> None:
    """Post-insert verification reads from the configured schema."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[contract],
    )

    query_text = _query_text(connection.executions[1].query)

    assert '"refdata_test_abc"."futures_contracts"' in query_text
    assert '"public"."futures_contracts"' not in query_text


# ---------------------------------------------------------------------------
# Transaction ownership
# ---------------------------------------------------------------------------


def test_futures_contract_operations_do_not_control_transactions() -> None:
    """Contract SQL helpers neither commit nor roll back transactions."""

    contract = _contract()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _contract_row(contract),
                ]
            ),
        ]
    )

    insert_futures_contracts(
        _as_connection(connection),
        schema="refdata_test_abc",
        contracts=[contract],
    )

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
