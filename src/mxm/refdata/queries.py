"""Read/query routines for MXM reference data."""

from __future__ import annotations

from datetime import date
from typing import Protocol, TypeGuard, cast

from mxm.config import MXMConfig
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.mappings import (
    futures_contract_from_orm,
    futures_product_from_orm,
    period_cycle_from_orm,
    period_cycle_membership_from_orm,
    period_from_orm,
)
from mxm.refdata.materialisation import (
    RefDataNotInitialisedError,
    db_has_any_products,
)
from mxm.refdata.models import FuturesContract, FuturesProduct, Period, PeriodType
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.period_cycles import PeriodCycle, PeriodCycleMembership
from mxm.refdata.utils.cache_manager import CacheManager


def check_refdata_ready(refdata: RefDataRuntime) -> None:
    """Verify that refdata is initialised before running read queries."""
    if db_has_any_products(refdata.session_manager):
        return

    raise RefDataNotInitialisedError(
        "Refdata database is not initialised. "
        "Build refdata explicitly before running read queries."
    )


class RefDataLookupError(KeyError):
    """Raised when a required reference-data object cannot be found."""


class RefDataRuntime(Protocol):
    config: MXMConfig
    session_manager: SQLSessionManager
    cache: CacheManager[object]


def maybe_get_contract_by_id(
    refdata: RefDataRuntime,
    contract_id: str,
) -> FuturesContract | None:
    """Retrieve a futures contract by contract ID, if available."""
    check_refdata_ready(refdata)

    cache_key = f"contract:{contract_id}"
    cached = refdata.cache.get_as(cache_key, FuturesContract)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        contract = (
            session.query(FuturesContractORM).filter_by(contract_id=contract_id).first()
        )
        if contract is None:
            return None

        result = futures_contract_from_orm(contract)

    refdata.cache.set(cache_key, result)
    return result


def get_contract_by_id(
    refdata: RefDataRuntime,
    contract_id: str,
) -> FuturesContract:
    """Retrieve a futures contract by contract ID, enforcing existence."""
    contract = maybe_get_contract_by_id(refdata, contract_id)

    if contract is None:
        raise RefDataLookupError(
            f"FuturesContract not found for contract_id='{contract_id}'. "
            "This indicates missing or incomplete reference data."
        )

    return contract


def is_futures_contract_list(value: object) -> TypeGuard[list[FuturesContract]]:
    """Return whether a value is a list of FuturesContract objects."""
    if not isinstance(value, list):
        return False

    items = cast(list[object], value)

    return all(isinstance(item, FuturesContract) for item in items)


def get_contracts_by_id(
    refdata: RefDataRuntime,
    contract_ids: list[str],
) -> list[FuturesContract]:
    """Retrieve futures contracts by ID, preserving input order."""
    check_refdata_ready(refdata)

    if not contract_ids:
        return []

    ordered_ids = list(contract_ids)
    unique_ids = list(dict.fromkeys(contract_ids))

    cache_key = f"contracts:ids:{','.join(unique_ids)}"
    cached = refdata.cache.get_checked(cache_key, is_futures_contract_list)
    if cached is not None:
        by_id: dict[str, FuturesContract] = {
            contract.contract_id: contract for contract in cached
        }
        return [
            by_id[contract_id] for contract_id in ordered_ids if contract_id in by_id
        ]

    with refdata.session_manager.db_session_scope() as session:
        contract_rows = (
            session.query(FuturesContractORM)
            .filter(FuturesContractORM.contract_id.in_(unique_ids))
            .all()
        )
        contracts: list[FuturesContract] = [
            futures_contract_from_orm(contract) for contract in contract_rows
        ]

    refdata.cache.set(cache_key, contracts)

    by_id: dict[str, FuturesContract] = {
        contract.contract_id: contract for contract in contracts
    }
    return [by_id[contract_id] for contract_id in ordered_ids if contract_id in by_id]


def get_active_contracts(
    refdata: RefDataRuntime,
    as_of_date: date,
    *,
    product_id: str | None = None,
    product_ids: list[str] | None = None,
) -> list[FuturesContract]:
    """Retrieve contracts active on a given date."""
    check_refdata_ready(refdata)

    if product_id is not None and product_ids is not None:
        raise ValueError("Provide only one of product_id or product_ids, not both.")

    pid_part = (
        f"pid:{product_id}"
        if product_id is not None
        else (
            f"pids:{','.join(sorted(product_ids))}"
            if product_ids is not None
            else "pid:ALL"
        )
    )
    cache_key = f"active_contracts:{as_of_date.isoformat()}:{pid_part}"

    cached = refdata.cache.get_checked(cache_key, is_futures_contract_list)
    if cached is not None:
        return cached
    with refdata.session_manager.db_session_scope() as session:
        query = session.query(FuturesContractORM).filter(
            FuturesContractORM.first_day_of_interest <= as_of_date,
            FuturesContractORM.last_trading_day >= as_of_date,
        )

        if product_id is not None:
            query = query.filter(FuturesContractORM.product_id == product_id)
        elif product_ids is not None:
            if not product_ids:
                return []
            query = query.filter(FuturesContractORM.product_id.in_(product_ids))

        contract_rows = query.order_by(
            FuturesContractORM.product_id.asc(),
            FuturesContractORM.last_trading_day.asc(),
            FuturesContractORM.contract_id.asc(),
        ).all()
        contracts = [futures_contract_from_orm(contract) for contract in contract_rows]

    refdata.cache.set(cache_key, contracts)
    return contracts


def is_futures_product_list(value: object) -> TypeGuard[list[FuturesProduct]]:
    """Return whether a value is a list of FuturesProduct objects."""
    if not isinstance(value, list):
        return False

    items = cast(list[object], value)
    return all(isinstance(item, FuturesProduct) for item in items)


def get_all_products(refdata: RefDataRuntime) -> list[FuturesProduct]:
    """Retrieve all futures products."""
    check_refdata_ready(refdata)

    cache_key = "all_products"
    cached = refdata.cache.get_checked(cache_key, is_futures_product_list)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        product_rows = session.query(FuturesProductORM).all()
        products: list[FuturesProduct] = [
            futures_product_from_orm(product) for product in product_rows
        ]

    refdata.cache.set(cache_key, products)
    return products


def get_product_by_id(
    refdata: RefDataRuntime,
    product_id: str,
) -> FuturesProduct:
    """Retrieve a futures product by product ID, enforcing existence."""
    check_refdata_ready(refdata)

    cache_key = f"product:{product_id}"
    cached = refdata.cache.get(cache_key)
    if isinstance(cached, FuturesProduct):
        return cached

    with refdata.session_manager.db_session_scope() as session:
        product = (
            session.query(FuturesProductORM).filter_by(product_id=product_id).first()
        )
        if product is None:
            raise RefDataLookupError(
                f"FuturesProduct not found for product_id='{product_id}'. "
                "This indicates missing or incomplete reference data."
            )

        result = futures_product_from_orm(product)

    refdata.cache.set(cache_key, result)
    return result


def get_contracts_for_product(
    refdata: RefDataRuntime,
    product_id: str,
    *,
    period_type: PeriodType | str | None = None,
) -> list[FuturesContract]:
    """Retrieve all contracts for a futures product."""
    check_refdata_ready(refdata)

    resolved_period_type = resolve_period_type(period_type)
    cache_key = (
        f"contracts_for_product:{product_id}:"
        f"period_type={resolved_period_type.value if resolved_period_type else '*'}"
    )

    cached = refdata.cache.get_checked(cache_key, is_futures_contract_list)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        contract_rows = (
            session.query(FuturesContractORM).filter_by(product_id=product_id).all()
        )
        contracts = [futures_contract_from_orm(contract) for contract in contract_rows]

    if not contracts:
        refdata.cache.set(cache_key, [])
        return []

    periods = get_periods_by_id(
        refdata,
        [contract.period_id for contract in contracts],
    )
    period_by_id = {period.period_id: period for period in periods}

    filtered_contracts = [
        contract for contract in contracts if contract.period_id in period_by_id
    ]

    if resolved_period_type is not None:
        filtered_contracts = [
            contract
            for contract in filtered_contracts
            if period_by_id[contract.period_id].period_type == resolved_period_type
        ]

    result = sorted(
        filtered_contracts,
        key=lambda contract: (
            period_by_id[contract.period_id],
            contract.contract_id,
        ),
    )
    refdata.cache.set(cache_key, result)
    return result


def get_contracts_for_date(
    refdata: RefDataRuntime,
    target_date: date,
) -> list[FuturesContract]:
    """Retrieve contracts whose delivery period contains a given date."""
    check_refdata_ready(refdata)

    cache_key = f"contracts_for_date:{target_date.isoformat()}"
    cached = refdata.cache.get(cache_key)

    cached = refdata.cache.get_checked(cache_key, is_futures_contract_list)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        contract_rows = (
            session.query(FuturesContractORM)
            .join(PeriodORM, FuturesContractORM.period_id == PeriodORM.period_id)
            .filter(
                PeriodORM.first_date <= target_date,
                PeriodORM.last_date >= target_date,
            )
            .all()
        )
        contracts = [futures_contract_from_orm(contract) for contract in contract_rows]

    refdata.cache.set(cache_key, contracts)
    return contracts


def is_period_list(value: object) -> TypeGuard[list[Period]]:
    """Return whether a value is a list of Period objects."""
    if not isinstance(value, list):
        return False

    items = cast(list[object], value)
    return all(isinstance(item, Period) for item in items)


def get_periods(refdata: RefDataRuntime) -> list[Period]:
    """Retrieve all available periods."""
    check_refdata_ready(refdata)

    cache_key = "all_periods"
    cached = refdata.cache.get_checked(cache_key, is_period_list)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        period_rows = session.query(PeriodORM).all()
        periods: list[Period] = [period_from_orm(period) for period in period_rows]

    refdata.cache.set(cache_key, periods)
    return periods


def get_period_by_id(
    refdata: RefDataRuntime,
    period_id: str,
) -> Period | None:
    """Retrieve a period by period ID, if present."""
    check_refdata_ready(refdata)

    cache_key = f"period:{period_id}"
    cached = refdata.cache.get(cache_key)
    if isinstance(cached, Period):
        return cached

    with refdata.session_manager.db_session_scope() as session:
        period = session.query(PeriodORM).filter_by(period_id=period_id).first()
        if period is None:
            return None

        result = period_from_orm(period)

    refdata.cache.set(cache_key, result)
    return result


def get_periods_by_id(
    refdata: RefDataRuntime,
    period_ids: list[str],
) -> list[Period]:
    """Retrieve periods by period ID, preserving input order."""
    check_refdata_ready(refdata)

    if not period_ids:
        return []

    ordered_ids = list(period_ids)
    unique_ids = list(dict.fromkeys(period_ids))

    cache_key = f"periods:ids:{','.join(unique_ids)}"
    cached = refdata.cache.get_checked(cache_key, is_period_list)
    if cached is not None:
        by_id = {period.period_id: period for period in cached}
        return [by_id[period_id] for period_id in ordered_ids if period_id in by_id]

    with refdata.session_manager.db_session_scope() as session:
        period_rows = (
            session.query(PeriodORM).filter(PeriodORM.period_id.in_(unique_ids)).all()
        )
        periods = [period_from_orm(period) for period in period_rows]

    refdata.cache.set(cache_key, periods)

    by_id = {period.period_id: period for period in periods}
    return [by_id[period_id] for period_id in ordered_ids if period_id in by_id]


def is_period_cycle_list(value: object) -> TypeGuard[list[PeriodCycle]]:
    """Return whether a value is a list of PeriodCycle objects."""
    if not isinstance(value, list):
        return False

    items = cast(list[object], value)
    return all(isinstance(item, PeriodCycle) for item in items)


def get_cycles(refdata: RefDataRuntime) -> list[PeriodCycle]:
    """Retrieve all available period cycles."""
    check_refdata_ready(refdata)

    cache_key = "all_period_cycles"
    cached = refdata.cache.get_checked(cache_key, is_period_cycle_list)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        cycle_rows = (
            session.query(PeriodCycleORM).order_by(PeriodCycleORM.cycle_id.asc()).all()
        )
        cycles: list[PeriodCycle] = [
            period_cycle_from_orm(cycle) for cycle in cycle_rows
        ]

    refdata.cache.set(cache_key, cycles)
    return cycles


def get_cycle_by_id(
    refdata: RefDataRuntime,
    cycle_id: str,
) -> PeriodCycle | None:
    """Retrieve a period cycle by cycle ID, if present."""
    check_refdata_ready(refdata)

    cache_key = f"period_cycle:{cycle_id}"
    cached = refdata.cache.get(cache_key)
    if isinstance(cached, PeriodCycle):
        return cached

    with refdata.session_manager.db_session_scope() as session:
        cycle = session.query(PeriodCycleORM).filter_by(cycle_id=cycle_id).first()
        if cycle is None:
            return None

        result = period_cycle_from_orm(cycle)

    refdata.cache.set(cache_key, result)
    return result


def is_period_cycle_membership_list(
    value: object,
) -> TypeGuard[list[PeriodCycleMembership]]:
    """Return whether a value is a list of PeriodCycleMembership objects."""
    if not isinstance(value, list):
        return False

    items = cast(list[object], value)
    return all(isinstance(item, PeriodCycleMembership) for item in items)


def get_cycle_memberships(
    refdata: RefDataRuntime,
    cycle_id: str,
) -> list[PeriodCycleMembership]:
    """Retrieve memberships for a period cycle."""
    check_refdata_ready(refdata)

    cache_key = f"period_cycle_memberships:{cycle_id}"
    cached = refdata.cache.get_checked(
        cache_key,
        is_period_cycle_membership_list,
    )
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        rows = (
            session.query(PeriodCycleMembershipORM)
            .filter(PeriodCycleMembershipORM.cycle_id == cycle_id)
            .order_by(
                PeriodCycleMembershipORM.cycle_instance.asc(),
                PeriodCycleMembershipORM.cycle_element.asc(),
                PeriodCycleMembershipORM.period_id.asc(),
            )
            .all()
        )
        memberships: list[PeriodCycleMembership] = [
            period_cycle_membership_from_orm(row) for row in rows
        ]

    refdata.cache.set(cache_key, memberships)
    return memberships


def get_cycle_elements(
    refdata: RefDataRuntime,
    period_ids: list[str],
    *,
    cycle_id: str,
) -> dict[str, int]:
    """Map period IDs to cycle elements for a period cycle."""
    check_refdata_ready(refdata)

    if not period_ids:
        return {}

    unique_ids = sorted(set(period_ids))
    cache_key = f"period_cycle_elements:{cycle_id}:pids:{','.join(unique_ids)}"

    cached = refdata.cache.get_checked(cache_key, is_str_int_dict)
    if cached is not None:
        return cached

    with refdata.session_manager.db_session_scope() as session:
        rows = (
            session.query(
                PeriodCycleMembershipORM.period_id,
                PeriodCycleMembershipORM.cycle_element,
            )
            .filter(
                PeriodCycleMembershipORM.cycle_id == cycle_id,
                PeriodCycleMembershipORM.period_id.in_(unique_ids),
            )
            .order_by(PeriodCycleMembershipORM.period_id.asc())
            .all()
        )

        result: dict[str, int] = {
            period_id: int(cycle_element) for period_id, cycle_element in rows
        }

    refdata.cache.set(cache_key, result)
    return result


def get_cycle_element(
    refdata: RefDataRuntime,
    period_id: str,
    *,
    cycle_id: str,
) -> int | None:
    """Return one period's cycle element for a period cycle."""
    check_refdata_ready(refdata)

    cache_key = f"period_cycle_element:{cycle_id}:{period_id}"
    cached = refdata.cache.get(cache_key)
    if isinstance(cached, int):
        return cached

    with refdata.session_manager.db_session_scope() as session:
        row = (
            session.query(PeriodCycleMembershipORM.cycle_element)
            .filter(
                PeriodCycleMembershipORM.cycle_id == cycle_id,
                PeriodCycleMembershipORM.period_id == period_id,
            )
            .first()
        )
        if row is None:
            return None

        result = int(row[0])

    refdata.cache.set(cache_key, result)
    return result


def resolve_period_type(period_type: PeriodType | str | None) -> PeriodType | None:
    """Resolve optional period-type input."""
    if period_type is None:
        return None

    if isinstance(period_type, PeriodType):
        return period_type

    try:
        return PeriodType(period_type)
    except ValueError as err:
        raise ValueError(f"Unknown period_type {period_type!r}") from err


def is_str_int_dict(value: object) -> TypeGuard[dict[str, int]]:
    """Return whether a value is a ``dict[str, int]``."""
    if not isinstance(value, dict):
        return False

    items = cast(dict[object, object], value)

    return all(
        isinstance(key, str) and isinstance(item, int) for key, item in items.items()
    )
