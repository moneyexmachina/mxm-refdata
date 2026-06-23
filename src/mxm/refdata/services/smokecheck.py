"""Operational smoke checks for the materialised mxm-refdata database."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.mappings import (
    futures_contract_from_orm,
    futures_product_from_orm,
    period_from_orm,
)
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.utils.period_types_codec import decode_period_types

CYCLE_ID_CALENDAR_MONTHS = "CALENDAR_MONTHS"
CYCLE_ID_CALENDAR_QUARTERS = "CALENDAR_QUARTERS"

type SmokeCheckStatus = Literal["pass", "fail"]


class SmokeCheckFailed(Exception):
    """Raised when an individual smoke check fails."""


@dataclass(frozen=True)
class RefDataCounts:
    """Row counts for the materialised refdata database."""

    products: int
    periods: int
    contracts: int
    cycles: int
    memberships: int


@dataclass(frozen=True)
class SmokeCheckResult:
    """Result of one smoke check."""

    name: str
    status: SmokeCheckStatus
    message: str = ""


@dataclass(frozen=True)
class SmokeCheckReport:
    """Aggregate smoke-check report."""

    counts: RefDataCounts
    results: list[SmokeCheckResult]

    @property
    def passed(self) -> bool:
        """Return True if all smoke checks passed."""
        return all(result.status == "pass" for result in self.results)


type SmokeCheck = Callable[[Session], None]


def _fail(message: str) -> None:
    raise SmokeCheckFailed(message)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _pick_first[T](iterable: Iterable[T]) -> T | None:
    for item in iterable:
        return item
    return None


def count_refdata_rows(session: Session) -> RefDataCounts:
    """Count key materialised refdata tables."""
    return RefDataCounts(
        products=session.query(FuturesProductORM).count(),
        periods=session.query(PeriodORM).count(),
        contracts=session.query(FuturesContractORM).count(),
        cycles=session.query(PeriodCycleORM).count(),
        memberships=session.query(PeriodCycleMembershipORM).count(),
    )


def smoke_check_non_empty_core_tables(session: Session) -> None:
    """Verify that products, periods, and contracts are populated."""
    counts = count_refdata_rows(session)

    _assert(counts.products > 0, "No products inserted.")
    _assert(counts.periods > 0, "No periods inserted.")
    _assert(counts.contracts > 0, "No contracts inserted.")


def smoke_check_roundtrip_period_types(session: Session) -> None:
    """Verify period_types storage and ORM/domain round-trip semantics."""
    product_orm = _pick_first(session.query(FuturesProductORM).limit(1).all())
    if product_orm is None:
        raise SmokeCheckFailed("No products found.")

    decoded = decode_period_types(product_orm.period_types)
    product = futures_product_from_orm(product_orm)

    _assert(
        product.period_types == decoded,
        "Domain period_types does not match decoded ORM value.",
    )


def smoke_check_contract_date_types(session: Session) -> None:
    """Verify contract date fields map correctly into the domain model."""
    contract_orm = _pick_first(session.query(FuturesContractORM).limit(1).all())

    if contract_orm is None:
        raise SmokeCheckFailed("No contracts found.")

    contract = futures_contract_from_orm(contract_orm)

    _assert(
        contract.first_day_of_interest == contract_orm.first_day_of_interest,
        "Domain first_day_of_interest does not match ORM value.",
    )
    _assert(
        contract.last_trading_day == contract_orm.last_trading_day,
        "Domain last_trading_day does not match ORM value.",
    )


def smoke_check_contracts_periods_coherence(session: Session) -> None:
    """Verify contracts reference periods and period-type filtering is feasible."""
    product_id = _pick_first(
        product_id
        for (product_id,) in session.query(FuturesContractORM.product_id)
        .distinct()
        .limit(1)
        .all()
    )
    _assert(product_id is not None, "No product_id found in contracts table.")

    contracts_orm = (
        session.query(FuturesContractORM)
        .filter(FuturesContractORM.product_id == product_id)
        .order_by(FuturesContractORM.contract_id.asc())
        .all()
    )
    _assert(
        len(contracts_orm) > 0,
        f"No contracts found for product_id={product_id!r}.",
    )

    contracts = [futures_contract_from_orm(contract) for contract in contracts_orm]
    periods = {p.period_id: period_from_orm(p) for p in session.query(PeriodORM).all()}

    period_types = [
        periods[contract.period_id].period_type
        for contract in contracts
        if contract.period_id in periods
    ]

    _assert(
        len(period_types) > 0,
        "Could not resolve period types for contracts via periods table.",
    )

    chosen = _pick_first(sorted(set(period_types), key=lambda item: item.value))
    _assert(chosen is not None, "No period types found for product contracts.")

    subset = [
        contract
        for contract in contracts
        if periods[contract.period_id].period_type == chosen
    ]
    _assert(
        0 < len(subset) <= len(contracts),
        "Filtering by period_type should yield a non-empty subset.",
    )


def smoke_check_period_cycles_present(session: Session) -> None:
    """Verify canonical calendar cycles exist and have memberships."""
    cycle_ids = {
        cycle_id for (cycle_id,) in session.query(PeriodCycleORM.cycle_id).all()
    }

    _assert(CYCLE_ID_CALENDAR_MONTHS in cycle_ids, "Missing cycle CALENDAR_MONTHS.")
    _assert(CYCLE_ID_CALENDAR_QUARTERS in cycle_ids, "Missing cycle CALENDAR_QUARTERS.")

    month_memberships = (
        session.query(PeriodCycleMembershipORM)
        .filter(PeriodCycleMembershipORM.cycle_id == CYCLE_ID_CALENDAR_MONTHS)
        .count()
    )
    quarter_memberships = (
        session.query(PeriodCycleMembershipORM)
        .filter(PeriodCycleMembershipORM.cycle_id == CYCLE_ID_CALENDAR_QUARTERS)
        .count()
    )

    _assert(month_memberships > 0, "No memberships for CALENDAR_MONTHS.")
    _assert(quarter_memberships > 0, "No memberships for CALENDAR_QUARTERS.")


def smoke_check_period_cycle_membership_uniqueness(session: Session) -> None:
    """Verify canonical cycle membership keys are unique."""
    duplicates = (
        session.query(
            PeriodCycleMembershipORM.cycle_id,
            PeriodCycleMembershipORM.cycle_instance,
            PeriodCycleMembershipORM.cycle_element,
            func.count().label("n"),
        )
        .group_by(
            PeriodCycleMembershipORM.cycle_id,
            PeriodCycleMembershipORM.cycle_instance,
            PeriodCycleMembershipORM.cycle_element,
        )
        .having(func.count() > 1)
        .limit(1)
        .all()
    )

    _assert(not duplicates, f"Duplicate cycle membership keys found: {duplicates!r}")


def smoke_check_calendar_month_mapping(session: Session) -> None:
    """Spot-check that December periods map to calendar month element 12."""
    expected_month = 12
    membership = (
        session.query(PeriodCycleMembershipORM)
        .filter(
            PeriodCycleMembershipORM.cycle_id == CYCLE_ID_CALENDAR_MONTHS,
            PeriodCycleMembershipORM.cycle_element == expected_month,
        )
        .limit(1)
        .one_or_none()
    )
    if membership is None:
        raise SmokeCheckFailed(
            f"No month membership found for element={expected_month}."
        )

    period = (
        session.query(PeriodORM)
        .filter(PeriodORM.period_id == membership.period_id)
        .one_or_none()
    )
    if period is None:
        raise SmokeCheckFailed(
            f"Membership references missing Period: {membership.period_id!r}"
        )

    _assert(
        period.period_type == PeriodType.MONTH,
        f"Expected mapped period_type MONTH, got {period.period_type!r}.",
    )
    _assert(
        period.first_date.month == expected_month,
        f"Expected Period.first_date.month={expected_month}, "
        f"got {period.first_date.month}.",
    )


SMOKE_CHECKS: tuple[tuple[str, SmokeCheck], ...] = (
    ("core tables populated", smoke_check_non_empty_core_tables),
    ("period_types storage + round-trip", smoke_check_roundtrip_period_types),
    ("contract date field types", smoke_check_contract_date_types),
    (
        "contracts/periods coherence + filterability",
        smoke_check_contracts_periods_coherence,
    ),
    (
        "period cycles present + non-empty memberships",
        smoke_check_period_cycles_present,
    ),
    (
        "period cycle membership uniqueness",
        smoke_check_period_cycle_membership_uniqueness,
    ),
    ("calendar month mapping spot-check", smoke_check_calendar_month_mapping),
)


def run_smokechecks(session_manager: SQLSessionManager) -> SmokeCheckReport:
    """Run operational smoke checks against the materialised refdata database."""

    with session_manager.db_session_scope() as session:
        counts = count_refdata_rows(session)
        results: list[SmokeCheckResult] = []

        for name, check in SMOKE_CHECKS:
            try:
                check(session)
            except SmokeCheckFailed as err:
                results.append(
                    SmokeCheckResult(
                        name=name,
                        status="fail",
                        message=str(err),
                    )
                )
            else:
                results.append(
                    SmokeCheckResult(
                        name=name,
                        status="pass",
                    )
                )

    return SmokeCheckReport(counts=counts, results=results)
