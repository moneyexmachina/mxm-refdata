#!/usr/bin/env python3
"""
mxm-refdata/scripts/rebuild_and_smokecheck_refdata_db.py

Reset the refdata SQLite DB, rebuild it from CSV + generators, then run a small
set of high-signal “smell checks” to confirm the schema + domain/ORM semantics.

This script is intentionally NOT a full test suite. It is a fast operational
sanity check for:
- schema creation
- deterministic rebuild
- type-sound ORM ↔ domain mapping surfaces
- basic coherence of core artifacts (periods/products/contracts)
- basic coherence of new PeriodCycle artifacts (cycles + memberships)

Usage examples:

  poetry run python mxm-refdata/scripts/rebuild_and_smokecheck_refdata_db.py

  poetry run python mxm-refdata/scripts/rebuild_and_smokecheck_refdata_db.py \
    --start 2010-01-01 --end 2035-12-31

  poetry run python mxm-refdata/scripts/rebuild_and_smokecheck_refdata_db.py \
    --csv /path/to/futures_products.csv

Exit code:
  0 = success
  1 = failed checks
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import func

from mxm_refdata.database.sql_session_manager import SQLSessionManager
from mxm_refdata.mappings import (
    futures_contract_from_orm,
    futures_product_from_orm,
    period_from_orm,
)
from mxm_refdata.models.orm.futures_contracts import FuturesContractORM
from mxm_refdata.models.orm.futures_products import FuturesProductORM
from mxm_refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.services.ref_data_service import RefDataService
from mxm_refdata.utils.period_types_codec import decode_period_types

# Canonical cycle IDs (keep aligned with RefDataService initialisation)
CYCLE_ID_CALENDAR_MONTHS = "CALENDAR_MONTHS"
CYCLE_ID_CALENDAR_QUARTERS = "CALENDAR_QUARTERS"

# -----------------------------
# Small assertion helpers
# -----------------------------


class CheckFailed(Exception):
    pass


def _fail(msg: str) -> None:
    raise CheckFailed(msg)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        _fail(msg)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@dataclass(frozen=True)
class Counts:
    products: int
    periods: int
    contracts: int
    cycles: int
    memberships: int


def _count_rows(session) -> Counts:
    return Counts(
        products=session.query(FuturesProductORM).count(),
        periods=session.query(PeriodORM).count(),
        contracts=session.query(FuturesContractORM).count(),
        cycles=session.query(PeriodCycleORM).count(),
        memberships=session.query(PeriodCycleMembershipORM).count(),
    )


def _pick_first(iterable: Iterable):
    for x in iterable:
        return x
    return None


# -----------------------------
# Smell checks
# -----------------------------


def smell_check_roundtrip_period_types(session) -> None:
    """
    Verify:
      - ORM stores period_types as TEXT
      - Domain exposes tuple[PeriodType,...]
      - Codec round-trips
    """
    product_orm = _pick_first(session.query(FuturesProductORM).limit(1).all())
    _assert(product_orm is not None, "No products found after rebuild.")

    raw = product_orm.period_types
    _assert(isinstance(raw, str), f"ORM period_types must be str, got {type(raw)}.")
    decoded = decode_period_types(raw)
    _assert(isinstance(decoded, tuple), "Decoded period_types must be tuple.")
    _assert(
        all(isinstance(x, PeriodType) for x in decoded),
        "Decoded tuple must contain PeriodType members.",
    )

    product = futures_product_from_orm(product_orm)
    _assert(
        isinstance(product.period_types, tuple),
        "Domain FuturesProduct.period_types must be tuple.",
    )
    _assert(
        all(isinstance(x, PeriodType) for x in product.period_types),
        "Domain period_types tuple must contain PeriodType members.",
    )

    _assert(
        product.period_types == decoded,
        "Domain period_types does not match decoded ORM value.",
    )


def smell_check_contract_date_types(session) -> None:
    """
    Verify contract date fields are datetime.date in ORM and domain.
    """
    contract_orm = _pick_first(session.query(FuturesContractORM).limit(1).all())
    _assert(contract_orm is not None, "No contracts found after rebuild.")

    fdoi = contract_orm.first_day_of_interest
    ltd = contract_orm.last_trading_day
    _assert(
        isinstance(fdoi, date),
        f"ORM first_day_of_interest must be date, got {type(fdoi)}.",
    )
    _assert(
        isinstance(ltd, date), f"ORM last_trading_day must be date, got {type(ltd)}."
    )

    contract = futures_contract_from_orm(contract_orm)
    _assert(
        isinstance(contract.first_day_of_interest, date),
        "Domain first_day_of_interest must be date.",
    )
    _assert(
        isinstance(contract.last_trading_day, date),
        "Domain last_trading_day must be date.",
    )


def smell_check_contracts_periods_coherence(session) -> None:
    """
    Coherence check:
      - contracts reference existing periods via period_id
      - period_type filtering is feasible
    """
    product_id = _pick_first(
        [
            pid
            for (pid,) in session.query(FuturesContractORM.product_id)
            .distinct()
            .limit(1)
            .all()
        ]
    )
    _assert(product_id is not None, "No product_id found in contracts table.")

    contracts_orm = (
        session.query(FuturesContractORM)
        .filter(FuturesContractORM.product_id == product_id)
        .order_by(FuturesContractORM.contract_id.asc())
        .all()
    )
    _assert(
        len(contracts_orm) > 0, f"No contracts found for product_id={product_id!r}."
    )

    contracts = [futures_contract_from_orm(c) for c in contracts_orm]
    sample = contracts[0]
    period_id = getattr(sample, "period_id", None)
    _assert(
        period_id is not None,
        "Domain FuturesContract is expected to expose period_id for period typing/filtering.",
    )

    periods = {p.period_id: period_from_orm(p) for p in session.query(PeriodORM).all()}

    ptypes = []
    for c in contracts:
        p = periods.get(c.period_id)
        if p is not None:
            ptypes.append(p.period_type)

    _assert(
        len(ptypes) > 0,
        "Could not resolve period types for contracts via periods table.",
    )
    chosen = _pick_first(sorted(set(ptypes), key=lambda x: x.value))
    _assert(chosen is not None, "No period types found for product contracts.")

    subset = [c for c in contracts if periods[c.period_id].period_type == chosen]
    _assert(
        0 < len(subset) <= len(contracts),
        "Filtering by period_type should yield a non-empty subset.",
    )


def smell_check_period_cycles_present(session) -> None:
    """
    Verify that the canonical calendar cycles exist and have memberships.
    """
    cycle_ids = {cid for (cid,) in session.query(PeriodCycleORM.cycle_id).all()}
    _assert(CYCLE_ID_CALENDAR_MONTHS in cycle_ids, "Missing cycle CALENDAR_MONTHS.")
    _assert(CYCLE_ID_CALENDAR_QUARTERS in cycle_ids, "Missing cycle CALENDAR_QUARTERS.")

    m_months = (
        session.query(PeriodCycleMembershipORM)
        .filter(PeriodCycleMembershipORM.cycle_id == CYCLE_ID_CALENDAR_MONTHS)
        .count()
    )
    m_quarters = (
        session.query(PeriodCycleMembershipORM)
        .filter(PeriodCycleMembershipORM.cycle_id == CYCLE_ID_CALENDAR_QUARTERS)
        .count()
    )
    _assert(m_months > 0, "No memberships for CALENDAR_MONTHS.")
    _assert(m_quarters > 0, "No memberships for CALENDAR_QUARTERS.")


def smell_check_period_cycle_membership_uniqueness(session) -> None:
    """
    Verify uniqueness constraints are not violated (high-signal for bad seeding).

    We check (cycle_id, cycle_instance, cycle_element) is unique.
    The DB schema also enforces this, but this check gives a clear message.
    """
    dup = (
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
    _assert(not dup, f"Duplicate cycle membership keys found: {dup!r}")


def smell_check_calendar_month_mapping(session, *, expect_month: int = 12) -> None:
    """
    Spot-check: for some YEAR, there exists a MONTH period mapped to cycle_element=expect_month.

    This does not assume period_id parsing. We verify via Period.first_date.month.
    """
    # pick any membership with cycle_element==expect_month
    mem = (
        session.query(PeriodCycleMembershipORM)
        .filter(
            PeriodCycleMembershipORM.cycle_id == CYCLE_ID_CALENDAR_MONTHS,
            PeriodCycleMembershipORM.cycle_element == expect_month,
        )
        .limit(1)
        .one_or_none()
    )
    _assert(mem is not None, f"No month membership found for element={expect_month}.")

    p = (
        session.query(PeriodORM)
        .filter(PeriodORM.period_id == mem.period_id)
        .one_or_none()
    )
    _assert(p is not None, f"Membership references missing Period: {mem.period_id!r}")
    _assert(
        p.period_type == PeriodType.MONTH,
        f"Expected mapped period_type MONTH, got {p.period_type!r}",
    )
    _assert(
        p.first_date.month == expect_month,
        f"Expected Period.first_date.month={expect_month}, got {p.first_date.month}",
    )


# -----------------------------
# Main
# -----------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild mxm-refdata DB and run smoke checks."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Optional path to futures_products.csv (defaults to packaged resource).",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2000-01-01",
        help="Start date for period/contract generation (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2045-12-31",
        help="End date for period/contract generation (YYYY-MM-DD).",
    )
    args = parser.parse_args()

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    _assert(start <= end, f"Invalid date range: start={start} > end={end}")

    sm = SQLSessionManager()
    svc = RefDataService(session_manager=sm)

    print("== mxm-refdata rebuild ==")
    print(f"Range: {start} .. {end}")
    print(f"CSV:   {args.csv or '(packaged resource)'}")

    svc.reset_database()
    svc.setup_instruments(csv_file_path=args.csv, start_date=start, end_date=end)

    print("== smoke checks ==")
    failures: list[str] = []
    with sm.db_session_scope() as session:
        counts = _count_rows(session)
        print(
            "Counts: "
            f"products={counts.products}, "
            f"periods={counts.periods}, "
            f"contracts={counts.contracts}, "
            f"cycles={counts.cycles}, "
            f"memberships={counts.memberships}"
        )

        try:
            _assert(counts.products > 0, "No products inserted.")
            _assert(counts.periods > 0, "No periods inserted.")
            _assert(counts.contracts > 0, "No contracts inserted.")

            smell_check_roundtrip_period_types(session)
            print("OK: period_types storage + round-trip")

            smell_check_contract_date_types(session)
            print("OK: contract date field types")

            smell_check_contracts_periods_coherence(session)
            print("OK: contracts/periods coherence + filterability")

            smell_check_period_cycles_present(session)
            print("OK: period cycles present + non-empty memberships")

            smell_check_period_cycle_membership_uniqueness(session)
            print("OK: period cycle membership uniqueness")

            smell_check_calendar_month_mapping(session, expect_month=12)
            print("OK: calendar month mapping spot-check (Dec)")

        except CheckFailed as e:
            failures.append(str(e))

    if failures:
        print("== FAILED ==")
        for f in failures:
            print(f"- {f}")
        return 1

    print("== SUCCESS ==")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as e:
        print(f"FAILED: {e}")
        raise SystemExit(1)
