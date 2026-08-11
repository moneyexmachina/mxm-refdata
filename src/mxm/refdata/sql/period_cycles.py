"""Plain-SQL persistence operations for period cycles and memberships.

This module owns the PostgreSQL representation of ``PeriodCycle`` and
``PeriodCycleMembership`` objects.

All functions operate on a caller-provided Psycopg connection. They do not
open, commit, or roll back transactions. Transaction ownership belongs to the
higher-level materialisation or query operation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from psycopg import Connection, sql

from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.sql.postgres import PostgresRow

type ExecutableQuery = sql.SQL | sql.Composed
type MembershipIdentity = tuple[str, str]
type MembershipPosition = tuple[str, int, int]


class PeriodCyclePersistenceError(RuntimeError):
    """Base error for invalid or inconsistent persisted cycle state."""


class PeriodCycleConflictError(PeriodCyclePersistenceError):
    """Raised when one cycle identity or position has conflicting values."""


def fetch_period_cycles(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> dict[str, PeriodCycle]:
    """Return all persisted period cycles keyed by cycle ID.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``period_cycles`` table.

    Returns:
        Persisted cycles keyed by their stable cycle identifiers.
    """

    query = sql.SQL(
        """
        SELECT
            cycle_id,
            name,
            period_type,
            instance_kind,
            cycle_size
        FROM {}
        ORDER BY cycle_id
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycles",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    return _period_cycles_from_rows(rows)


def fetch_period_cycle_memberships(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> dict[MembershipIdentity, PeriodCycleMembership]:
    """Return all persisted cycle memberships keyed by membership identity.

    Membership identity is ``(cycle_id, period_id)``.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the
            ``period_cycle_memberships`` table.

    Returns:
        Persisted memberships keyed by ``(cycle_id, period_id)``.
    """

    query = sql.SQL(
        """
        SELECT
            cycle_id,
            period_id,
            cycle_instance,
            cycle_element
        FROM {}
        ORDER BY
            cycle_id,
            cycle_instance,
            cycle_element,
            period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycle_memberships",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    return _period_cycle_memberships_from_rows(rows)


def insert_period_cycles(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    period_cycles: Sequence[PeriodCycle],
) -> None:
    """Persist period cycles idempotently while rejecting conflicts.

    A cycle absent from the database is inserted.

    A cycle already present with identical values is accepted as an
    idempotent no-op.

    A cycle already present with different values raises
    ``PeriodCycleConflictError``.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``period_cycles`` table.
        period_cycles:
            Domain cycles to persist.

    Raises:
        PeriodCycleConflictError:
            If duplicate input or persisted state assigns different values to
            the same cycle ID.
        PeriodCyclePersistenceError:
            If an expected cycle is absent after insertion.
    """

    cycles_by_id = _normalise_period_cycles(period_cycles)

    if not cycles_by_id:
        return

    query = sql.SQL(
        """
        INSERT INTO {} (
            cycle_id,
            name,
            period_type,
            instance_kind,
            cycle_size
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (cycle_id) DO NOTHING
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycles",
        )
    )

    parameters = [
        (
            cycle.cycle_id,
            cycle.name,
            cycle.period_type.name,
            cycle.instance_kind.value,
            cycle.cycle_size,
        )
        for cycle in sorted(
            cycles_by_id.values(),
            key=lambda item: item.cycle_id,
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            parameters,
        )

    persisted_cycles = fetch_period_cycles_by_ids(
        connection,
        schema=schema,
        cycle_ids=tuple(cycles_by_id),
    )

    missing_cycle_ids = cycles_by_id.keys() - persisted_cycles.keys()

    if missing_cycle_ids:
        raise PeriodCyclePersistenceError(
            "Period cycles were not present after insertion: "
            f"{sorted(missing_cycle_ids)!r}"
        )

    for cycle_id, expected_cycle in cycles_by_id.items():
        persisted_cycle = persisted_cycles[cycle_id]

        if persisted_cycle != expected_cycle:
            raise PeriodCycleConflictError(
                "Persisted period cycle conflicts with requested cycle for "
                f"cycle_id {cycle_id!r}: "
                f"persisted={persisted_cycle!r}, "
                f"requested={expected_cycle!r}"
            )


def insert_period_cycle_memberships(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    memberships: Sequence[PeriodCycleMembership],
) -> None:
    """Persist cycle memberships idempotently while rejecting conflicts.

    Memberships have two relevant identities:

    - membership identity: ``(cycle_id, period_id)``;
    - cycle position:
      ``(cycle_id, cycle_instance, cycle_element)``.

    An identical existing membership is accepted as an idempotent no-op.

    A membership conflict is raised when:

    - the same ``(cycle_id, period_id)`` has a different cycle position; or
    - the same cycle position is occupied by a different period.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the
            ``period_cycle_memberships`` table.
        memberships:
            Domain memberships to persist.

    Raises:
        PeriodCycleConflictError:
            If input or persisted state contains conflicting membership
            identities or cycle positions.
        PeriodCyclePersistenceError:
            If an expected membership is absent after insertion.
    """

    (
        memberships_by_identity,
        memberships_by_position,
    ) = _normalise_period_cycle_memberships(memberships)

    if not memberships_by_identity:
        return

    query = sql.SQL(
        """
        INSERT INTO {} (
            cycle_id,
            period_id,
            cycle_instance,
            cycle_element
        )
        VALUES (
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT DO NOTHING
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycle_memberships",
        )
    )

    parameters = [
        (
            membership.cycle_id,
            membership.period_id,
            membership.cycle_instance,
            membership.cycle_element,
        )
        for membership in sorted(
            memberships_by_identity.values(),
            key=lambda item: (
                item.cycle_id,
                item.cycle_instance,
                item.cycle_element,
                item.period_id,
            ),
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            parameters,
        )

    affected_cycle_ids = tuple(
        sorted({membership.cycle_id for membership in memberships_by_identity.values()})
    )

    persisted_memberships = fetch_period_cycle_memberships_by_cycle_ids(
        connection,
        schema=schema,
        cycle_ids=affected_cycle_ids,
    )

    persisted_by_position = _memberships_by_position(persisted_memberships.values())

    for identity, expected_membership in memberships_by_identity.items():
        persisted_membership = persisted_memberships.get(identity)

        if persisted_membership is not None:
            if persisted_membership != expected_membership:
                raise PeriodCycleConflictError(
                    "Persisted period-cycle membership conflicts with "
                    "requested membership for identity "
                    f"{identity!r}: "
                    f"persisted={persisted_membership!r}, "
                    f"requested={expected_membership!r}"
                )

            continue

        expected_position = _membership_position(expected_membership)

        occupying_membership = persisted_by_position.get(expected_position)

        if occupying_membership is not None:
            raise PeriodCycleConflictError(
                "Persisted period-cycle position is occupied by a different "
                f"membership for position {expected_position!r}: "
                f"persisted={occupying_membership!r}, "
                f"requested={expected_membership!r}"
            )

        raise PeriodCyclePersistenceError(
            "Period-cycle membership was not present after insertion: "
            f"{expected_membership!r}"
        )

    requested_positions = set(memberships_by_position)

    for position in requested_positions:
        persisted_membership = persisted_by_position.get(position)

        if persisted_membership is None:
            raise PeriodCyclePersistenceError(
                f"Period-cycle position was not present after insertion: {position!r}"
            )

        expected_membership = memberships_by_position[position]

        if persisted_membership != expected_membership:
            raise PeriodCycleConflictError(
                "Persisted period-cycle position conflicts with requested "
                f"membership for position {position!r}: "
                f"persisted={persisted_membership!r}, "
                f"requested={expected_membership!r}"
            )


def fetch_period_cycles_by_ids(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    cycle_ids: Sequence[str],
) -> dict[str, PeriodCycle]:
    """Return the requested persisted cycles keyed by cycle ID."""

    unique_cycle_ids = sorted(set(cycle_ids))

    if not unique_cycle_ids:
        return {}

    query = sql.SQL(
        """
        SELECT
            cycle_id,
            name,
            period_type,
            instance_kind,
            cycle_size
        FROM {}
        WHERE cycle_id = ANY(%s::text[])
        ORDER BY cycle_id
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycles",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (unique_cycle_ids,),
    )

    return _period_cycles_from_rows(rows)


def fetch_period_cycle_memberships_by_cycle_ids(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    cycle_ids: Sequence[str],
) -> dict[MembershipIdentity, PeriodCycleMembership]:
    """Return memberships belonging to the requested cycle IDs."""

    unique_cycle_ids = sorted(set(cycle_ids))

    if not unique_cycle_ids:
        return {}

    query = sql.SQL(
        """
        SELECT
            cycle_id,
            period_id,
            cycle_instance,
            cycle_element
        FROM {}
        WHERE cycle_id = ANY(%s::text[])
        ORDER BY
            cycle_id,
            cycle_instance,
            cycle_element,
            period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycle_memberships",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (unique_cycle_ids,),
    )

    return _period_cycle_memberships_from_rows(rows)


def fetch_period_cycle_memberships_for_periods(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    cycle_id: str,
    period_ids: Sequence[str],
) -> dict[MembershipIdentity, PeriodCycleMembership]:
    """Return memberships for selected periods within one cycle.

    Missing requested period IDs are simply absent from the returned mapping.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the
            ``period_cycle_memberships`` table.
        cycle_id:
            Period-cycle identifier whose memberships should be returned.
        period_ids:
            Period identifiers to include.

    Returns:
        Matching memberships keyed by ``(cycle_id, period_id)``.
    """

    unique_period_ids = sorted(set(period_ids))

    if not unique_period_ids:
        return {}

    query = sql.SQL(
        """
        SELECT
            cycle_id,
            period_id,
            cycle_instance,
            cycle_element
        FROM {}
        WHERE cycle_id = %s
          AND period_id = ANY(%s::text[])
        ORDER BY period_id
        """
    ).format(
        sql.Identifier(
            schema,
            "period_cycle_memberships",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (
            cycle_id,
            unique_period_ids,
        ),
    )

    return _period_cycle_memberships_from_rows(rows)


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


def _normalise_period_cycles(
    period_cycles: Sequence[PeriodCycle],
) -> dict[str, PeriodCycle]:
    """Return cycles keyed by ID while rejecting conflicting input."""

    cycles_by_id: dict[str, PeriodCycle] = {}

    for cycle in period_cycles:
        existing_cycle = cycles_by_id.get(cycle.cycle_id)

        if existing_cycle is None:
            cycles_by_id[cycle.cycle_id] = cycle
            continue

        if existing_cycle != cycle:
            raise PeriodCycleConflictError(
                "Input contains conflicting period cycles for "
                f"cycle_id {cycle.cycle_id!r}: "
                f"first={existing_cycle!r}, "
                f"second={cycle!r}"
            )

    return cycles_by_id


def _normalise_period_cycle_memberships(
    memberships: Sequence[PeriodCycleMembership],
) -> tuple[
    dict[MembershipIdentity, PeriodCycleMembership],
    dict[MembershipPosition, PeriodCycleMembership],
]:
    """Index memberships while rejecting conflicting input."""

    memberships_by_identity: dict[
        MembershipIdentity,
        PeriodCycleMembership,
    ] = {}

    memberships_by_position: dict[
        MembershipPosition,
        PeriodCycleMembership,
    ] = {}

    for membership in memberships:
        identity = _membership_identity(membership)
        position = _membership_position(membership)

        existing_identity_membership = memberships_by_identity.get(identity)

        if existing_identity_membership is not None:
            if existing_identity_membership != membership:
                raise PeriodCycleConflictError(
                    "Input contains conflicting period-cycle memberships for "
                    f"identity {identity!r}: "
                    f"first={existing_identity_membership!r}, "
                    f"second={membership!r}"
                )
        else:
            memberships_by_identity[identity] = membership

        existing_position_membership = memberships_by_position.get(position)

        if existing_position_membership is not None:
            if existing_position_membership != membership:
                raise PeriodCycleConflictError(
                    "Input contains conflicting period-cycle memberships for "
                    f"position {position!r}: "
                    f"first={existing_position_membership!r}, "
                    f"second={membership!r}"
                )
        else:
            memberships_by_position[position] = membership

    return (
        memberships_by_identity,
        memberships_by_position,
    )


def _period_cycles_from_rows(
    rows: Sequence[PostgresRow],
) -> dict[str, PeriodCycle]:
    """Reconstruct cycles and reject duplicate database identities."""

    cycles: dict[str, PeriodCycle] = {}

    for row in rows:
        cycle = _period_cycle_from_row(row)

        if cycle.cycle_id in cycles:
            raise PeriodCyclePersistenceError(
                f"Period-cycle query returned duplicate cycle_id {cycle.cycle_id!r}"
            )

        cycles[cycle.cycle_id] = cycle

    return cycles


def _period_cycle_memberships_from_rows(
    rows: Sequence[PostgresRow],
) -> dict[MembershipIdentity, PeriodCycleMembership]:
    """Reconstruct memberships and reject duplicate identities or positions."""

    memberships_by_identity: dict[
        MembershipIdentity,
        PeriodCycleMembership,
    ] = {}

    memberships_by_position: dict[
        MembershipPosition,
        PeriodCycleMembership,
    ] = {}

    for row in rows:
        membership = _period_cycle_membership_from_row(row)
        identity = _membership_identity(membership)
        position = _membership_position(membership)

        if identity in memberships_by_identity:
            raise PeriodCyclePersistenceError(
                "Period-cycle membership query returned duplicate identity "
                f"{identity!r}"
            )

        if position in memberships_by_position:
            raise PeriodCyclePersistenceError(
                "Period-cycle membership query returned duplicate position "
                f"{position!r}"
            )

        memberships_by_identity[identity] = membership
        memberships_by_position[position] = membership

    return memberships_by_identity


def _memberships_by_position(
    memberships: Iterable[PeriodCycleMembership],
) -> dict[MembershipPosition, PeriodCycleMembership]:
    """Index persisted memberships by cycle position."""

    memberships_by_position: dict[
        MembershipPosition,
        PeriodCycleMembership,
    ] = {}

    for membership in memberships:
        position = _membership_position(membership)

        existing_membership = memberships_by_position.get(position)

        if existing_membership is not None:
            raise PeriodCyclePersistenceError(
                "Persisted period-cycle memberships contain duplicate "
                f"position {position!r}: "
                f"first={existing_membership!r}, "
                f"second={membership!r}"
            )

        memberships_by_position[position] = membership

    return memberships_by_position


def _membership_identity(
    membership: PeriodCycleMembership,
) -> MembershipIdentity:
    """Return the primary identity of one membership."""

    return (
        membership.cycle_id,
        membership.period_id,
    )


def _membership_position(
    membership: PeriodCycleMembership,
) -> MembershipPosition:
    """Return the unique cycle position of one membership."""

    return (
        membership.cycle_id,
        membership.cycle_instance,
        membership.cycle_element,
    )


def _period_cycle_from_row(
    row: PostgresRow,
) -> PeriodCycle:
    """Reconstruct one validated period cycle from a database row."""

    if len(row) != 5:
        raise PeriodCyclePersistenceError(
            f"Period-cycle query returned an unexpected row shape: {row!r}"
        )

    cycle_id = row[0]
    name = row[1]
    period_type_text = row[2]
    instance_kind_text = row[3]
    cycle_size = row[4]

    if not isinstance(cycle_id, str):
        raise PeriodCyclePersistenceError(
            f"Persisted cycle_id must be text, got {cycle_id!r}"
        )

    if not isinstance(name, str):
        raise PeriodCyclePersistenceError(
            f"Persisted cycle name must be text, got {name!r}"
        )

    if not isinstance(period_type_text, str):
        raise PeriodCyclePersistenceError(
            f"Persisted period_type must be text, got {period_type_text!r}"
        )

    if not isinstance(instance_kind_text, str):
        raise PeriodCyclePersistenceError(
            f"Persisted instance_kind must be text, got {instance_kind_text!r}"
        )

    if not isinstance(cycle_size, int) or isinstance(cycle_size, bool):
        raise PeriodCyclePersistenceError(
            f"Persisted cycle_size must be an integer, got {cycle_size!r}"
        )

    try:
        period_type = PeriodType[period_type_text]
    except KeyError as err:
        raise PeriodCyclePersistenceError(
            f"Persisted period_type is not recognised: {period_type_text!r}"
        ) from err

    try:
        instance_kind = CycleInstanceKind(instance_kind_text)
    except ValueError as err:
        raise PeriodCyclePersistenceError(
            f"Persisted instance_kind is not recognised: {instance_kind_text!r}"
        ) from err

    try:
        return PeriodCycle(
            cycle_id=cycle_id,
            name=name,
            period_type=period_type,
            cycle_size=cycle_size,
            instance_kind=instance_kind,
        )
    except ValueError as err:
        raise PeriodCyclePersistenceError(
            f"Persisted period cycle is invalid: {row!r}"
        ) from err


def _period_cycle_membership_from_row(
    row: PostgresRow,
) -> PeriodCycleMembership:
    """Reconstruct one validated membership from a database row."""

    if len(row) != 4:
        raise PeriodCyclePersistenceError(
            f"Period-cycle membership query returned an unexpected row shape: {row!r}"
        )

    cycle_id = row[0]
    period_id = row[1]
    cycle_instance = row[2]
    cycle_element = row[3]

    if not isinstance(cycle_id, str):
        raise PeriodCyclePersistenceError(
            f"Persisted membership cycle_id must be text, got {cycle_id!r}"
        )

    if not isinstance(period_id, str):
        raise PeriodCyclePersistenceError(
            f"Persisted membership period_id must be text, got {period_id!r}"
        )

    if not isinstance(cycle_instance, int) or isinstance(cycle_instance, bool):
        raise PeriodCyclePersistenceError(
            f"Persisted cycle_instance must be an integer, got {cycle_instance!r}"
        )

    if not isinstance(cycle_element, int) or isinstance(cycle_element, bool):
        raise PeriodCyclePersistenceError(
            f"Persisted cycle_element must be an integer, got {cycle_element!r}"
        )

    try:
        return PeriodCycleMembership(
            cycle_id=cycle_id,
            period_id=period_id,
            cycle_instance=cycle_instance,
            cycle_element=cycle_element,
        )
    except ValueError as err:
        raise PeriodCyclePersistenceError(
            f"Persisted period-cycle membership is invalid: {row!r}"
        ) from err
