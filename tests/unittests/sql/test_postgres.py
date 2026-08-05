"""Unit tests for the PostgreSQL connection and transaction boundary."""

from __future__ import annotations

from types import TracebackType
from typing import Any, cast

import pytest

from mxm.refdata.sql.postgres import ConnectFactory, PostgresDatabase


class FakeCursor:
    """Minimal context-managed cursor used by PostgreSQL unit tests."""

    def __init__(
        self,
        *,
        row: tuple[Any, ...] | None = (1,),
        execute_error: BaseException | None = None,
        events: list[str] | None = None,
    ) -> None:
        """Initialise cursor behaviour and recorded events."""

        self.row = row
        self.execute_error = execute_error
        self.events = events if events is not None else []
        self.executed: list[str] = []
        self.closed = False

    def __enter__(self) -> FakeCursor:
        """Enter the cursor context."""

        self.events.append("cursor_enter")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the cursor context."""

        del exc_type, exc_value, traceback

        self.closed = True
        self.events.append("cursor_exit")

    def execute(self, query: str) -> None:
        """Record or fail execution of a SQL query."""

        self.executed.append(query)
        self.events.append(f"execute:{query}")

        if self.execute_error is not None:
            raise self.execute_error

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return the configured query result row."""

        self.events.append("fetchone")
        return self.row


class FakeConnection:
    """Minimal Psycopg-like connection used by PostgreSQL unit tests."""

    def __init__(
        self,
        *,
        cursor: FakeCursor | None = None,
        commit_error: BaseException | None = None,
        rollback_error: BaseException | None = None,
        close_error: BaseException | None = None,
        events: list[str] | None = None,
    ) -> None:
        """Initialise connection behaviour and recorded events."""

        self.events = events if events is not None else []
        self.fake_cursor = cursor or FakeCursor(events=self.events)

        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.close_error = close_error

        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def cursor(self) -> FakeCursor:
        """Return the configured fake cursor."""

        self.events.append("cursor")
        return self.fake_cursor

    def commit(self) -> None:
        """Record or fail transaction commit."""

        self.commit_calls += 1
        self.events.append("commit")

        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        """Record or fail transaction rollback."""

        self.rollback_calls += 1
        self.events.append("rollback")

        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        """Record or fail connection closure."""

        self.close_calls += 1
        self.events.append("close")

        if self.close_error is not None:
            raise self.close_error


class FakeConnectFactory:
    """Callable fake that records connection URLs."""

    def __init__(
        self,
        connection: FakeConnection | None = None,
        *,
        connection_error: BaseException | None = None,
    ) -> None:
        """Initialise the configured connection or connection failure."""

        self.connection = connection or FakeConnection()
        self.connection_error = connection_error
        self.connection_urls: list[str] = []

    def __call__(self, connection_url: str) -> FakeConnection:
        """Record the URL and return or fail connection creation."""

        self.connection_urls.append(connection_url)

        if self.connection_error is not None:
            raise self.connection_error

        return self.connection


def _make_database(
    connection: FakeConnection | None = None,
    *,
    connection_url: str = "postgresql://mxm@localhost/mxm_dev",
    schema: str = "refdata",
    connection_error: BaseException | None = None,
) -> tuple[PostgresDatabase, FakeConnectFactory]:
    """Construct a database boundary backed by a fake connection factory."""

    connect_factory = FakeConnectFactory(
        connection,
        connection_error=connection_error,
    )

    database = PostgresDatabase(
        connection_url,
        schema=schema,
        connect_factory=cast(ConnectFactory, connect_factory),
    )

    return database, connect_factory


# ---------------------------------------------------------------------
# CONNECTION URL
# ---------------------------------------------------------------------


def test_normalises_sqlalchemy_psycopg_connection_url() -> None:
    connection = FakeConnection()
    database, connect_factory = _make_database(
        connection,
        connection_url=("postgresql+psycopg://mxm_dev_app@localhost:5432/mxm_dev"),
    )

    with database.transaction() as yielded_connection:
        assert yielded_connection is connection

    assert connect_factory.connection_urls == [
        "postgresql://mxm_dev_app@localhost:5432/mxm_dev"
    ]


def test_accepts_native_postgresql_connection_url() -> None:
    connection_url = "postgresql://mxm_dev_app@localhost:5432/mxm_dev"
    database, connect_factory = _make_database(
        connection_url=connection_url,
    )

    with database.transaction():
        pass

    assert connect_factory.connection_urls == [connection_url]


def test_strips_surrounding_connection_url_whitespace() -> None:
    database, connect_factory = _make_database(
        connection_url=("  postgresql+psycopg://mxm_dev_app@localhost/mxm_dev  "),
    )

    with database.transaction():
        pass

    assert connect_factory.connection_urls == [
        "postgresql://mxm_dev_app@localhost/mxm_dev"
    ]


@pytest.mark.parametrize(
    "connection_url",
    [
        "",
        "   ",
        "sqlite:///:memory:",
        "mysql://mxm@localhost/mxm_dev",
        "postgresql+asyncpg://mxm@localhost/mxm_dev",
        "postgres://mxm@localhost/mxm_dev",
    ],
)
def test_rejects_unsupported_connection_url(
    connection_url: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"PostgreSQL connection URL|Unsupported database",
    ):
        PostgresDatabase(connection_url)


# ---------------------------------------------------------------------
# SCHEMA VALIDATION
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema",
    [
        "refdata",
        "refdata_test_abc123",
        "a",
        "a_1",
        "schema123",
    ],
)
def test_accepts_valid_schema_name(schema: str) -> None:
    database = PostgresDatabase(
        "postgresql://mxm@localhost/mxm_dev",
        schema=schema,
    )

    assert database.schema == schema


def test_uses_refdata_as_default_schema() -> None:
    database = PostgresDatabase(
        "postgresql://mxm@localhost/mxm_dev",
    )

    assert database.schema == "refdata"


@pytest.mark.parametrize(
    "schema",
    [
        "",
        "RefData",
        "_refdata",
        "1refdata",
        "refdata.test",
        "refdata-test",
        '"refdata"',
        "refdata test",
        "refdata;drop_schema",
        "refdata/drop",
        "a" * 64,
    ],
)
def test_rejects_invalid_schema_name(schema: str) -> None:
    with pytest.raises(
        ValueError,
        match="Invalid PostgreSQL schema name",
    ):
        PostgresDatabase(
            "postgresql://mxm@localhost/mxm_dev",
            schema=schema,
        )


# ---------------------------------------------------------------------
# TRANSACTION LIFECYCLE
# ---------------------------------------------------------------------


def test_transaction_commits_and_closes_on_success() -> None:
    events: list[str] = []
    connection = FakeConnection(events=events)
    database, _ = _make_database(connection)

    with database.transaction() as yielded_connection:
        assert yielded_connection is connection
        events.append("caller")

    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert connection.close_calls == 1
    assert events == [
        "caller",
        "commit",
        "close",
    ]


def test_transaction_rolls_back_and_closes_on_caller_error() -> None:
    events: list[str] = []
    connection = FakeConnection(events=events)
    database, _ = _make_database(connection)
    expected_error = RuntimeError("caller failed")

    with pytest.raises(RuntimeError) as exc_info:
        with database.transaction():
            events.append("caller")
            raise expected_error

    assert exc_info.value is expected_error
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1
    assert events == [
        "caller",
        "rollback",
        "close",
    ]


def test_transaction_rolls_back_after_commit_failure() -> None:
    events: list[str] = []
    expected_error = RuntimeError("commit failed")
    connection = FakeConnection(
        commit_error=expected_error,
        events=events,
    )
    database, _ = _make_database(connection)

    with pytest.raises(RuntimeError) as exc_info:
        with database.transaction():
            events.append("caller")

    assert exc_info.value is expected_error
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1
    assert events == [
        "caller",
        "commit",
        "rollback",
        "close",
    ]


def test_transaction_propagates_connection_creation_error() -> None:
    expected_error = ConnectionError("database unavailable")
    database, connect_factory = _make_database(
        connection_error=expected_error,
    )

    with pytest.raises(ConnectionError) as exc_info:
        with database.transaction():
            pytest.fail("Transaction body must not be entered")

    assert exc_info.value is expected_error
    assert connect_factory.connection_urls == ["postgresql://mxm@localhost/mxm_dev"]


def test_rollback_failure_does_not_replace_original_error() -> None:
    original_error = RuntimeError("caller failed")
    rollback_error = RuntimeError("rollback failed")
    connection = FakeConnection(
        rollback_error=rollback_error,
    )
    database, _ = _make_database(connection)

    with pytest.raises(RuntimeError) as exc_info:
        with database.transaction():
            raise original_error

    assert exc_info.value is original_error
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1

    notes = getattr(exc_info.value, "__notes__", [])
    assert any("rollback also failed" in note for note in notes)


def test_close_failure_during_error_does_not_replace_original_error() -> None:
    original_error = RuntimeError("caller failed")
    close_error = RuntimeError("close failed")
    connection = FakeConnection(
        close_error=close_error,
    )
    database, _ = _make_database(connection)

    with pytest.raises(RuntimeError) as exc_info:
        with database.transaction():
            raise original_error

    assert exc_info.value is original_error
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1

    notes = getattr(exc_info.value, "__notes__", [])
    assert any("connection close also failed" in note for note in notes)


def test_close_failure_after_success_propagates() -> None:
    expected_error = RuntimeError("close failed")
    connection = FakeConnection(
        close_error=expected_error,
    )
    database, _ = _make_database(connection)

    with pytest.raises(RuntimeError) as exc_info:
        with database.transaction():
            pass

    assert exc_info.value is expected_error
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert connection.close_calls == 1


# ---------------------------------------------------------------------
# CONNECTIVITY CHECK
# ---------------------------------------------------------------------


def test_check_connection_returns_true_for_select_one() -> None:
    events: list[str] = []
    cursor = FakeCursor(
        row=(1,),
        events=events,
    )
    connection = FakeConnection(
        cursor=cursor,
        events=events,
    )
    database, _ = _make_database(connection)

    result = database.check_connection()

    assert result is True
    assert cursor.executed == ["SELECT 1"]
    assert cursor.closed is True
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert connection.close_calls == 1
    assert events == [
        "cursor",
        "cursor_enter",
        "execute:SELECT 1",
        "fetchone",
        "cursor_exit",
        "commit",
        "close",
    ]


@pytest.mark.parametrize(
    "row",
    [
        (0,),
        None,
        ("1",),
        (1, 2),
    ],
)
def test_check_connection_returns_false_for_unexpected_result(
    row: tuple[Any, ...] | None,
) -> None:
    cursor = FakeCursor(row=row)
    connection = FakeConnection(cursor=cursor)
    database, _ = _make_database(connection)

    result = database.check_connection()

    assert result is False
    assert cursor.executed == ["SELECT 1"]
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert connection.close_calls == 1


def test_check_connection_rolls_back_and_propagates_query_error() -> None:
    expected_error = RuntimeError("query failed")
    cursor = FakeCursor(
        execute_error=expected_error,
    )
    connection = FakeConnection(cursor=cursor)
    database, _ = _make_database(connection)

    with pytest.raises(RuntimeError) as exc_info:
        database.check_connection()

    assert exc_info.value is expected_error
    assert cursor.executed == ["SELECT 1"]
    assert cursor.closed is True
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1
    assert connection.close_calls == 1
