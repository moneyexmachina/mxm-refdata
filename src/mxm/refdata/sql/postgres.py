"""PostgreSQL connection and transaction boundary for MXM reference data.

This module provides the lowest-level PostgreSQL runtime abstraction used by
reference-data migrations, repositories, queries, and diagnostics.

It deliberately owns only:

- PostgreSQL connection URL validation and normalisation;
- validation of the owned PostgreSQL schema identifier;
- creation of Psycopg connections;
- commit, rollback, and connection-close lifecycle;
- basic database connectivity checking.

Schema migration, SQL query construction, and domain-object mapping belong to
higher-level modules.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Final

import psycopg
from psycopg import Connection

type PostgresRow = tuple[Any, ...]
type ConnectFactory = Callable[[str], Connection[PostgresRow]]

_SQLALCHEMY_PSYCOPG_PREFIX: Final = "postgresql+psycopg://"
_PSYCOPG_PREFIX: Final = "postgresql://"

_SCHEMA_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]{0,62}$",
    flags=re.ASCII,
)


def _normalise_connection_url(connection_url: str) -> str:
    """Return a Psycopg-compatible PostgreSQL connection URL.

    MXM configuration currently represents PostgreSQL URLs using SQLAlchemy's
    explicit Psycopg driver syntax::

        postgresql+psycopg://...

    Psycopg expects the ordinary PostgreSQL URI form::

        postgresql://...

    No other database dialects or PostgreSQL drivers are accepted.
    """

    normalised = connection_url.strip()

    if not normalised:
        raise ValueError("PostgreSQL connection URL must be non-empty")

    if normalised.startswith(_SQLALCHEMY_PSYCOPG_PREFIX):
        return _PSYCOPG_PREFIX + normalised.removeprefix(_SQLALCHEMY_PSYCOPG_PREFIX)

    if normalised.startswith(_PSYCOPG_PREFIX):
        return normalised

    raise ValueError(
        "Unsupported database connection URL. Expected a URL beginning with "
        f"{_SQLALCHEMY_PSYCOPG_PREFIX!r} or {_PSYCOPG_PREFIX!r}"
    )


def _validate_schema_name(schema: str) -> str:
    """Validate and return an unquoted PostgreSQL schema identifier.

    MXM schema names use lower-case ASCII identifiers only. Restricting the
    accepted syntax prevents callers from supplying qualified names, quoted
    identifiers, whitespace, or executable SQL fragments.

    PostgreSQL identifiers are limited to 63 bytes. The accepted character set
    is ASCII, so the 63-character limit is also the 63-byte limit.
    """

    if not _SCHEMA_NAME_PATTERN.fullmatch(schema):
        raise ValueError(
            "Invalid PostgreSQL schema name. Expected a lower-case ASCII "
            "identifier matching '^[a-z][a-z0-9_]{0,62}$', "
            f"got {schema!r}"
        )

    return schema


def _default_connect(
    connection_url: str,
) -> Connection[PostgresRow]:
    """Open a transactional Psycopg connection."""

    return psycopg.connect(
        connection_url,
        autocommit=False,
    )


class PostgresDatabase:
    """Own PostgreSQL connection creation and transaction lifecycle.

    The class is intentionally independent of MXM domain models and table
    definitions. Callers receive a normal Psycopg connection and remain
    responsible for creating cursors and executing their own SQL.

    A replaceable connection factory allows unit tests to exercise transaction
    behaviour without requiring a running PostgreSQL server.
    """

    def __init__(
        self,
        connection_url: str,
        *,
        schema: str = "refdata",
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        """Create a PostgreSQL runtime boundary.

        Args:
            connection_url:
                PostgreSQL URI. Both ``postgresql://`` and the transitional
                SQLAlchemy-style ``postgresql+psycopg://`` prefix are accepted.
            schema:
                Explicitly owned PostgreSQL schema. It must be a lower-case
                unquoted identifier of at most 63 ASCII characters.
            connect_factory:
                Optional connection constructor used primarily by unit tests.
                Production use defaults to :func:`psycopg.connect`.

        Raises:
            ValueError:
                If the connection URL or schema name is invalid.
        """

        self._connection_url = _normalise_connection_url(connection_url)
        self._schema = _validate_schema_name(schema)
        self._connect = connect_factory or _default_connect

    @property
    def schema(self) -> str:
        """Return the validated owned PostgreSQL schema name."""

        return self._schema

    @contextmanager
    def transaction(
        self,
    ) -> Generator[Connection[PostgresRow]]:
        """Yield one connection inside an explicit transaction boundary.

        A successful block is committed. Any exception raised by the caller or
        by the commit operation triggers a rollback and is then re-raised.

        The connection is closed in all cases. If rollback or close also fails
        while handling an existing exception, the cleanup failure is attached
        as a note without replacing the original error.
        """

        connection = self._connect(self._connection_url)
        pending_error: BaseException | None = None

        try:
            yield connection
            connection.commit()
        except BaseException as error:
            pending_error = error

            try:
                connection.rollback()
            except BaseException as rollback_error:
                error.add_note(f"PostgreSQL rollback also failed: {rollback_error!r}")

            raise
        finally:
            try:
                connection.close()
            except BaseException as close_error:
                if pending_error is None:
                    raise

                pending_error.add_note(
                    f"PostgreSQL connection close also failed: {close_error!r}"
                )

    def check_connection(self) -> bool:
        """Return whether PostgreSQL responds correctly to ``SELECT 1``.

        Connection and query exceptions deliberately propagate to the caller.
        Operational surfaces such as preflight can catch those exceptions and
        present them with the appropriate runtime context.
        """

        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()

        return row == (1,)
