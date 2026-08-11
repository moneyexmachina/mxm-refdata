"""Unit tests for plain-SQL futures-product persistence operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal, Self, cast

import pytest
from psycopg import Connection, sql
from psycopg.types.json import Jsonb

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProduct,
    LastTradingRule,
)
from mxm.refdata.models.products.settlement import SettlementMethod
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.sources.futures_product import (
    FuturesProductSourceMetadata,
)
from mxm.refdata.sql.futures_products import (
    FuturesProductConflictError,
    FuturesProductPersistenceError,
    FuturesProductSourceConflictError,
    fetch_futures_product_sources,
    fetch_futures_products,
    fetch_futures_products_by_ids,
    insert_futures_products,
    upsert_futures_product_sources,
)
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed
type ParameterRow = tuple[object, ...]


_SOURCE_REVISION_A = "a" * 40
_SOURCE_REVISION_B = "b" * 40


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


def _contract_rules(
    *,
    with_weekday: bool = True,
) -> ContractRules:
    """Construct representative contract-generation rules."""

    if with_weekday:
        last_trading_rule = LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.WEEKDAY_OF_PERIOD,
            n_reference=3,
            business_day_offset=0,
            weekday=Weekday.from_str("Friday"),
        )
    else:
        last_trading_rule = LastTradingRule(
            period_offset=0,
            reference_event=ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
            n_reference=-3,
            business_day_offset=0,
        )

    return ContractRules(
        last_trading_rule=last_trading_rule,
        first_day_of_interest_rule=FirstDayOfInterestRule(
            shift_rule=FirstDayOfInterestShiftRule(
                shift_period_type=PeriodType.MONTH,
                n_shift={
                    "Mar": 63,
                    "Jun": 63,
                    "Sep": 63,
                    "Dec": 63,
                },
            ),
            reference_rule="next_b_day_after_period",
        ),
    )


def _product(
    product_id: str = "TEST_PRODUCT",
    *,
    optional_values: bool = True,
    with_weekday: bool = True,
) -> FuturesProduct:
    """Construct a representative complete operational futures product."""

    return FuturesProduct(
        product_id=product_id,
        asset_class="metals",
        venue="COMEX",
        description=f"{product_id} Futures",
        currency=Currency.USD,
        unit=ProductUnit.TROY_OUNCE,
        contract_size=100.0,
        valid_period_rule="HMUZ",
        listing_rule="Quarterly contracts",
        period_types=(PeriodType.MONTH,),
        settlement=SettlementMethod.PHYSICAL,
        last_trading_rule="Third Friday of delivery month",
        expiry_rule="Delivery month",
        trading_calendar="CME",
        contract_rules=_contract_rules(with_weekday=with_weekday),
        trading_hours=("23:00 - 22:00 UTC" if optional_values else None),
        tick_size=(0.1 if optional_values else None),
        tick_value=(10.0 if optional_values else None),
        initial_margin=(5000.0 if optional_values else None),
        maintenance_margin=(4500.0 if optional_values else None),
    )


def _source_metadata(
    *,
    source_relative_path: str = "metals/test_product.json",
    source_digest: str = "c" * 64,
    notes: tuple[str, ...] = (
        "Curated from exchange specification.",
        "Reviewed manually.",
    ),
) -> FuturesProductSourceMetadata:
    """Construct representative futures-product source metadata."""

    return FuturesProductSourceMetadata(
        schema_version="futures_product.v1",
        source_relative_path=source_relative_path,
        source_digest=source_digest,
        created_at=date(
            2026,
            6,
            1,
        ),
        updated_at=date(
            2026,
            7,
            1,
        ),
        review_status="reviewed",
        curator="mxm",
        source_type="exchange_specification",
        source_url="https://example.test/product",
        source_accessed_at=date(
            2026,
            5,
            31,
        ),
        curation_method="manual",
        assistance="llm-assisted",
        notes=notes,
    )


# ---------------------------------------------------------------------------
# PostgreSQL row encoding helpers
# ---------------------------------------------------------------------------


def _contract_rules_json(
    rules: ContractRules,
) -> dict[str, object]:
    """Encode contract rules as their expected PostgreSQL JSON value."""

    last_trading_rule = rules.last_trading_rule
    first_day_rule = rules.first_day_of_interest_rule
    shift_rule = first_day_rule.shift_rule

    return {
        "last_trading_rule": {
            "period_offset": (last_trading_rule.period_offset),
            "reference_event": (last_trading_rule.reference_event.value),
            "n_reference": (last_trading_rule.n_reference),
            "business_day_offset": (last_trading_rule.business_day_offset),
            "weekday": (
                last_trading_rule.weekday.as_str
                if last_trading_rule.weekday is not None
                else None
            ),
        },
        "first_day_of_interest_rule": {
            "shift_rule": {
                "shift_period_type": (shift_rule.shift_period_type.name),
                "n_shift": dict(shift_rule.n_shift),
            },
            "reference_rule": (first_day_rule.reference_rule),
        },
    }


def _product_row(
    product: FuturesProduct,
) -> PostgresRow:
    """Encode a futures product as one PostgreSQL result row."""

    return cast(
        PostgresRow,
        (
            product.product_id,
            product.asset_class,
            product.venue,
            product.description,
            product.currency.name,
            product.unit.name,
            product.contract_size,
            product.valid_period_rule,
            product.listing_rule,
            ",".join(period_type.name for period_type in product.period_types),
            product.settlement.name,
            product.last_trading_rule,
            product.expiry_rule,
            product.trading_calendar,
            _contract_rules_json(product.contract_rules),
            product.trading_hours,
            product.tick_size,
            product.tick_value,
            product.initial_margin,
            product.maintenance_margin,
        ),
    )


def _source_row(
    product_id: str,
    metadata: FuturesProductSourceMetadata,
    source_revision: str = _SOURCE_REVISION_A,
) -> PostgresRow:
    """Encode source state as one PostgreSQL result row."""

    return cast(
        PostgresRow,
        (
            product_id,
            metadata.schema_version,
            metadata.source_relative_path,
            metadata.source_digest,
            source_revision,
            metadata.created_at,
            metadata.updated_at,
            metadata.review_status,
            metadata.curator,
            metadata.source_type,
            metadata.source_url,
            metadata.source_accessed_at,
            metadata.curation_method,
            metadata.assistance,
            list(metadata.notes),
        ),
    )


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


def _jsonb_payload(
    value: object,
) -> object:
    """Return the wrapped value from a Psycopg Jsonb parameter."""

    assert isinstance(
        value,
        Jsonb,
    )

    return value.obj


# ---------------------------------------------------------------------------
# fetch_futures_products
# ---------------------------------------------------------------------------


def test_fetch_futures_products_returns_empty_mapping() -> None:
    """An empty futures-products table produces an empty mapping."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    products = fetch_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert products == {}
    assert connection.cursor_calls == 1


def test_fetch_futures_products_reconstructs_complete_domain_products() -> None:
    """Persisted rows reconstruct complete operational products."""

    first = _product("PRODUCT_A")
    second = _product(
        "PRODUCT_B",
        with_weekday=False,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _product_row(first),
                    _product_row(second),
                ]
            ),
        ]
    )

    products = fetch_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert products == {
        first.product_id: first,
        second.product_id: second,
    }


def test_fetch_futures_products_reconstructs_nullable_values() -> None:
    """Nullable operational fields remain None after reconstruction."""

    product = _product(
        optional_values=False,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    products = fetch_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    reconstructed = products[product.product_id]

    assert reconstructed == product
    assert reconstructed.trading_hours is None
    assert reconstructed.tick_size is None
    assert reconstructed.tick_value is None
    assert reconstructed.initial_margin is None
    assert reconstructed.maintenance_margin is None


def test_fetch_futures_products_uses_configured_schema() -> None:
    """The product query uses the caller-provided schema."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert execution.operation == "execute"
    assert '"refdata_test_abc"."futures_products"' in query_text
    assert '"public"."futures_products"' not in query_text


def test_fetch_futures_products_uses_deterministic_ordering() -> None:
    """The all-products query defines stable product-ID ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    execution = _single_execution(connection)

    assert "ORDER BY product_id" in _query_text(execution.query)


def test_fetch_futures_products_rejects_duplicate_database_identity() -> None:
    """A query returning one product ID twice is invalid state."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _product_row(product),
                    _product_row(product),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"duplicate product_id.*TEST_PRODUCT",
    ):
        fetch_futures_products(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


_PRODUCT_ROW = _product_row(_product())


@pytest.mark.parametrize(
    ("row", "error_match"),
    [
        (
            _row(
                *_PRODUCT_ROW[:-1],
            ),
            r"unexpected row shape",
        ),
        (
            _row(
                *_PRODUCT_ROW,
                "extra",
            ),
            r"unexpected row shape",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                0,
                123,
            ),
            r"product_id must be non-empty text",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                6,
                "100",
            ),
            r"contract_size must be numeric",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                4,
                "NOT_A_CURRENCY",
            ),
            r"currency is not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                5,
                "NOT_A_UNIT",
            ),
            r"unit is not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                9,
                "NOT_A_PERIOD_TYPE",
            ),
            r"period_types are not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                10,
                "NOT_A_SETTLEMENT_METHOD",
            ),
            r"settlement is not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                14,
                "not-an-object",
            ),
            r"contract_rules must be a JSON object",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                14,
                {
                    **_contract_rules_json(_contract_rules()),
                    "last_trading_rule": {
                        "period_offset": 0,
                        "reference_event": "not_an_event",
                        "n_reference": 3,
                        "business_day_offset": 0,
                        "weekday": "Friday",
                    },
                },
            ),
            r"reference_event is not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                14,
                {
                    **_contract_rules_json(_contract_rules()),
                    "last_trading_rule": {
                        "period_offset": 0,
                        "reference_event": (ReferenceEvent.WEEKDAY_OF_PERIOD.value),
                        "n_reference": 3,
                        "business_day_offset": 0,
                        "weekday": "Notaday",
                    },
                },
            ),
            r"weekday is not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                14,
                {
                    "last_trading_rule": (
                        _contract_rules_json(_contract_rules())["last_trading_rule"]
                    ),
                    "first_day_of_interest_rule": {
                        "shift_rule": {
                            "shift_period_type": "UNKNOWN",
                            "n_shift": {
                                "Mar": 63,
                            },
                        },
                        "reference_rule": ("next_b_day_after_period"),
                    },
                },
            ),
            r"shift_period_type is not recognised",
        ),
        (
            _row_with_value(
                _PRODUCT_ROW,
                14,
                {
                    "last_trading_rule": (
                        _contract_rules_json(_contract_rules())["last_trading_rule"]
                    ),
                    "first_day_of_interest_rule": {
                        "shift_rule": {
                            "shift_period_type": "MONTH",
                            "n_shift": {
                                "Mar": "sixty-three",
                            },
                        },
                        "reference_rule": ("next_b_day_after_period"),
                    },
                },
            ),
            r"n_shift.*Mar.*integer",
        ),
    ],
)
def test_fetch_futures_products_rejects_invalid_rows(
    row: PostgresRow,
    error_match: str,
) -> None:
    """Malformed persisted product rows cannot enter the domain."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=error_match,
    ):
        fetch_futures_products(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# fetch_futures_products_by_ids
# ---------------------------------------------------------------------------


def test_fetch_futures_products_by_ids_returns_early_for_empty_selection() -> None:
    """An empty product-ID selection performs no database operation."""

    connection = FakeConnection()

    products = fetch_futures_products_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_ids=[],
    )

    assert products == {}
    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_fetch_futures_products_by_ids_collapses_and_orders_ids() -> None:
    """Product-ID query parameters are unique and deterministic."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_products_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_ids=[
            "PRODUCT_C",
            "PRODUCT_A",
            "PRODUCT_B",
            "PRODUCT_A",
        ],
    )

    execution = _single_execution(connection)

    assert execution.operation == "execute"
    assert execution.parameters == (
        [
            "PRODUCT_A",
            "PRODUCT_B",
            "PRODUCT_C",
        ],
    )


def test_fetch_futures_products_by_ids_uses_expected_filter_and_schema() -> None:
    """Product-ID selection uses the configured table and text-array filter."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_products_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_ids=[
            "PRODUCT_A",
        ],
    )

    execution = _single_execution(connection)
    query_text = _query_text(execution.query)

    assert '"refdata_test_abc"."futures_products"' in query_text
    assert '"public"."futures_products"' not in query_text
    assert "product_id = ANY(%s::text[])" in query_text
    assert "ORDER BY product_id" in query_text


def test_fetch_futures_products_by_ids_reconstructs_matching_rows() -> None:
    """Matching rows reconstruct complete operational products."""

    product_a = _product("PRODUCT_A")
    product_b = _product(
        "PRODUCT_B",
        with_weekday=False,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _product_row(product_a),
                    _product_row(product_b),
                ]
            ),
        ]
    )

    products = fetch_futures_products_by_ids(
        _as_connection(connection),
        schema="refdata_test_abc",
        product_ids=[
            product_b.product_id,
            "MISSING_PRODUCT",
            product_a.product_id,
        ],
    )

    assert products == {
        product_a.product_id: product_a,
        product_b.product_id: product_b,
    }


# ---------------------------------------------------------------------------
# insert_futures_products: input handling and SQL encoding
# ---------------------------------------------------------------------------


def test_insert_futures_products_returns_early_for_empty_input() -> None:
    """An empty product insertion performs no database work."""

    connection = FakeConnection()

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[],
    )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_futures_products_collapses_identical_duplicates() -> None:
    """Repeated identical products produce one insert parameter row."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[
            product,
            product,
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert len(parameters) == 1
    assert parameters[0][0] == product.product_id


def test_insert_futures_products_rejects_conflicting_duplicate_input() -> None:
    """One product ID cannot identify two operational product values."""

    product = _product()
    conflicting = replace(
        product,
        description="Different persisted product definition",
    )

    connection = FakeConnection()

    with pytest.raises(
        FuturesProductConflictError,
        match=r"conflicting futures products.*TEST_PRODUCT",
    ):
        insert_futures_products(
            _as_connection(connection),
            schema="refdata_test_abc",
            products=[
                product,
                conflicting,
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_insert_futures_products_orders_rows_by_product_id() -> None:
    """Product insertion parameter ordering is deterministic."""

    product_b = _product("PRODUCT_B")
    product_a = _product("PRODUCT_A")

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product_a),
                    _product_row(product_b),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[
            product_b,
            product_a,
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert [row[0] for row in parameters] == [
        "PRODUCT_A",
        "PRODUCT_B",
    ]


def test_insert_futures_products_uses_configured_schema() -> None:
    """Product insertion targets the configured schema."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[product],
    )

    query_text = _query_text(connection.executions[0].query)

    assert '"refdata_test_abc"."futures_products"' in query_text
    assert '"public"."futures_products"' not in query_text


def test_insert_futures_products_uses_identity_conflict_clause() -> None:
    """Product replay is handled by product identity."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[product],
    )

    query_text = _query_text(connection.executions[0].query)

    assert "ON CONFLICT (product_id) DO NOTHING" in query_text


def test_insert_futures_products_encodes_complete_domain_values() -> None:
    """A complete domain product is encoded into the expected SQL values."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[product],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert len(parameters) == 1

    row = parameters[0]

    assert row[:14] == (
        product.product_id,
        product.asset_class,
        product.venue,
        product.description,
        product.currency.name,
        product.unit.name,
        product.contract_size,
        product.valid_period_rule,
        product.listing_rule,
        "MONTH",
        product.settlement.name,
        product.last_trading_rule,
        product.expiry_rule,
        product.trading_calendar,
    )

    assert _jsonb_payload(row[14]) == _contract_rules_json(product.contract_rules)

    assert row[15:] == (
        product.trading_hours,
        product.tick_size,
        product.tick_value,
        product.initial_margin,
        product.maintenance_margin,
    )


# ---------------------------------------------------------------------------
# insert_futures_products: persisted-state verification
# ---------------------------------------------------------------------------


def test_insert_futures_products_accepts_matching_persisted_state() -> None:
    """A matching product after insertion is accepted."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[product],
    )

    assert len(connection.executions) == 2
    assert connection.executions[0].operation == "executemany"
    assert connection.executions[1].operation == "execute"


def test_insert_futures_products_rejects_conflicting_persisted_state() -> None:
    """An existing operational product with changed values is rejected."""

    requested = _product()
    persisted = replace(
        requested,
        description="Conflicting persisted description",
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(persisted),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesProductConflictError,
        match=r"Persisted futures product conflicts.*TEST_PRODUCT",
    ):
        insert_futures_products(
            _as_connection(connection),
            schema="refdata_test_abc",
            products=[requested],
        )


def test_insert_futures_products_rejects_missing_persisted_state() -> None:
    """A requested product must exist after insertion."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(rows=[]),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"Futures products were not present after insertion.*TEST_PRODUCT",
    ):
        insert_futures_products(
            _as_connection(connection),
            schema="refdata_test_abc",
            products=[product],
        )


def test_insert_futures_products_validates_all_unique_ids() -> None:
    """The validation query receives every unique requested product ID."""

    product_c = _product("PRODUCT_C")
    product_a = _product("PRODUCT_A")
    product_b = _product("PRODUCT_B")

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product_a),
                    _product_row(product_b),
                    _product_row(product_c),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[
            product_c,
            product_a,
            product_b,
            product_a,
        ],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert "product_id = ANY(%s::text[])" in query_text
    assert validation_execution.parameters == (
        [
            "PRODUCT_A",
            "PRODUCT_B",
            "PRODUCT_C",
        ],
    )


def test_insert_futures_products_validation_uses_configured_schema() -> None:
    """Post-insert validation reads from the configured product table."""

    product = _product()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
        ]
    )

    insert_futures_products(
        _as_connection(connection),
        schema="refdata_test_abc",
        products=[product],
    )

    query_text = _query_text(connection.executions[1].query)

    assert '"refdata_test_abc"."futures_products"' in query_text
    assert '"public"."futures_products"' not in query_text


# ---------------------------------------------------------------------------
# fetch_futures_product_sources
# ---------------------------------------------------------------------------


def test_fetch_futures_product_sources_returns_empty_mapping() -> None:
    """An empty source table produces an empty mapping."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    sources = fetch_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert sources == {}


def test_fetch_futures_product_sources_reconstructs_metadata_and_revision() -> None:
    """Persisted source rows reconstruct metadata and repository revision."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                        _SOURCE_REVISION_A,
                    ),
                ]
            ),
        ]
    )

    sources = fetch_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    assert sources == {
        "TEST_PRODUCT": (
            metadata,
            _SOURCE_REVISION_A,
        )
    }


def test_fetch_futures_product_sources_reconstructs_notes_as_tuple() -> None:
    """JSON source notes reconstruct as an immutable tuple."""

    metadata = _source_metadata(
        notes=(
            "First",
            "Second",
        )
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    sources = fetch_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    reconstructed_metadata = sources["TEST_PRODUCT"][0]

    assert reconstructed_metadata.notes == (
        "First",
        "Second",
    )


def test_fetch_futures_product_sources_uses_configured_schema() -> None:
    """The source query uses the caller-provided schema."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    query_text = _query_text(_single_execution(connection).query)

    assert '"refdata_test_abc"."futures_product_sources"' in query_text
    assert '"public"."futures_product_sources"' not in query_text


def test_fetch_futures_product_sources_uses_deterministic_ordering() -> None:
    """Source rows use stable product-ID ordering."""

    connection = FakeConnection(
        [
            FakeCursor(rows=[]),
        ]
    )

    fetch_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
    )

    query_text = _query_text(_single_execution(connection).query)

    assert "ORDER BY product_id" in query_text


def test_fetch_futures_product_sources_rejects_duplicate_product_id() -> None:
    """A source query may return each product ID only once."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"duplicate product_id.*TEST_PRODUCT",
    ):
        fetch_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


def test_fetch_futures_product_sources_rejects_duplicate_source_path() -> None:
    """One persisted source-relative path may identify only one product."""

    first = _source_metadata(source_relative_path="shared/product.json")
    second = _source_metadata(
        source_relative_path="shared/product.json",
        source_digest="d" * 64,
    )

    connection = FakeConnection(
        [
            FakeCursor(
                rows=[
                    _source_row(
                        "PRODUCT_A",
                        first,
                    ),
                    _source_row(
                        "PRODUCT_B",
                        second,
                    ),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"duplicate source_relative_path.*shared/product\.json",
    ):
        fetch_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# fetch_futures_product_sources: invalid persisted state
# ---------------------------------------------------------------------------


def test_fetch_futures_product_sources_rejects_short_row() -> None:
    """A source row with missing columns cannot enter the domain."""

    valid_row = _source_row(
        "TEST_PRODUCT",
        _source_metadata(),
    )

    assert len(valid_row) == 15

    row = _row(
        *valid_row[:-1],
    )

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"unexpected row shape",
    ):
        fetch_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


def test_fetch_futures_product_sources_rejects_long_row() -> None:
    """A source row with excess columns cannot enter the domain."""

    valid_row = _source_row(
        "TEST_PRODUCT",
        _source_metadata(),
    )

    assert len(valid_row) == 15

    row = _row(
        *valid_row,
        "extra",
    )

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"unexpected row shape",
    ):
        fetch_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


@pytest.mark.parametrize(
    (
        "replacements",
        "error_match",
    ),
    [
        (
            {
                0: 123,
            },
            r"product_id must be non-empty text",
        ),
        (
            {
                4: "short",
            },
            r"source_revision must be a 40-character",
        ),
        (
            {
                5: "2026-06-01",
            },
            r"created_at must be a date",
        ),
        (
            {
                14: {
                    "not": "an-array",
                },
            },
            r"notes must be a JSON array",
        ),
        (
            {
                14: [
                    "valid",
                    123,
                ],
            },
            r"notes must contain only strings",
        ),
        (
            {
                3: "not-a-digest",
            },
            r"source metadata is invalid",
        ),
        (
            {
                5: date(
                    2026,
                    8,
                    1,
                ),
                6: date(
                    2026,
                    7,
                    1,
                ),
            },
            r"source metadata is invalid",
        ),
    ],
)
def test_fetch_futures_product_sources_rejects_invalid_values(
    replacements: dict[int, object],
    error_match: str,
) -> None:
    """Malformed persisted source values cannot enter the domain."""

    valid_row = _source_row(
        "TEST_PRODUCT",
        _source_metadata(),
    )

    assert len(valid_row) == 15

    row = _row_with_values(
        valid_row,
        replacements,
    )

    connection = FakeConnection(
        [
            FakeCursor(rows=[row]),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=error_match,
    ):
        fetch_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
        )


# ---------------------------------------------------------------------------
# upsert_futures_product_sources: input handling and SQL encoding
# ---------------------------------------------------------------------------


def test_upsert_futures_product_sources_returns_early_for_empty_input() -> None:
    """An empty source upsert performs no database work."""

    connection = FakeConnection()

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[],
    )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_upsert_futures_product_sources_collapses_identical_duplicates() -> None:
    """Repeated identical source state produces one upsert parameter row."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    state = (
        "TEST_PRODUCT",
        metadata,
        _SOURCE_REVISION_A,
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            state,
            state,
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert len(parameters) == 1
    assert parameters[0][0] == "TEST_PRODUCT"


def test_upsert_futures_product_sources_rejects_conflicting_duplicate_input() -> None:
    """One product ID cannot have two requested source states."""

    first = _source_metadata()
    second = replace(
        first,
        source_digest="d" * 64,
    )

    connection = FakeConnection()

    with pytest.raises(
        FuturesProductSourceConflictError,
        match=r"conflicting futures-product source state.*TEST_PRODUCT",
    ):
        upsert_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
            sources=[
                (
                    "TEST_PRODUCT",
                    first,
                    _SOURCE_REVISION_A,
                ),
                (
                    "TEST_PRODUCT",
                    second,
                    _SOURCE_REVISION_B,
                ),
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_upsert_futures_product_sources_rejects_duplicate_source_path() -> None:
    """One requested source path cannot belong to multiple products."""

    first = _source_metadata(source_relative_path="shared/product.json")
    second = _source_metadata(
        source_relative_path="shared/product.json",
        source_digest="d" * 64,
    )

    connection = FakeConnection()

    with pytest.raises(
        FuturesProductSourceConflictError,
        match=r"one source_relative_path to multiple products",
    ):
        upsert_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
            sources=[
                (
                    "PRODUCT_A",
                    first,
                    _SOURCE_REVISION_A,
                ),
                (
                    "PRODUCT_B",
                    second,
                    _SOURCE_REVISION_A,
                ),
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


@pytest.mark.parametrize(
    "source_revision",
    [
        "",
        "abc",
        "A" * 40,
        "z" * 40,
        "a" * 39,
        "a" * 41,
    ],
)
def test_upsert_futures_product_sources_rejects_invalid_revision(
    source_revision: str,
) -> None:
    """Invalid repository revisions fail before database access."""

    connection = FakeConnection()

    with pytest.raises(
        ValueError,
        match=r"source_revision must be a 40-character",
    ):
        upsert_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
            sources=[
                (
                    "TEST_PRODUCT",
                    _source_metadata(),
                    source_revision,
                )
            ],
        )

    assert connection.cursor_calls == 0
    assert connection.executions == []


def test_upsert_futures_product_sources_orders_rows_by_product_id() -> None:
    """Source upsert parameter ordering is deterministic."""

    metadata_a = _source_metadata(source_relative_path="a.json")
    metadata_b = _source_metadata(
        source_relative_path="b.json",
        source_digest="d" * 64,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "PRODUCT_A",
                        metadata_a,
                    ),
                    _source_row(
                        "PRODUCT_B",
                        metadata_b,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "PRODUCT_B",
                metadata_b,
                _SOURCE_REVISION_A,
            ),
            (
                "PRODUCT_A",
                metadata_a,
                _SOURCE_REVISION_A,
            ),
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert [row[0] for row in parameters] == [
        "PRODUCT_A",
        "PRODUCT_B",
    ]


def test_upsert_futures_product_sources_uses_configured_schema() -> None:
    """Source upsert targets the configured schema."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "TEST_PRODUCT",
                metadata,
                _SOURCE_REVISION_A,
            )
        ],
    )

    query_text = _query_text(connection.executions[0].query)

    assert '"refdata_test_abc"."futures_product_sources"' in query_text
    assert '"public"."futures_product_sources"' not in query_text


def test_upsert_futures_product_sources_uses_update_conflict_clause() -> None:
    """Source provenance may explicitly evolve for an existing product."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "TEST_PRODUCT",
                metadata,
                _SOURCE_REVISION_A,
            )
        ],
    )

    query_text = _query_text(connection.executions[0].query)

    assert "ON CONFLICT (product_id) DO UPDATE SET" in query_text
    assert "source_digest = EXCLUDED.source_digest" in query_text
    assert "source_revision = EXCLUDED.source_revision" in query_text
    assert "updated_at = EXCLUDED.updated_at" in query_text


def test_upsert_futures_product_sources_encodes_source_state() -> None:
    """Source metadata and repository revision encode into SQL values."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "TEST_PRODUCT",
                metadata,
                _SOURCE_REVISION_A,
            )
        ],
    )

    parameters = _executemany_parameters(connection.executions[0])

    assert len(parameters) == 1

    row = parameters[0]

    assert row[:14] == (
        "TEST_PRODUCT",
        metadata.schema_version,
        metadata.source_relative_path,
        metadata.source_digest,
        _SOURCE_REVISION_A,
        metadata.created_at,
        metadata.updated_at,
        metadata.review_status,
        metadata.curator,
        metadata.source_type,
        metadata.source_url,
        metadata.source_accessed_at,
        metadata.curation_method,
        metadata.assistance,
    )

    assert _jsonb_payload(row[14]) == list(metadata.notes)


# ---------------------------------------------------------------------------
# upsert_futures_product_sources: persisted-state verification
# ---------------------------------------------------------------------------


def test_upsert_futures_product_sources_accepts_matching_persisted_state() -> None:
    """Matching source state after the upsert is accepted."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "TEST_PRODUCT",
                metadata,
                _SOURCE_REVISION_A,
            )
        ],
    )

    assert len(connection.executions) == 2
    assert connection.executions[0].operation == "executemany"
    assert connection.executions[1].operation == "execute"


def test_upsert_futures_product_sources_rejects_missing_persisted_state() -> None:
    """Requested source state must exist after the upsert."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(rows=[]),
        ]
    )

    with pytest.raises(
        FuturesProductPersistenceError,
        match=r"source rows were not present after upsert.*TEST_PRODUCT",
    ):
        upsert_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
            sources=[
                (
                    "TEST_PRODUCT",
                    metadata,
                    _SOURCE_REVISION_A,
                )
            ],
        )


def test_upsert_futures_product_sources_rejects_mismatching_persisted_state() -> None:
    """Persisted source state must exactly match the requested post-upsert state."""

    requested = _source_metadata()
    persisted = replace(
        requested,
        source_digest="d" * 64,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        persisted,
                        _SOURCE_REVISION_B,
                    ),
                ]
            ),
        ]
    )

    with pytest.raises(
        FuturesProductSourceConflictError,
        match=r"source state differs.*TEST_PRODUCT",
    ):
        upsert_futures_product_sources(
            _as_connection(connection),
            schema="refdata_test_abc",
            sources=[
                (
                    "TEST_PRODUCT",
                    requested,
                    _SOURCE_REVISION_A,
                )
            ],
        )


def test_upsert_futures_product_sources_validates_all_unique_ids() -> None:
    """Post-upsert validation queries every affected product ID."""

    metadata_a = _source_metadata(source_relative_path="a.json")
    metadata_b = _source_metadata(
        source_relative_path="b.json",
        source_digest="d" * 64,
    )

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "PRODUCT_A",
                        metadata_a,
                    ),
                    _source_row(
                        "PRODUCT_B",
                        metadata_b,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "PRODUCT_B",
                metadata_b,
                _SOURCE_REVISION_A,
            ),
            (
                "PRODUCT_A",
                metadata_a,
                _SOURCE_REVISION_A,
            ),
            (
                "PRODUCT_A",
                metadata_a,
                _SOURCE_REVISION_A,
            ),
        ],
    )

    validation_execution = connection.executions[1]
    query_text = _query_text(validation_execution.query)

    assert "product_id = ANY(%s::text[])" in query_text
    assert validation_execution.parameters == (
        [
            "PRODUCT_A",
            "PRODUCT_B",
        ],
    )


def test_upsert_futures_product_sources_validation_uses_configured_schema() -> None:
    """Post-upsert validation reads from the configured source table."""

    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        "TEST_PRODUCT",
                        metadata,
                    ),
                ]
            ),
        ]
    )

    upsert_futures_product_sources(
        _as_connection(connection),
        schema="refdata_test_abc",
        sources=[
            (
                "TEST_PRODUCT",
                metadata,
                _SOURCE_REVISION_A,
            )
        ],
    )

    query_text = _query_text(connection.executions[1].query)

    assert '"refdata_test_abc"."futures_product_sources"' in query_text
    assert '"public"."futures_product_sources"' not in query_text


# ---------------------------------------------------------------------------
# Transaction ownership
# ---------------------------------------------------------------------------


def test_futures_product_operations_do_not_control_transactions() -> None:
    """Product SQL helpers neither commit nor roll back transactions."""

    product = _product()
    metadata = _source_metadata()

    connection = FakeConnection(
        [
            FakeCursor(),
            FakeCursor(
                rows=[
                    _product_row(product),
                ]
            ),
            FakeCursor(),
            FakeCursor(
                rows=[
                    _source_row(
                        product.product_id,
                        metadata,
                    ),
                ]
            ),
        ]
    )

    typed_connection = _as_connection(connection)

    insert_futures_products(
        typed_connection,
        schema="refdata_test_abc",
        products=[product],
    )

    upsert_futures_product_sources(
        typed_connection,
        schema="refdata_test_abc",
        sources=[
            (
                product.product_id,
                metadata,
                _SOURCE_REVISION_A,
            )
        ],
    )

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
