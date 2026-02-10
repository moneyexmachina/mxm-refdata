#!/usr/bin/env python3
"""
mxm-refdata/scripts/rebuild_and_smokecheck_refdata_db.py

Reset the refdata SQLite DB, rebuild it from CSV + generators, then run a small
set of high-signal “smell checks” to confirm the schema + domain/ORM semantics.

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
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from mxm_refdata.database.sql_session_manager import SQLSessionManager
from mxm_refdata.mappings.orm_converter import orm_to_obj
from mxm_refdata.models.orm.futures_contracts import FuturesContractORM
from mxm_refdata.models.orm.futures_products import FuturesProductORM
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.services.ref_data_service import RefDataService
from mxm_refdata.utils.period_types_codec import decode_period_types

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


def _count_rows(session) -> Counts:
    return Counts(
        products=session.query(FuturesProductORM).count(),
        periods=session.query(PeriodORM).count(),
        contracts=session.query(FuturesContractORM).count(),
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

    product = orm_to_obj(product_orm)
    _assert(
        isinstance(product.period_types, tuple),
        "Domain FuturesProduct.period_types must be tuple.",
    )
    _assert(
        all(isinstance(x, PeriodType) for x in product.period_types),
        "Domain period_types tuple must contain PeriodType members.",
    )

    # Exact equality between domain and decoded string
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

    # ORM field types
    fdoi = contract_orm.first_day_of_interest
    ltd = contract_orm.last_trading_day
    _assert(
        isinstance(fdoi, date),
        f"ORM first_day_of_interest must be date, got {type(fdoi)}.",
    )
    _assert(
        isinstance(ltd, date), f"ORM last_trading_day must be date, got {type(ltd)}."
    )

    # Domain field types
    contract = orm_to_obj(contract_orm)
    _assert(
        isinstance(contract.first_day_of_interest, date),
        "Domain first_day_of_interest must be date.",
    )
    _assert(
        isinstance(contract.last_trading_day, date),
        "Domain last_trading_day must be date.",
    )


def smell_check_get_contracts_for_product_like_semantics(session) -> None:
    """
    Lightweight proxy check for RefDataAPI contract retrieval semantics without assuming the API class.
    We verify:
      - We can group contracts by product_id
      - Filtering by period_type is feasible and returns a subset
      - Deterministic ordering can be enforced downstream (selector will own selection logic)

    This does NOT test RefDataAPI directly; it checks the stored artifacts are coherent.
    """
    # Pick a product with contracts
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

    # Pull contracts for that product
    contracts_orm = (
        session.query(FuturesContractORM)
        .filter(FuturesContractORM.product_id == product_id)
        .order_by(FuturesContractORM.contract_id.asc())
        .all()
    )
    _assert(
        len(contracts_orm) > 0, f"No contracts found for product_id={product_id!r}."
    )

    # Convert
    contracts = [orm_to_obj(c) for c in contracts_orm]

    # If periods are attached by period_id, ensure we can load them and filter by period_type.
    # This assumes FuturesContract has period_id or period reference via contract.period_id.
    sample = contracts[0]
    period_id = getattr(sample, "period_id", None)
    _assert(
        period_id is not None,
        "Domain FuturesContract is expected to expose period_id for period typing/filtering.",
    )

    # Load periods into dict
    periods_orm = session.query(PeriodORM).all()
    periods = {p.period_id: orm_to_obj(p) for p in periods_orm}

    # Choose a period type that exists for this product (if any)
    ptypes = []
    for c in contracts:
        p = periods.get(c.period_id)
        if p is not None:
            ptypes.append(p.period_type)

    _assert(
        len(ptypes) > 0,
        "Could not resolve period types for contracts via periods table.",
    )
    chosen = _pick_first(sorted(set(ptypes), key=lambda x: x.value))  # type: ignore[attr-defined]
    _assert(chosen is not None, "No period types found for product contracts.")

    subset = [c for c in contracts if periods[c.period_id].period_type == chosen]
    _assert(
        0 < len(subset) <= len(contracts),
        "Filtering by period_type should yield a non-empty subset.",
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
    parser.add_argument(
        "--max-products",
        type=int,
        default=None,
        help="Optional: cap products inserted (debug only).",
    )
    args = parser.parse_args()

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    _assert(start <= end, f"Invalid date range: start={start} > end={end}")

    # Create service
    sm = SQLSessionManager()
    svc = RefDataService(session_manager=sm)

    print("== mxm-refdata rebuild ==")
    print(f"Range: {start} .. {end}")
    print(f"CSV:   {args.csv or '(packaged resource)'}")

    # Rebuild
    svc.reset_database()
    svc.setup_instruments(csv_file_path=args.csv, start_date=start, end_date=end)

    # Smell checks
    print("== smoke checks ==")
    failures: list[str] = []
    with sm.db_session_scope() as session:
        counts = _count_rows(session)
        print(
            f"Counts: products={counts.products}, periods={counts.periods}, contracts={counts.contracts}"
        )

        try:
            _assert(counts.products > 0, "No products inserted.")
            _assert(counts.periods > 0, "No periods inserted.")
            _assert(counts.contracts > 0, "No contracts inserted.")

            smell_check_roundtrip_period_types(session)
            print("OK: period_types storage + round-trip")

            smell_check_contract_date_types(session)
            print("OK: contract date field types")

            smell_check_get_contracts_for_product_like_semantics(session)
            print("OK: contracts/periods coherence + filterability")

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
