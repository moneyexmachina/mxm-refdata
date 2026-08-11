"""Plain-SQL persistence operations for futures contracts.

This module owns the PostgreSQL representation of ``FuturesContract`` objects.

All functions operate on a caller-provided Psycopg connection. They do not
open, commit, or roll back transactions. Transaction ownership belongs to the
higher-level materialisation or query operation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from psycopg import Connection, sql

from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed


class FuturesContractPersistenceError(RuntimeError):
    """Base error for invalid or inconsistent persisted contract state."""


class FuturesContractConflictError(FuturesContractPersistenceError):
    """Raised when one contract ID identifies different contract values."""


def fetch_futures_contracts(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> dict[str, FuturesContract]:
    """Return all persisted futures contracts keyed by contract ID.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_contracts`` table.

    Returns:
        Persisted contracts keyed by their stable contract identifiers.
    """

    query = sql.SQL(
        """
        SELECT
            contract_id,
            product_id,
            period_id,
            contract_size,
            currency,
            unit,
            trading_calendar,
            first_day_of_interest,
            last_trading_day
        FROM {}
        ORDER BY
            product_id,
            last_trading_day,
            contract_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_contracts",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    return _futures_contracts_from_rows(rows)


def fetch_futures_contracts_by_ids(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    contract_ids: Sequence[str],
) -> dict[str, FuturesContract]:
    """Return requested futures contracts keyed by contract ID.

    Missing requested IDs are simply absent from the returned mapping. Existence
    policy belongs to the higher-level query operation.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_contracts`` table.
        contract_ids:
            Contract identifiers to retrieve.

    Returns:
        Matching persisted contracts keyed by contract ID.
    """

    unique_contract_ids = sorted(set(contract_ids))

    if not unique_contract_ids:
        return {}

    for contract_id in unique_contract_ids:
        _validate_identifier(
            contract_id,
            field="contract_id",
        )

    query = sql.SQL(
        """
        SELECT
            contract_id,
            product_id,
            period_id,
            contract_size,
            currency,
            unit,
            trading_calendar,
            first_day_of_interest,
            last_trading_day
        FROM {}
        WHERE contract_id = ANY(%s::text[])
        ORDER BY contract_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_contracts",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (unique_contract_ids,),
    )

    return _futures_contracts_from_rows(rows)


def fetch_futures_contracts_for_product(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    product_id: str,
    period_type: PeriodType | None = None,
) -> dict[str, FuturesContract]:
    """Return persisted contracts for one futures product.

    When ``period_type`` is supplied, only contracts whose associated delivery
    period has that type are returned.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_contracts`` and
            ``periods`` tables.
        product_id:
            Product identifier whose contracts should be returned.
        period_type:
            Optional delivery-period type restricting the result.

    Returns:
        Matching contracts keyed by contract ID.
    """

    _validate_identifier(
        product_id,
        field="product_id",
    )

    if period_type is None:
        query = sql.SQL(
            """
            SELECT
                contract_id,
                product_id,
                period_id,
                contract_size,
                currency,
                unit,
                trading_calendar,
                first_day_of_interest,
                last_trading_day
            FROM {}
            WHERE product_id = %s
            ORDER BY
                contract_id
            """
        ).format(
            sql.Identifier(
                schema,
                "futures_contracts",
            )
        )

        rows = _fetch_rows(
            connection,
            query,
            (product_id,),
        )

        return _futures_contracts_from_rows(rows)

    query = sql.SQL(
        """
        SELECT
            contracts.contract_id,
            contracts.product_id,
            contracts.period_id,
            contracts.contract_size,
            contracts.currency,
            contracts.unit,
            contracts.trading_calendar,
            contracts.first_day_of_interest,
            contracts.last_trading_day
        FROM {} AS contracts
        JOIN {} AS periods
          ON periods.period_id = contracts.period_id
        WHERE contracts.product_id = %s
          AND periods.period_type = %s
        ORDER BY
            contracts.contract_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_contracts",
        ),
        sql.Identifier(
            schema,
            "periods",
        ),
    )

    rows = _fetch_rows(
        connection,
        query,
        (
            product_id,
            period_type.name,
        ),
    )

    return _futures_contracts_from_rows(rows)


def fetch_active_futures_contracts(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    as_of_date: date,
    product_ids: Sequence[str] | None = None,
) -> dict[str, FuturesContract]:
    """Return futures contracts active on an inclusive as-of date.

    A contract is active when:

    - ``first_day_of_interest <= as_of_date``; and
    - ``last_trading_day >= as_of_date``.

    When ``product_ids`` is ``None``, all products are considered. An empty
    explicit product selection returns immediately without database access.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_contracts`` table.
        as_of_date:
            Inclusive active-contract date.
        product_ids:
            Optional product identifiers restricting the result.

    Returns:
        Active contracts keyed by contract ID.
    """

    if product_ids is None:
        query = sql.SQL(
            """
            SELECT
                contract_id,
                product_id,
                period_id,
                contract_size,
                currency,
                unit,
                trading_calendar,
                first_day_of_interest,
                last_trading_day
            FROM {}
            WHERE first_day_of_interest <= %s
              AND last_trading_day >= %s
            ORDER BY
                product_id,
                contract_id
            """
        ).format(
            sql.Identifier(
                schema,
                "futures_contracts",
            )
        )

        rows = _fetch_rows(
            connection,
            query,
            (
                as_of_date,
                as_of_date,
            ),
        )

        return _futures_contracts_from_rows(rows)

    unique_product_ids = sorted(set(product_ids))

    if not unique_product_ids:
        return {}

    for product_id in unique_product_ids:
        _validate_identifier(
            product_id,
            field="product_id",
        )

    query = sql.SQL(
        """
        SELECT
            contract_id,
            product_id,
            period_id,
            contract_size,
            currency,
            unit,
            trading_calendar,
            first_day_of_interest,
            last_trading_day
        FROM {}
        WHERE first_day_of_interest <= %s
          AND last_trading_day >= %s
          AND product_id = ANY(%s::text[])
        ORDER BY
            product_id,
            contract_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_contracts",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (
            as_of_date,
            as_of_date,
            unique_product_ids,
        ),
    )

    return _futures_contracts_from_rows(rows)


def insert_futures_contracts(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    contracts: Sequence[FuturesContract],
) -> None:
    """Persist futures contracts idempotently while rejecting conflicts.

    A contract absent from the database is inserted.

    A contract already present with identical values is accepted as an
    idempotent no-op.

    A contract already present with different values raises
    ``FuturesContractConflictError``.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_contracts`` table.
        contracts:
            Domain contracts to persist.
    """

    contracts_by_id = _normalise_futures_contracts(contracts)

    if not contracts_by_id:
        return

    query = sql.SQL(
        """
        INSERT INTO {} (
            contract_id,
            product_id,
            period_id,
            contract_size,
            currency,
            unit,
            trading_calendar,
            first_day_of_interest,
            last_trading_day
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (contract_id) DO NOTHING
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_contracts",
        )
    )

    parameters = [
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
        for contract in sorted(
            contracts_by_id.values(),
            key=lambda item: item.contract_id,
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            parameters,
        )

    requested_contract_ids = tuple(sorted(contracts_by_id))

    persisted_contracts = fetch_futures_contracts_by_ids(
        connection,
        schema=schema,
        contract_ids=requested_contract_ids,
    )

    missing_contract_ids = [
        contract_id
        for contract_id in requested_contract_ids
        if contract_id not in persisted_contracts
    ]

    if missing_contract_ids:
        raise FuturesContractPersistenceError(
            "Futures contracts were not present after insertion: "
            f"{missing_contract_ids!r}"
        )

    for contract_id, expected_contract in contracts_by_id.items():
        persisted_contract = persisted_contracts[contract_id]

        if persisted_contract != expected_contract:
            raise FuturesContractConflictError(
                "Persisted futures contract conflicts with requested "
                f"contract for contract_id {contract_id!r}: "
                f"persisted={persisted_contract!r}, "
                f"requested={expected_contract!r}"
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


def _normalise_futures_contracts(
    contracts: Sequence[FuturesContract],
) -> dict[str, FuturesContract]:
    """Return contracts keyed by ID while rejecting invalid or conflicting input."""

    contracts_by_id: dict[
        str,
        FuturesContract,
    ] = {}

    for contract in contracts:
        _validate_futures_contract(contract)

        existing_contract = contracts_by_id.get(contract.contract_id)

        if existing_contract is None:
            contracts_by_id[contract.contract_id] = contract
            continue

        if existing_contract != contract:
            raise FuturesContractConflictError(
                "Input contains conflicting futures contracts for "
                f"contract_id {contract.contract_id!r}: "
                f"first={existing_contract!r}, "
                f"second={contract!r}"
            )

    return contracts_by_id


def _futures_contracts_from_rows(
    rows: Sequence[PostgresRow],
) -> dict[str, FuturesContract]:
    """Reconstruct contracts and reject duplicate database identities."""

    contracts: dict[
        str,
        FuturesContract,
    ] = {}

    for row in rows:
        contract = _futures_contract_from_row(row)

        if contract.contract_id in contracts:
            raise FuturesContractPersistenceError(
                "Futures-contract query returned duplicate "
                f"contract_id {contract.contract_id!r}"
            )

        contracts[contract.contract_id] = contract

    return contracts


def _futures_contract_from_row(
    row: PostgresRow,
) -> FuturesContract:
    """Reconstruct one validated futures contract from a database row."""

    if len(row) != 9:
        raise FuturesContractPersistenceError(
            f"Futures-contract query returned an unexpected row shape: {row!r}"
        )

    contract_id = _require_text(
        row[0],
        field="contract_id",
    )

    product_id = _require_text(
        row[1],
        field="product_id",
    )

    period_id = _require_text(
        row[2],
        field="period_id",
    )

    contract_size = _require_float(
        row[3],
        field="contract_size",
    )

    currency_text = _require_text(
        row[4],
        field="currency",
    )

    unit_text = _require_text(
        row[5],
        field="unit",
    )

    trading_calendar = _require_text(
        row[6],
        field="trading_calendar",
    )

    first_day_of_interest = _require_date(
        row[7],
        field="first_day_of_interest",
    )

    last_trading_day = _require_date(
        row[8],
        field="last_trading_day",
    )

    try:
        currency = Currency[currency_text]
    except KeyError as err:
        raise FuturesContractPersistenceError(
            f"Persisted currency is not recognised: {currency_text!r}"
        ) from err

    try:
        unit = ProductUnit[unit_text]
    except KeyError as err:
        raise FuturesContractPersistenceError(
            f"Persisted unit is not recognised: {unit_text!r}"
        ) from err

    contract = FuturesContract(
        contract_id=contract_id,
        product_id=product_id,
        period_id=period_id,
        contract_size=contract_size,
        unit=unit,
        currency=currency,
        trading_calendar=trading_calendar,
        first_day_of_interest=first_day_of_interest,
        last_trading_day=last_trading_day,
    )

    _validate_futures_contract(contract)

    return contract


def _validate_futures_contract(
    contract: FuturesContract,
) -> None:
    """Validate persistence-level futures-contract invariants."""

    _validate_identifier(
        contract.contract_id,
        field="contract_id",
    )

    _validate_identifier(
        contract.product_id,
        field="product_id",
    )

    _validate_identifier(
        contract.period_id,
        field="period_id",
    )

    if contract.contract_size <= 0:
        raise FuturesContractPersistenceError(
            "Futures-contract contract_size must be positive, "
            f"got {contract.contract_size!r}"
        )

    if not contract.trading_calendar:
        raise FuturesContractPersistenceError(
            "Futures-contract trading_calendar must be non-empty text, "
            f"got {contract.trading_calendar!r}"
        )

    expected_contract_id = f"{contract.product_id}.{contract.period_id}"

    if contract.contract_id != expected_contract_id:
        raise FuturesContractPersistenceError(
            "Futures-contract identity is inconsistent: "
            f"contract_id={contract.contract_id!r}, "
            f"expected={expected_contract_id!r}"
        )

    if contract.first_day_of_interest > contract.last_trading_day:
        raise FuturesContractPersistenceError(
            "Futures-contract lifecycle is invalid: "
            "first_day_of_interest must not be after "
            "last_trading_day; "
            f"contract_id={contract.contract_id!r}, "
            f"first_day_of_interest="
            f"{contract.first_day_of_interest!r}, "
            f"last_trading_day="
            f"{contract.last_trading_day!r}"
        )


def _validate_identifier(
    value: object,
    *,
    field: str,
) -> None:
    """Require a non-empty text identifier."""

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise FuturesContractPersistenceError(
            f"Futures-contract {field} must be non-empty text, got {value!r}"
        )


def _require_text(
    value: object,
    *,
    field: str,
) -> str:
    """Require a non-empty persisted text value."""

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise FuturesContractPersistenceError(
            f"Persisted {field} must be non-empty text, got {value!r}"
        )

    return value


def _require_float(
    value: object,
    *,
    field: str,
) -> float:
    """Require a persisted numeric value and return it as a float."""

    if not isinstance(
        value,
        int | float,
    ) or isinstance(
        value,
        bool,
    ):
        raise FuturesContractPersistenceError(
            f"Persisted {field} must be numeric, got {value!r}"
        )

    return float(value)


def _require_date(
    value: object,
    *,
    field: str,
) -> date:
    """Require a persisted date value."""

    if not isinstance(
        value,
        date,
    ):
        raise FuturesContractPersistenceError(
            f"Persisted {field} must be a date, got {value!r}"
        )

    return value
