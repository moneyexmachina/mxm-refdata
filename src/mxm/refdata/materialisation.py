"""Materialisation routines for MXM reference data.

This module contains the write/build side of the refdata runtime.  It operates
on a protocol instead of importing ``RefData`` directly so that ``runtime.py``
can delegate to these functions without creating circular imports.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase

from mxm.config import MXMConfig
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.factories import (
    FuturesContractFactory,
    FuturesProductFactory,
    PeriodFactory,
)
from mxm.refdata.mappings import (
    futures_contract_to_orm,
    futures_product_from_orm,
    futures_product_to_orm,
    period_from_orm,
    period_to_orm,
)
from mxm.refdata.models import FuturesContract, FuturesProduct, Period, PeriodType
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.period_cycles import CycleInstanceKind
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar

logger = logging.getLogger(__name__)

CYCLE_ID_CALENDAR_MONTHS = "CALENDAR_MONTHS"
CYCLE_ID_CALENDAR_QUARTERS = "CALENDAR_QUARTERS"
CONTRACT_RULE_LOOKBACK_YEARS = 2
CONTRACT_RULE_LOOKAHEAD_YEARS = 1


class RefDataNotInitialisedError(RuntimeError):
    """Raised when refdata is required but DB auto-initialisation is forbidden."""


class RefDataRuntime(Protocol):
    """Protocol required by refdata materialisation functions."""

    config: MXMConfig
    session_manager: SQLSessionManager
    product_factory: FuturesProductFactory
    contract_factory: FuturesContractFactory
    period_factory: PeriodFactory


def build_refdata(refdata: RefDataRuntime) -> None:
    """Build the refdata database without first dropping existing tables."""
    refdata.session_manager.init_db()
    setup_instruments(refdata)


def rebuild_refdata(refdata: RefDataRuntime) -> None:
    """Destructively rebuild the refdata database."""
    logger.warning("Resetting the database. This will delete ALL existing data.")
    refdata.session_manager.drop_db()
    refdata.session_manager.init_db()
    setup_instruments(refdata)
    logger.info("Database successfully rebuilt.")


def ensure_refdata_ready(refdata: RefDataRuntime) -> None:
    """Ensure the refdata database is initialised and populated."""
    if db_has_any_products(refdata.session_manager):
        return

    if refdata.config["REFDATA_DB_MODE"] != "buildable":
        raise RefDataNotInitialisedError(
            "Refdata database is not initialised and auto-creation is forbidden "
            f"(REFDATA_DB_MODE={refdata.config['REFDATA_DB_MODE']!r}). "
            "Initialise refdata explicitly."
        )

    build_refdata(refdata)


def setup_instruments(
    refdata: RefDataRuntime,
    *,
    json_root: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> None:
    """Materialise periods, period cycles, futures products, and contracts."""
    start = start_date or date.fromisoformat(
        refdata.config["REFDATA_CONTRACT_START_DATE"]
    )
    end = end_date or date.fromisoformat(refdata.config["REFDATA_CONTRACT_END_DATE"])

    initialise_periods(refdata, start_date=start, end_date=end)
    initialise_period_cycles(refdata)
    initialise_futures_products(refdata, json_root=json_root)
    initialise_futures_contracts(refdata, start_date=start, end_date=end)


def initialise_futures_products(
    refdata: RefDataRuntime,
    *,
    json_root: str | None = None,
) -> None:
    """Initialise futures products from the configured JSON source."""
    if not is_table_empty(refdata.session_manager, FuturesProductORM):
        raise ValueError("Database already contains products. Run rebuild first.")

    root = json_root or refdata.config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"]
    products = refdata.product_factory.initialise_from_json(root)

    with refdata.session_manager.db_session_scope() as session:
        for product in products:
            session.add(futures_product_to_orm(product))


def initialise_periods(
    refdata: RefDataRuntime,
    *,
    start_date: date,
    end_date: date,
    period_types: list[PeriodType] | None = None,
) -> None:
    """Initialise calendar periods for the requested range."""
    if not is_table_empty(refdata.session_manager, PeriodORM):
        raise ValueError("Database already contains periods. Run rebuild first.")

    selected_period_types = period_types or [
        PeriodType.YEAR,
        PeriodType.QUARTER,
        PeriodType.MONTH,
    ]

    with refdata.session_manager.db_session_scope() as session:
        existing_period_ids = {p.period_id for p in session.query(PeriodORM).all()}

    new_periods: list[Period] = []
    for period_type in selected_period_types:
        generated_periods = refdata.period_factory.get_periods_in_range(
            start_date,
            end_date,
            period_type,
        )
        new_periods.extend(
            period
            for period in generated_periods
            if period.period_id not in existing_period_ids
        )

    with refdata.session_manager.db_session_scope() as session:
        for period in new_periods:
            session.add(period_to_orm(period))


def initialise_period_cycles(refdata: RefDataRuntime) -> None:
    """Initialise canonical period cycles and cycle memberships."""
    has_cycles = not is_table_empty(refdata.session_manager, PeriodCycleORM)
    has_memberships = not is_table_empty(
        refdata.session_manager, PeriodCycleMembershipORM
    )

    if has_cycles or has_memberships:
        raise ValueError("Database already contains period cycles. Run rebuild first.")

    with refdata.session_manager.db_session_scope() as session:
        session.add_all(
            [
                PeriodCycleORM(
                    cycle_id=CYCLE_ID_CALENDAR_MONTHS,
                    name="Calendar Months",
                    period_type=PeriodType.MONTH.name,
                    instance_kind=CycleInstanceKind.YEAR.value,
                    cycle_size=12,
                ),
                PeriodCycleORM(
                    cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
                    name="Calendar Quarters",
                    period_type=PeriodType.QUARTER.name,
                    instance_kind=CycleInstanceKind.YEAR.value,
                    cycle_size=4,
                ),
            ]
        )

        periods = (
            session.query(PeriodORM)
            .filter(
                PeriodORM.period_type.in_(
                    [PeriodType.MONTH.name, PeriodType.QUARTER.name]
                )
            )
            .all()
        )

        memberships: list[PeriodCycleMembershipORM] = []
        for period in periods:
            year = period.first_date.year
            month = period.first_date.month

            if period.period_type == PeriodType.MONTH:
                memberships.append(
                    PeriodCycleMembershipORM(
                        cycle_id=CYCLE_ID_CALENDAR_MONTHS,
                        period_id=period.period_id,
                        cycle_instance=year,
                        cycle_element=month,
                    )
                )
            elif period.period_type == PeriodType.QUARTER:
                memberships.append(
                    PeriodCycleMembershipORM(
                        cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
                        period_id=period.period_id,
                        cycle_instance=year,
                        cycle_element=((month - 1) // 3) + 1,
                    )
                )

        session.add_all(memberships)


def initialise_futures_contracts(
    refdata: RefDataRuntime,
    *,
    start_date: date,
    end_date: date,
) -> None:
    """Initialise futures contracts from stored products and periods."""
    with refdata.session_manager.db_session_scope() as session:
        products = [
            futures_product_from_orm(product_orm)
            for product_orm in session.query(FuturesProductORM).all()
        ]

    if not products:
        raise ValueError(
            "No products found in the database. Run initialise_futures_products first."
        )

    validate_calendar_coverage_for_contract_initialisation(
        products=products,
        start_date=start_date,
        end_date=end_date,
    )

    with refdata.session_manager.db_session_scope() as session:
        periods = {
            period_orm.period_id: period_from_orm(period_orm)
            for period_orm in session.query(PeriodORM)
            .filter(
                PeriodORM.first_date >= start_date,
                PeriodORM.last_date <= end_date,
            )
            .all()
        }

    if not periods:
        raise ValueError(
            "No periods found in the database. Run initialise_periods first."
        )

    contracts: list[FuturesContract] = []
    for product in products:
        contracts.extend(
            refdata.contract_factory.create_contracts_for_product(product, periods)
        )

    with refdata.session_manager.db_session_scope() as session:
        for contract in contracts:
            session.add(futures_contract_to_orm(contract=contract))


def is_table_empty(
    session_manager: SQLSessionManager,
    orm_model: type[DeclarativeBase],
) -> bool:
    """Return whether an ORM table is empty."""
    with session_manager.db_session_scope() as session:
        return session.query(orm_model).count() == 0


def db_has_any_products(session_manager: SQLSessionManager) -> bool:
    """Return whether the configured database contains any futures products."""
    try:
        with session_manager.db_session_scope() as session:
            return session.query(FuturesProductORM).limit(1).first() is not None
    except SQLAlchemyError:
        return False


def validate_calendar_coverage_for_contract_initialisation(
    *,
    products: list[FuturesProduct],
    start_date: date,
    end_date: date,
) -> None:
    """Validate trading-calendar coverage for contract materialisation."""
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
        calendar = TradingCalendar(product.trading_calendar)
        calendar.ensure_range_in_coverage(required_start, required_end)
