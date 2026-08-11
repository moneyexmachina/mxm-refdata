"""Plain-SQL persistence operations for futures products and source metadata.

This module owns the PostgreSQL representation of ``FuturesProduct`` and
``FuturesProductSourceMetadata`` objects.

Operational futures products and their source provenance are persisted
separately:

- ``futures_products`` contains the complete operational product definition;
- ``futures_product_sources`` contains source and curation metadata together
  with the repository revision from which the source was loaded.

All functions operate on a caller-provided Psycopg connection. They do not
open, commit, or roll back transactions. Transaction ownership belongs to the
higher-level materialisation or query operation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import cast

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
from mxm.refdata.sql.postgres import PostgresRow
from mxm.refdata.utils.period_types_codec import (
    decode_period_types,
    encode_period_types,
)
from mxm.types import JSONObj

type ExecutableQuery = sql.SQL | sql.Composed

type FuturesProductSourceState = tuple[
    FuturesProductSourceMetadata,
    str,
]

type FuturesProductSourceWrite = tuple[
    str,
    FuturesProductSourceMetadata,
    str,
]


_GIT_REVISION_PATTERN = re.compile(
    r"^[0-9a-f]{40}$",
    flags=re.ASCII,
)


class FuturesProductPersistenceError(RuntimeError):
    """Base error for invalid or inconsistent persisted futures-product state."""


class FuturesProductConflictError(FuturesProductPersistenceError):
    """Raised when one product ID identifies different operational values."""


class FuturesProductSourceConflictError(FuturesProductPersistenceError):
    """Raised when futures-product source state is internally inconsistent."""


# ---------------------------------------------------------------------
# FUTURES PRODUCT READS
# ---------------------------------------------------------------------


def fetch_futures_products(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> dict[str, FuturesProduct]:
    """Return all persisted futures products keyed by product ID.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_products`` table.

    Returns:
        Persisted futures products keyed by their stable product identifiers.
    """

    query = sql.SQL(
        """
        SELECT
            product_id,
            asset_class,
            venue,
            description,
            currency,
            unit,
            contract_size,
            valid_period_rule,
            listing_rule,
            period_types,
            settlement,
            last_trading_rule,
            expiry_rule,
            trading_calendar,
            contract_rules,
            trading_hours,
            tick_size,
            tick_value,
            initial_margin,
            maintenance_margin
        FROM {}
        ORDER BY product_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_products",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    return _futures_products_from_rows(rows)


def fetch_futures_product_sources(
    connection: Connection[PostgresRow],
    *,
    schema: str,
) -> dict[str, FuturesProductSourceState]:
    """Return all persisted futures-product source state keyed by product ID.

    The value for each product is ``(metadata, source_revision)``.

    Repository revision remains conceptually separate from
    ``FuturesProductSourceMetadata`` even though both are stored in the same
    relational row.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_product_sources`` table.

    Returns:
        Persisted source state keyed by product ID.
    """

    query = sql.SQL(
        """
        SELECT
            product_id,
            schema_version,
            source_relative_path,
            source_digest,
            source_revision,
            created_at,
            updated_at,
            review_status,
            curator,
            source_type,
            source_url,
            source_accessed_at,
            curation_method,
            assistance,
            notes
        FROM {}
        ORDER BY product_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_product_sources",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
    )

    return _futures_product_sources_from_rows(rows)


# ---------------------------------------------------------------------
# FUTURES PRODUCT WRITES
# ---------------------------------------------------------------------


def insert_futures_products(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    products: Sequence[FuturesProduct],
) -> None:
    """Persist operational futures products idempotently.

    A product absent from the database is inserted.

    A product already present with identical operational values is accepted as
    an idempotent no-op.

    A product already present with different operational values raises
    ``FuturesProductConflictError``.

    Source metadata is deliberately not handled by this operation.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_products`` table.
        products:
            Operational futures products to persist.

    Raises:
        FuturesProductConflictError:
            If duplicate input or persisted state assigns different
            operational values to the same product ID.
        FuturesProductPersistenceError:
            If an expected product is absent after insertion.
    """

    products_by_id = _normalise_futures_products(products)

    if not products_by_id:
        return

    query = sql.SQL(
        """
        INSERT INTO {} (
            product_id,
            asset_class,
            venue,
            description,
            currency,
            unit,
            contract_size,
            valid_period_rule,
            listing_rule,
            period_types,
            settlement,
            last_trading_rule,
            expiry_rule,
            trading_calendar,
            contract_rules,
            trading_hours,
            tick_size,
            tick_value,
            initial_margin,
            maintenance_margin
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
            %s,
            %s,
            %s,
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
        ON CONFLICT (product_id) DO NOTHING
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_products",
        )
    )

    parameters = [
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
            encode_period_types(product.period_types),
            product.settlement.name,
            product.last_trading_rule,
            product.expiry_rule,
            product.trading_calendar,
            Jsonb(_contract_rules_to_json(product.contract_rules)),
            product.trading_hours,
            product.tick_size,
            product.tick_value,
            product.initial_margin,
            product.maintenance_margin,
        )
        for product in sorted(
            products_by_id.values(),
            key=lambda item: item.product_id,
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            parameters,
        )

    persisted_products = fetch_futures_products_by_ids(
        connection,
        schema=schema,
        product_ids=tuple(products_by_id),
    )

    missing_product_ids = products_by_id.keys() - persisted_products.keys()

    if missing_product_ids:
        raise FuturesProductPersistenceError(
            "Futures products were not present after insertion: "
            f"{sorted(missing_product_ids)!r}"
        )

    for (
        product_id,
        expected_product,
    ) in products_by_id.items():
        persisted_product = persisted_products[product_id]

        if persisted_product != expected_product:
            raise FuturesProductConflictError(
                "Persisted futures product conflicts with requested product for "
                f"product_id {product_id!r}: "
                f"persisted={persisted_product!r}, "
                f"requested={expected_product!r}"
            )


def upsert_futures_product_sources(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    sources: Sequence[FuturesProductSourceWrite],
) -> None:
    """Persist futures-product source metadata and repository revisions.

    Unlike operational ``FuturesProduct`` state, source provenance is allowed
    to evolve while the operational product remains identical. Existing source
    rows are therefore updated explicitly.

    Duplicate input for one product ID is accepted only when the complete
    source state is identical. Conflicting duplicate input is rejected before
    writing so that outcome never depends on input ordering.

    Args:
        connection:
            Active Psycopg connection owned by the caller.
        schema:
            PostgreSQL schema containing the ``futures_product_sources`` table.
        sources:
            ``(product_id, metadata, source_revision)`` values to persist.

    Raises:
        FuturesProductSourceConflictError:
            If duplicate input assigns inconsistent source state to one product
            ID or assigns one source-relative path to multiple products.
        FuturesProductPersistenceError:
            If expected source state is absent or differs after the upsert.
        ValueError:
            If an input product ID or source revision is invalid.
    """

    sources_by_product_id = _normalise_futures_product_sources(sources)

    if not sources_by_product_id:
        return

    query = sql.SQL(
        """
        INSERT INTO {} (
            product_id,
            schema_version,
            source_relative_path,
            source_digest,
            source_revision,
            created_at,
            updated_at,
            review_status,
            curator,
            source_type,
            source_url,
            source_accessed_at,
            curation_method,
            assistance,
            notes
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
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (product_id)
        DO UPDATE SET
            schema_version = EXCLUDED.schema_version,
            source_relative_path = EXCLUDED.source_relative_path,
            source_digest = EXCLUDED.source_digest,
            source_revision = EXCLUDED.source_revision,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at,
            review_status = EXCLUDED.review_status,
            curator = EXCLUDED.curator,
            source_type = EXCLUDED.source_type,
            source_url = EXCLUDED.source_url,
            source_accessed_at = EXCLUDED.source_accessed_at,
            curation_method = EXCLUDED.curation_method,
            assistance = EXCLUDED.assistance,
            notes = EXCLUDED.notes
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_product_sources",
        )
    )

    parameters = [
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
            Jsonb(list(metadata.notes)),
        )
        for (
            product_id,
            (
                metadata,
                source_revision,
            ),
        ) in sorted(sources_by_product_id.items())
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            parameters,
        )

    persisted_sources = _fetch_futures_product_sources_by_ids(
        connection,
        schema=schema,
        product_ids=tuple(sources_by_product_id),
    )

    missing_product_ids = sources_by_product_id.keys() - persisted_sources.keys()

    if missing_product_ids:
        raise FuturesProductPersistenceError(
            "Futures-product source rows were not present after upsert: "
            f"{sorted(missing_product_ids)!r}"
        )

    for (
        product_id,
        expected_state,
    ) in sources_by_product_id.items():
        persisted_state = persisted_sources[product_id]

        if persisted_state != expected_state:
            raise FuturesProductSourceConflictError(
                "Persisted futures-product source state differs from requested "
                f"state for product_id {product_id!r}: "
                f"persisted={persisted_state!r}, "
                f"requested={expected_state!r}"
            )


def fetch_futures_products_by_ids(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    product_ids: Sequence[str],
) -> dict[str, FuturesProduct]:
    """Return requested persisted futures products keyed by product ID."""

    unique_product_ids = sorted(set(product_ids))

    if not unique_product_ids:
        return {}

    query = sql.SQL(
        """
        SELECT
            product_id,
            asset_class,
            venue,
            description,
            currency,
            unit,
            contract_size,
            valid_period_rule,
            listing_rule,
            period_types,
            settlement,
            last_trading_rule,
            expiry_rule,
            trading_calendar,
            contract_rules,
            trading_hours,
            tick_size,
            tick_value,
            initial_margin,
            maintenance_margin
        FROM {}
        WHERE product_id = ANY(%s::text[])
        ORDER BY product_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_products",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (unique_product_ids,),
    )

    return _futures_products_from_rows(rows)


# ---------------------------------------------------------------------
# PRIVATE FETCH OPERATIONS
# ---------------------------------------------------------------------


def _fetch_futures_product_sources_by_ids(
    connection: Connection[PostgresRow],
    *,
    schema: str,
    product_ids: Sequence[str],
) -> dict[str, FuturesProductSourceState]:
    """Return requested source rows keyed by product ID."""

    unique_product_ids = sorted(set(product_ids))

    if not unique_product_ids:
        return {}

    query = sql.SQL(
        """
        SELECT
            product_id,
            schema_version,
            source_relative_path,
            source_digest,
            source_revision,
            created_at,
            updated_at,
            review_status,
            curator,
            source_type,
            source_url,
            source_accessed_at,
            curation_method,
            assistance,
            notes
        FROM {}
        WHERE product_id = ANY(%s::text[])
        ORDER BY product_id
        """
    ).format(
        sql.Identifier(
            schema,
            "futures_product_sources",
        )
    )

    rows = _fetch_rows(
        connection,
        query,
        (unique_product_ids,),
    )

    return _futures_product_sources_from_rows(rows)


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


# ---------------------------------------------------------------------
# INPUT NORMALISATION
# ---------------------------------------------------------------------


def _normalise_futures_products(
    products: Sequence[FuturesProduct],
) -> dict[str, FuturesProduct]:
    """Return products keyed by ID while rejecting conflicting input."""

    products_by_id: dict[
        str,
        FuturesProduct,
    ] = {}

    for product in products:
        existing_product = products_by_id.get(product.product_id)

        if existing_product is None:
            products_by_id[product.product_id] = product
            continue

        if existing_product != product:
            raise FuturesProductConflictError(
                "Input contains conflicting futures products for "
                f"product_id {product.product_id!r}: "
                f"first={existing_product!r}, "
                f"second={product!r}"
            )

    return products_by_id


def _normalise_futures_product_sources(
    sources: Sequence[FuturesProductSourceWrite],
) -> dict[str, FuturesProductSourceState]:
    """Index source state while rejecting conflicting input."""

    sources_by_product_id: dict[
        str,
        FuturesProductSourceState,
    ] = {}

    product_id_by_source_path: dict[
        str,
        str,
    ] = {}

    for (
        product_id,
        metadata,
        source_revision,
    ) in sources:
        if not product_id:
            raise ValueError("Futures-product source product_id must be non-empty")

        _validate_source_revision(source_revision)

        state: FuturesProductSourceState = (
            metadata,
            source_revision,
        )

        existing_state = sources_by_product_id.get(product_id)

        if existing_state is not None:
            if existing_state != state:
                raise FuturesProductSourceConflictError(
                    "Input contains conflicting futures-product source state "
                    f"for product_id {product_id!r}: "
                    f"first={existing_state!r}, "
                    f"second={state!r}"
                )
        else:
            sources_by_product_id[product_id] = state

        existing_product_id = product_id_by_source_path.get(
            metadata.source_relative_path
        )

        if existing_product_id is not None and existing_product_id != product_id:
            raise FuturesProductSourceConflictError(
                "Input assigns one source_relative_path to multiple products: "
                f"path={metadata.source_relative_path!r}, "
                f"first_product_id={existing_product_id!r}, "
                f"second_product_id={product_id!r}"
            )

        product_id_by_source_path[metadata.source_relative_path] = product_id

    return sources_by_product_id


# ---------------------------------------------------------------------
# FUTURES PRODUCT ROW RECONSTRUCTION
# ---------------------------------------------------------------------


def _futures_products_from_rows(
    rows: Sequence[PostgresRow],
) -> dict[str, FuturesProduct]:
    """Reconstruct products and reject duplicate database identities."""

    products: dict[
        str,
        FuturesProduct,
    ] = {}

    for row in rows:
        product = _futures_product_from_row(row)

        if product.product_id in products:
            raise FuturesProductPersistenceError(
                "Futures-product query returned duplicate product_id "
                f"{product.product_id!r}"
            )

        products[product.product_id] = product

    return products


def _futures_product_from_row(
    row: PostgresRow,
) -> FuturesProduct:
    """Reconstruct one validated operational product from a database row."""

    if len(row) != 20:
        raise FuturesProductPersistenceError(
            f"Futures-product query returned an unexpected row shape: {row!r}"
        )

    product_id = _require_text(
        row[0],
        field="product_id",
    )

    asset_class = _require_text(
        row[1],
        field="asset_class",
    )

    venue = _require_text(
        row[2],
        field="venue",
    )

    description = _require_text(
        row[3],
        field="description",
    )

    currency_text = _require_text(
        row[4],
        field="currency",
    )

    unit_text = _require_text(
        row[5],
        field="unit",
    )

    contract_size = _require_number(
        row[6],
        field="contract_size",
    )

    valid_period_rule = _require_text(
        row[7],
        field="valid_period_rule",
    )

    listing_rule = _require_text(
        row[8],
        field="listing_rule",
    )

    period_types_text = _require_text(
        row[9],
        field="period_types",
    )

    settlement_text = _require_text(
        row[10],
        field="settlement",
    )

    last_trading_rule = _require_text(
        row[11],
        field="last_trading_rule",
    )

    expiry_rule = _require_text(
        row[12],
        field="expiry_rule",
    )

    trading_calendar = _require_text(
        row[13],
        field="trading_calendar",
    )

    contract_rules = _contract_rules_from_json(row[14])

    trading_hours = _optional_text(
        row[15],
        field="trading_hours",
    )

    tick_size = _optional_number(
        row[16],
        field="tick_size",
    )

    tick_value = _optional_number(
        row[17],
        field="tick_value",
    )

    initial_margin = _optional_number(
        row[18],
        field="initial_margin",
    )

    maintenance_margin = _optional_number(
        row[19],
        field="maintenance_margin",
    )

    try:
        currency = Currency[currency_text]
    except KeyError as err:
        raise FuturesProductPersistenceError(
            f"Persisted futures-product currency is not recognised: {currency_text!r}"
        ) from err

    try:
        unit = ProductUnit[unit_text]
    except KeyError as err:
        raise FuturesProductPersistenceError(
            f"Persisted futures-product unit is not recognised: {unit_text!r}"
        ) from err

    try:
        period_types = decode_period_types(period_types_text)
    except (KeyError, ValueError) as err:
        raise FuturesProductPersistenceError(
            "Persisted futures-product period_types are not recognised: "
            f"{period_types_text!r}"
        ) from err

    try:
        settlement = SettlementMethod[settlement_text]
    except KeyError as err:
        raise FuturesProductPersistenceError(
            "Persisted futures-product settlement is not recognised: "
            f"{settlement_text!r}"
        ) from err

    try:
        return FuturesProduct(
            product_id=product_id,
            asset_class=asset_class,
            venue=venue,
            description=description,
            currency=currency,
            unit=unit,
            contract_size=contract_size,
            valid_period_rule=valid_period_rule,
            listing_rule=listing_rule,
            period_types=period_types,
            settlement=settlement,
            last_trading_rule=last_trading_rule,
            expiry_rule=expiry_rule,
            trading_calendar=trading_calendar,
            contract_rules=contract_rules,
            trading_hours=trading_hours,
            tick_size=tick_size,
            tick_value=tick_value,
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
        )
    except ValueError as err:
        raise FuturesProductPersistenceError(
            f"Persisted futures product is invalid: {row!r}"
        ) from err


# ---------------------------------------------------------------------
# SOURCE ROW RECONSTRUCTION
# ---------------------------------------------------------------------


def _futures_product_sources_from_rows(
    rows: Sequence[PostgresRow],
) -> dict[str, FuturesProductSourceState]:
    """Reconstruct source state and reject duplicate database identities."""

    sources: dict[
        str,
        FuturesProductSourceState,
    ] = {}

    source_path_to_product_id: dict[
        str,
        str,
    ] = {}

    for row in rows:
        (
            product_id,
            state,
        ) = _futures_product_source_from_row(row)

        if product_id in sources:
            raise FuturesProductPersistenceError(
                "Futures-product source query returned duplicate product_id "
                f"{product_id!r}"
            )

        metadata = state[0]

        existing_product_id = source_path_to_product_id.get(
            metadata.source_relative_path
        )

        if existing_product_id is not None:
            raise FuturesProductPersistenceError(
                "Futures-product source query returned duplicate "
                "source_relative_path "
                f"{metadata.source_relative_path!r} for product IDs "
                f"{existing_product_id!r} and {product_id!r}"
            )

        sources[product_id] = state

        source_path_to_product_id[metadata.source_relative_path] = product_id

    return sources


def _futures_product_source_from_row(
    row: PostgresRow,
) -> tuple[
    str,
    FuturesProductSourceState,
]:
    """Reconstruct one validated futures-product source row."""

    if len(row) != 15:
        raise FuturesProductPersistenceError(
            f"Futures-product source query returned an unexpected row shape: {row!r}"
        )

    product_id = _require_text(
        row[0],
        field="product_id",
    )

    schema_version = _require_text(
        row[1],
        field="schema_version",
    )

    source_relative_path = _require_text(
        row[2],
        field="source_relative_path",
    )

    source_digest = _require_text(
        row[3],
        field="source_digest",
    )

    source_revision = _require_persisted_source_revision(row[4])

    created_at = _require_date(
        row[5],
        field="created_at",
    )

    updated_at = _require_date(
        row[6],
        field="updated_at",
    )

    review_status = _require_text(
        row[7],
        field="review_status",
    )

    curator = _require_text(
        row[8],
        field="curator",
    )

    source_type = _require_text(
        row[9],
        field="source_type",
    )

    source_url = _require_text(
        row[10],
        field="source_url",
    )

    source_accessed_at = _require_date(
        row[11],
        field="source_accessed_at",
    )

    curation_method = _require_text(
        row[12],
        field="curation_method",
    )

    assistance = _require_text(
        row[13],
        field="assistance",
    )

    notes = _require_string_tuple(
        row[14],
        field="notes",
    )

    try:
        metadata = FuturesProductSourceMetadata(
            schema_version=schema_version,
            source_relative_path=source_relative_path,
            source_digest=source_digest,
            created_at=created_at,
            updated_at=updated_at,
            review_status=review_status,
            curator=curator,
            source_type=source_type,
            source_url=source_url,
            source_accessed_at=source_accessed_at,
            curation_method=curation_method,
            assistance=assistance,
            notes=notes,
        )
    except ValueError as err:
        raise FuturesProductPersistenceError(
            f"Persisted futures-product source metadata is invalid: {row!r}"
        ) from err

    return (
        product_id,
        (
            metadata,
            source_revision,
        ),
    )


# ---------------------------------------------------------------------
# CONTRACT-RULE JSON ENCODING
# ---------------------------------------------------------------------


def _contract_rules_to_json(
    rules: ContractRules,
) -> JSONObj:
    """Encode contract rules into the accepted PostgreSQL JSON representation."""

    last_trading_rule = rules.last_trading_rule

    first_day_of_interest_rule = rules.first_day_of_interest_rule

    shift_rule = first_day_of_interest_rule.shift_rule

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
            "reference_rule": (first_day_of_interest_rule.reference_rule),
        },
    }


# ---------------------------------------------------------------------
# CONTRACT-RULE JSON DECODING
# ---------------------------------------------------------------------


def _contract_rules_from_json(
    value: object,
) -> ContractRules:
    """Decode contract rules from the accepted PostgreSQL JSON representation."""

    data = _require_json_object(
        value,
        context="contract_rules",
    )

    last_trading_data = _require_json_object_field(
        data,
        "last_trading_rule",
        context="contract_rules",
    )

    first_day_data = _require_json_object_field(
        data,
        "first_day_of_interest_rule",
        context="contract_rules",
    )

    shift_data = _require_json_object_field(
        first_day_data,
        "shift_rule",
        context=("contract_rules.first_day_of_interest_rule"),
    )

    reference_event_text = _require_json_text_field(
        last_trading_data,
        "reference_event",
        context=("contract_rules.last_trading_rule"),
    )

    try:
        reference_event = ReferenceEvent(reference_event_text)
    except ValueError as err:
        raise FuturesProductPersistenceError(
            "Persisted contract-rule reference_event is not recognised: "
            f"{reference_event_text!r}"
        ) from err

    weekday_text = _optional_json_text_field(
        last_trading_data,
        "weekday",
        context=("contract_rules.last_trading_rule"),
    )

    if weekday_text is None:
        weekday = None
    else:
        try:
            weekday = Weekday.from_str(weekday_text)
        except ValueError as err:
            raise FuturesProductPersistenceError(
                f"Persisted contract-rule weekday is not recognised: {weekday_text!r}"
            ) from err

    shift_period_type_text = _require_json_text_field(
        shift_data,
        "shift_period_type",
        context=("contract_rules.first_day_of_interest_rule.shift_rule"),
    )

    try:
        shift_period_type = PeriodType[shift_period_type_text]
    except KeyError as err:
        raise FuturesProductPersistenceError(
            "Persisted contract-rule shift_period_type is not recognised: "
            f"{shift_period_type_text!r}"
        ) from err

    n_shift = _require_int_mapping(
        shift_data.get("n_shift"),
        context=("contract_rules.first_day_of_interest_rule.shift_rule.n_shift"),
    )

    try:
        return ContractRules(
            last_trading_rule=LastTradingRule(
                period_offset=_require_json_int_field(
                    last_trading_data,
                    "period_offset",
                    context=("contract_rules.last_trading_rule"),
                ),
                reference_event=reference_event,
                n_reference=_require_json_int_field(
                    last_trading_data,
                    "n_reference",
                    context=("contract_rules.last_trading_rule"),
                ),
                business_day_offset=_require_json_int_field(
                    last_trading_data,
                    "business_day_offset",
                    context=("contract_rules.last_trading_rule"),
                ),
                weekday=weekday,
            ),
            first_day_of_interest_rule=(
                FirstDayOfInterestRule(
                    shift_rule=(
                        FirstDayOfInterestShiftRule(
                            shift_period_type=shift_period_type,
                            n_shift=n_shift,
                        )
                    ),
                    reference_rule=(
                        _require_json_text_field(
                            first_day_data,
                            "reference_rule",
                            context=("contract_rules.first_day_of_interest_rule"),
                        )
                    ),
                )
            ),
        )
    except ValueError as err:
        raise FuturesProductPersistenceError(
            "Persisted contract rules are invalid"
        ) from err


# ---------------------------------------------------------------------
# JSON VALIDATION
# ---------------------------------------------------------------------


def _require_json_object(
    value: object,
    *,
    context: str,
) -> dict[str, object]:
    """Require a JSON object returned from PostgreSQL."""

    if not isinstance(
        value,
        dict,
    ):
        raise FuturesProductPersistenceError(
            f"{context} must be a JSON object, got {value!r}"
        )

    raw_mapping = cast(
        dict[object, object],
        value,
    )

    result: dict[str, object] = {}

    for key, item in raw_mapping.items():
        if not isinstance(
            key,
            str,
        ):
            raise FuturesProductPersistenceError(
                f"{context} must contain only string keys"
            )

        result[key] = item

    return result


def _require_json_object_field(
    data: Mapping[str, object],
    field: str,
    *,
    context: str,
) -> dict[str, object]:
    """Require one nested JSON object field."""

    return _require_json_object(
        data.get(field),
        context=(f"{context}.{field}"),
    )


def _require_json_text_field(
    data: Mapping[str, object],
    field: str,
    *,
    context: str,
) -> str:
    """Require one non-empty text field from a JSON object."""

    value = data.get(field)

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise FuturesProductPersistenceError(
            f"{context}.{field} must be non-empty text, got {value!r}"
        )

    return value


def _optional_json_text_field(
    data: Mapping[str, object],
    field: str,
    *,
    context: str,
) -> str | None:
    """Return one optional text field from a JSON object."""

    value = data.get(field)

    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        raise FuturesProductPersistenceError(
            f"{context}.{field} must be text or null, got {value!r}"
        )

    return value


def _require_json_int_field(
    data: Mapping[str, object],
    field: str,
    *,
    context: str,
) -> int:
    """Require one integer field from a JSON object."""

    value = data.get(field)

    if isinstance(
        value,
        bool,
    ) or not isinstance(
        value,
        int,
    ):
        raise FuturesProductPersistenceError(
            f"{context}.{field} must be an integer, got {value!r}"
        )

    return value


def _require_int_mapping(
    value: object,
    *,
    context: str,
) -> dict[str, int]:
    """Require a JSON string-to-integer mapping."""

    data = _require_json_object(
        value,
        context=context,
    )

    result: dict[
        str,
        int,
    ] = {}

    for (
        key,
        item,
    ) in data.items():
        if isinstance(
            item,
            bool,
        ) or not isinstance(
            item,
            int,
        ):
            raise FuturesProductPersistenceError(
                f"{context}.{key} must be an integer, got {item!r}"
            )

        result[key] = item

    return result


def _require_string_tuple(
    value: object,
    *,
    field: str,
) -> tuple[str, ...]:
    """Require a JSON array containing only strings."""

    if not isinstance(
        value,
        list,
    ):
        raise FuturesProductPersistenceError(
            f"{field} must be a JSON array, got {value!r}"
        )

    raw_items = cast(
        list[object],
        value,
    )

    result: list[str] = []

    for item in raw_items:
        if not isinstance(
            item,
            str,
        ):
            raise FuturesProductPersistenceError(
                f"{field} must contain only strings, got {item!r}"
            )

        result.append(item)

    return tuple(result)


# ---------------------------------------------------------------------
# POSTGRESQL SCALAR VALIDATION
# ---------------------------------------------------------------------


def _require_text(
    value: object,
    *,
    field: str,
) -> str:
    """Require a non-empty PostgreSQL text value."""

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise FuturesProductPersistenceError(
            f"Persisted {field} must be non-empty text, got {value!r}"
        )

    return value


def _optional_text(
    value: object,
    *,
    field: str,
) -> str | None:
    """Require a PostgreSQL text or NULL value."""

    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        raise FuturesProductPersistenceError(
            f"Persisted {field} must be text or NULL, got {value!r}"
        )

    return value


def _require_number(
    value: object,
    *,
    field: str,
) -> float:
    """Require a PostgreSQL numeric value."""

    if isinstance(
        value,
        bool,
    ) or not isinstance(
        value,
        int | float,
    ):
        raise FuturesProductPersistenceError(
            f"Persisted {field} must be numeric, got {value!r}"
        )

    return float(value)


def _optional_number(
    value: object,
    *,
    field: str,
) -> float | None:
    """Require a PostgreSQL numeric or NULL value."""

    if value is None:
        return None

    return _require_number(
        value,
        field=field,
    )


def _require_date(
    value: object,
    *,
    field: str,
) -> date:
    """Require a PostgreSQL date value."""

    if not isinstance(
        value,
        date,
    ):
        raise FuturesProductPersistenceError(
            f"Persisted {field} must be a date, got {value!r}"
        )

    return value


# ---------------------------------------------------------------------
# SOURCE-REVISION VALIDATION
# ---------------------------------------------------------------------


def _validate_source_revision(
    source_revision: str,
) -> None:
    """Validate one caller-provided full lowercase Git revision."""

    if _GIT_REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ValueError(
            "source_revision must be a 40-character lowercase hexadecimal Git revision"
        )


def _require_persisted_source_revision(
    value: object,
) -> str:
    """Require a valid persisted full lowercase Git revision."""

    source_revision = _require_text(
        value,
        field="source_revision",
    )

    if _GIT_REVISION_PATTERN.fullmatch(source_revision) is None:
        raise FuturesProductPersistenceError(
            "Persisted source_revision must be a 40-character lowercase "
            f"hexadecimal Git revision, got {source_revision!r}"
        )

    return source_revision
