"""Materialisation capability for MXM reference data.

This module owns construction and persistence of the complete desired
reference-data state.

Desired state is constructed entirely before PostgreSQL is modified. The
resulting periods, cycles, products, source provenance, and futures contracts
are then persisted through the plain-SQL boundary in one data transaction.

Schema migration is deliberately separate from data materialisation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psycopg import sql

from mxm.config import MXMConfig
from mxm.refdata.generation.futures_contracts import (
    generate_futures_contracts,
)
from mxm.refdata.generation.periods import generate_periods
from mxm.refdata.models import (
    FuturesContract,
    FuturesProduct,
    Period,
    PeriodType,
)
from mxm.refdata.models.period_cycles import (
    CycleInstanceKind,
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.sources.futures_product import (
    FuturesProductSourceMetadata,
    load_futures_products,
    resolve_futures_product_source_revision,
)
from mxm.refdata.sql.futures_contracts import insert_futures_contracts
from mxm.refdata.sql.futures_products import (
    insert_futures_products,
    upsert_futures_product_sources,
)
from mxm.refdata.sql.migration_runner import MigrationRunner
from mxm.refdata.sql.period_cycles import (
    insert_period_cycle_memberships,
    insert_period_cycles,
)
from mxm.refdata.sql.periods import insert_periods
from mxm.refdata.sql.postgres import PostgresDatabase
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar

logger = logging.getLogger(__name__)

CYCLE_ID_CALENDAR_MONTHS = "CALENDAR_MONTHS"
CYCLE_ID_CALENDAR_QUARTERS = "CALENDAR_QUARTERS"

CONTRACT_RULE_LOOKBACK_YEARS = 2
CONTRACT_RULE_LOOKAHEAD_YEARS = 1

_DEFAULT_PERIOD_TYPES = (
    PeriodType.YEAR,
    PeriodType.QUARTER,
    PeriodType.MONTH,
)

_PROTECTED_SCHEMA_NAMES = frozenset(
    {
        "public",
        "pg_catalog",
        "information_schema",
    }
)

type FuturesProductSourceMetadataEntry = tuple[
    str,
    FuturesProductSourceMetadata,
]


@dataclass(frozen=True)
class _RefDataDesiredState:
    """Complete immutable reference-data state ready for persistence."""

    periods: tuple[Period, ...]
    period_cycles: tuple[PeriodCycle, ...]
    period_cycle_memberships: tuple[PeriodCycleMembership, ...]

    futures_products: tuple[FuturesProduct, ...]
    futures_product_source_metadata: tuple[FuturesProductSourceMetadataEntry, ...]
    futures_product_source_revision: str

    futures_contracts: tuple[FuturesContract, ...]


def build_refdata(
    *,
    config: MXMConfig,
    database: PostgresDatabase,
) -> None:
    """Materialise configured reference data non-destructively.

    Desired state is fully constructed and validated before PostgreSQL is
    modified.

    Packaged schema migrations are applied before data materialisation. The
    complete desired data state is subsequently persisted in one transaction.

    Existing identical operational state is accepted idempotently. Conflicting
    operational state raises through the persistence boundary and causes the
    complete materialisation transaction to roll back.

    Source provenance may evolve while the operational product definition
    remains unchanged.
    """

    desired_state = _build_desired_state(
        config=config,
    )

    MigrationRunner(database).migrate()

    _persist_desired_state(
        database=database,
        desired_state=desired_state,
    )


def rebuild_refdata(
    *,
    config: MXMConfig,
    database: PostgresDatabase,
) -> None:
    """Destructively rematerialise the owned reference-data schema.

    Desired state is constructed and validated before the existing schema is
    touched.

    Rebuild drops only the PostgreSQL schema explicitly owned by ``database``.
    It never drops the PostgreSQL database itself.

    Packaged migrations then recreate the schema before the complete desired
    data state is persisted.
    """

    desired_state = _build_desired_state(
        config=config,
    )

    logger.warning(
        "Rebuilding reference data by dropping PostgreSQL schema %r.",
        database.schema,
    )

    _drop_owned_schema(database)

    MigrationRunner(database).migrate()

    _persist_desired_state(
        database=database,
        desired_state=desired_state,
    )

    logger.info(
        "Reference-data schema %r successfully rebuilt.",
        database.schema,
    )


def _build_desired_state(
    *,
    config: MXMConfig,
) -> _RefDataDesiredState:
    """Construct complete desired state without database access."""

    source_root = Path(
        _require_config_text(
            config,
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT",
        )
    )

    start_date = _require_config_date(
        config,
        "REFDATA_CONTRACT_START_DATE",
    )
    end_date = _require_config_date(
        config,
        "REFDATA_CONTRACT_END_DATE",
    )

    if start_date > end_date:
        raise ValueError(
            "Reference-data contract start date must not be after end date: "
            f"{start_date!r} > {end_date!r}"
        )

    source_records = load_futures_products(
        source_root,
    )

    futures_products = tuple(record.product for record in source_records)

    futures_product_source_metadata = tuple(
        (
            record.product.product_id,
            record.metadata,
        )
        for record in source_records
    )

    futures_product_source_revision = resolve_futures_product_source_revision(
        source_root,
    )

    periods = tuple(
        generate_periods(
            start_date=start_date,
            end_date=end_date,
            period_types=_DEFAULT_PERIOD_TYPES,
        )
    )

    (
        period_cycles,
        period_cycle_memberships,
    ) = _build_period_cycle_state(periods)

    validate_calendar_coverage_for_contract_initialisation(
        products=futures_products,
        start_date=start_date,
        end_date=end_date,
    )

    futures_contracts = tuple(
        contract
        for product in futures_products
        for contract in generate_futures_contracts(
            product=product,
            periods=periods,
        )
    )

    return _RefDataDesiredState(
        periods=periods,
        period_cycles=period_cycles,
        period_cycle_memberships=period_cycle_memberships,
        futures_products=futures_products,
        futures_product_source_metadata=(futures_product_source_metadata),
        futures_product_source_revision=(futures_product_source_revision),
        futures_contracts=futures_contracts,
    )


def _build_period_cycle_state(
    periods: tuple[Period, ...],
) -> tuple[
    tuple[PeriodCycle, ...],
    tuple[PeriodCycleMembership, ...],
]:
    """Construct canonical calendar cycles and their memberships."""

    cycles = (
        PeriodCycle(
            cycle_id=CYCLE_ID_CALENDAR_MONTHS,
            name="Calendar Months",
            period_type=PeriodType.MONTH,
            cycle_size=12,
            instance_kind=CycleInstanceKind.YEAR,
        ),
        PeriodCycle(
            cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
            name="Calendar Quarters",
            period_type=PeriodType.QUARTER,
            cycle_size=4,
            instance_kind=CycleInstanceKind.YEAR,
        ),
    )

    memberships: list[PeriodCycleMembership] = []

    for period in periods:
        if period.period_type is PeriodType.MONTH:
            memberships.append(
                PeriodCycleMembership(
                    cycle_id=CYCLE_ID_CALENDAR_MONTHS,
                    period_id=period.period_id,
                    cycle_instance=period.first_date.year,
                    cycle_element=period.first_date.month,
                )
            )
            continue

        if period.period_type is PeriodType.QUARTER:
            memberships.append(
                PeriodCycleMembership(
                    cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
                    period_id=period.period_id,
                    cycle_instance=period.first_date.year,
                    cycle_element=(((period.first_date.month - 1) // 3) + 1),
                )
            )

    return (
        cycles,
        tuple(memberships),
    )


def _persist_desired_state(
    *,
    database: PostgresDatabase,
    desired_state: _RefDataDesiredState,
) -> None:
    """Persist complete desired data state in one PostgreSQL transaction."""

    schema = database.schema

    with database.transaction() as connection:
        insert_periods(
            connection,
            schema=schema,
            periods=desired_state.periods,
        )

        insert_period_cycles(
            connection,
            schema=schema,
            period_cycles=desired_state.period_cycles,
        )

        insert_period_cycle_memberships(
            connection,
            schema=schema,
            memberships=desired_state.period_cycle_memberships,
        )

        insert_futures_products(
            connection,
            schema=schema,
            products=desired_state.futures_products,
        )

        upsert_futures_product_sources(
            connection,
            schema=schema,
            sources=[
                (
                    product_id,
                    metadata,
                    desired_state.futures_product_source_revision,
                )
                for (
                    product_id,
                    metadata,
                ) in desired_state.futures_product_source_metadata
            ],
        )

        insert_futures_contracts(
            connection,
            schema=schema,
            contracts=desired_state.futures_contracts,
        )


def _drop_owned_schema(
    database: PostgresDatabase,
) -> None:
    """Drop only the explicitly configured reference-data schema."""

    schema = database.schema

    if not schema:
        raise ValueError(
            "Refusing to rebuild reference data with an empty schema name."
        )

    if schema in _PROTECTED_SCHEMA_NAMES:
        raise ValueError(f"Refusing to rebuild protected PostgreSQL schema {schema!r}.")

    query = sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))

    with database.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)


def validate_calendar_coverage_for_contract_initialisation(
    *,
    products: tuple[FuturesProduct, ...],
    start_date: date,
    end_date: date,
) -> None:
    """Validate trading-calendar coverage required by contract generation."""

    required_start = date(
        start_date.year - CONTRACT_RULE_LOOKBACK_YEARS,
        start_date.month,
        start_date.day,
    )

    required_end = date(
        end_date.year + CONTRACT_RULE_LOOKAHEAD_YEARS,
        end_date.month,
        end_date.day,
    )

    for product in products:
        calendar = TradingCalendar(
            product.trading_calendar,
        )

        calendar.ensure_range_in_coverage(
            required_start,
            required_end,
        )


def _require_config_text(
    config: MXMConfig,
    key: str,
) -> str:
    """Return a required non-empty text configuration value."""

    value = config[key]

    if not isinstance(value, str) or not value:
        raise ValueError(
            f"Reference-data configuration {key!r} must be non-empty text, "
            f"got {value!r}"
        )

    return value


def _require_config_date(
    config: MXMConfig,
    key: str,
) -> date:
    """Return a required ISO-date configuration value."""

    value = _require_config_text(
        config,
        key,
    )

    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise ValueError(
            f"Reference-data configuration {key!r} must be an ISO date, got {value!r}"
        ) from err
