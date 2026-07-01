from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Literal, TypedDict, cast

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.utils.period_types_codec import decode_period_types


class FuturesProductDict(TypedDict):
    """Intermediate representation of a futures product.

    This is a structured representation derived from MXM-owned data sources
    (CSV, JSON). It is NOT a domain object, only a staging structure for
    deterministic construction of FuturesProduct instances.
    """

    product_id: str
    venue: str
    description: str
    currency: str
    unit: str
    contract_size: str | float
    valid_period_rule: str
    listing_rule: str
    period_types: str
    settlement: str
    last_trading_rule: str
    expiry_rule: str
    trading_calendar: str
    trading_hours: str | None
    tick_size: str | float | None
    tick_value: str | float | None
    initial_margin: str | float | None
    maintenance_margin: str | float | None


# ---------------------------------------------------------------------
# CSV LOADING
# ---------------------------------------------------------------------


def parse_futures_products_csv(file_path: Path) -> list[FuturesProductDict]:
    """Parse futures_products.csv into intermediate dict representation.

    This function performs only CSV I/O and minimal structural validation.
    No domain conversion is performed here.
    """

    required_fields: set[str] = {
        "product_id",
        "venue",
        "description",
        "currency",
        "unit",
        "contract_size",
        "valid_period_rule",
        "listing_rule",
        "period_types",
        "settlement",
        "last_trading_rule",
        "expiry_rule",
        "trading_calendar",
        "trading_hours",
        "tick_size",
        "tick_value",
        "initial_margin",
        "maintenance_margin",
    }

    with open(file_path, encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)

        rows: list[FuturesProductDict] = []

        for row in reader:
            missing = required_fields - set(row.keys())
            if missing:
                raise ValueError(f"Missing required CSV fields: {missing}")

            rows.append(_row_to_dict(row))

        return rows


def _row_to_dict(row: dict[str, str | None]) -> FuturesProductDict:
    """Convert raw CSV row into a FuturesProductDict."""

    return FuturesProductDict(
        product_id=row["product_id"] or "",
        venue=row["venue"] or "",
        description=row["description"] or "",
        currency=row["currency"] or "",
        unit=row["unit"] or "",
        contract_size=row.get("contract_size") or "",
        valid_period_rule=row["valid_period_rule"] or "",
        listing_rule=row["listing_rule"] or "",
        period_types=row["period_types"] or "",
        settlement=row["settlement"] or "",
        last_trading_rule=row["last_trading_rule"] or "",
        expiry_rule=row["expiry_rule"] or "",
        trading_calendar=row["trading_calendar"] or "",
        trading_hours=row.get("trading_hours"),
        tick_size=row.get("tick_size"),
        tick_value=row.get("tick_value"),
        initial_margin=row.get("initial_margin"),
        maintenance_margin=row.get("maintenance_margin"),
    )


# ---------------------------------------------------------------------
# JSON LOADING
# ---------------------------------------------------------------------


def _parse_futures_product_json(file_path: Path) -> FuturesProductDict:
    """Parse a single futures product JSON file into FuturesProductDict."""

    with file_path.open("r", encoding="utf-8") as f:
        raw: dict[str, object] = json.load(f)

    if "product" not in raw:
        raise ValueError(f"Invalid product JSON (missing 'product'): {file_path}")

    return cast(FuturesProductDict, raw["product"])


def parse_futures_products_json(file_path: Path) -> list[FuturesProductDict]:
    """Parse a directory of MXM futures product JSON files.

    Each JSON file contains exactly one product definition under the
    `product` key, plus metadata (provenance, parsed_rules, etc.).

    This loader:
    - walks the directory tree recursively
    - loads each JSON file
    - extracts the `product` section
    - converts it into a FuturesProductDict

    Args:
        file_path: Root directory of mxm-refdata-source futures products.

    Returns:
        List of FuturesProductDict entries (one per product file).
    """

    if not file_path.exists():
        raise ValueError(f"JSON root directory does not exist: {file_path}")

    products: list[FuturesProductDict] = []

    for _path in file_path.rglob("*.json"):
        products.append(_parse_futures_product_json(_path))

    return products


# ---------------------------------------------------------------------
# DOMAIN CONSTRUCTION
# ---------------------------------------------------------------------


def futures_product_from_dict(data: FuturesProductDict) -> FuturesProduct:
    """Construct a FuturesProduct from a normalized intermediate dict."""

    def _opt_float(v: object) -> float | None:
        if v is None:
            return None
        s = str(v).strip()
        return float(s) if s else None

    def _req_float(v: object, field: str) -> float:
        s = str(v).strip()
        if not s:
            raise ValueError(f"required numeric field '{field}' is empty")
        return float(s)

    return FuturesProduct(
        product_id=data["product_id"],
        venue=data["venue"],
        description=data["description"],
        currency=Currency[data["currency"]],
        unit=ProductUnit[data["unit"]],
        contract_size=_req_float(data["contract_size"], "contract_size"),
        valid_period_rule=data["valid_period_rule"],
        listing_rule=data["listing_rule"],
        period_types=decode_period_types(data["period_types"]),
        settlement=SettlementMethod[data["settlement"]],
        last_trading_rule=data["last_trading_rule"],
        expiry_rule=data["expiry_rule"],
        trading_calendar=data["trading_calendar"],
        trading_hours=(str(data.get("trading_hours") or "").strip() or None),
        tick_size=_opt_float(data.get("tick_size")),
        tick_value=_opt_float(data.get("tick_value")),
        initial_margin=_opt_float(data.get("initial_margin")),
        maintenance_margin=_opt_float(data.get("maintenance_margin")),
    )


# ---------------------------------------------------------------------
# HIGH-LEVEL PIPELINE
# ---------------------------------------------------------------------
def build_futures_products(
    file_path: Path, source: Literal["csv", "json"]
) -> list[FuturesProduct]:
    """End-to-end pipeline from csv/json files to FuturesProduct."""
    if source == "csv":
        dicts = parse_futures_products_csv(file_path)
    elif source == "json":
        dicts = parse_futures_products_json(file_path)
    return [futures_product_from_dict(r) for r in dicts]
