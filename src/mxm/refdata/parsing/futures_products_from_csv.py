from __future__ import annotations

import csv

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.products.futures_product import FuturesProduct, SettlementMethod
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.utils.period_types_codec import decode_period_types


def parse_futures_products_csv(csv_file_path: str) -> list[FuturesProduct]:
    """Parse futures_products.csv into FuturesProduct domain objects."""
    required_fields = {
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

    def _fopt(x: str | None) -> float | None:
        s = (x or "").strip()
        return float(s) if s else None

    def _freq(x: str | None, field: str) -> float:
        s = (x or "").strip()
        if not s:
            raise ValueError(f"required numeric field {field!r} is empty")
        return float(s)

    with open(csv_file_path, mode="r", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        products: list[FuturesProduct] = []

        for row in reader:
            missing_fields = required_fields - set(row.keys())
            if missing_fields:
                raise ValueError(f"Missing required fields in CSV: {missing_fields}")

            products.append(
                FuturesProduct(
                    product_id=row["product_id"],
                    venue=row["venue"],
                    description=row["description"],
                    currency=Currency[row["currency"]],
                    unit=ProductUnit[row["unit"]],
                    contract_size=_freq(row.get("contract_size"), "contract_size"),
                    valid_period_rule=row["valid_period_rule"],
                    listing_rule=row["listing_rule"],
                    period_types=decode_period_types(row["period_types"]),
                    settlement=SettlementMethod[row["settlement"]],
                    last_trading_rule=row["last_trading_rule"],
                    expiry_rule=row["expiry_rule"],
                    trading_calendar=row["trading_calendar"],
                    trading_hours=(row.get("trading_hours") or "").strip() or None,
                    tick_size=_fopt(row.get("tick_size")),
                    tick_value=_fopt(row.get("tick_value")),
                    initial_margin=_fopt(row.get("initial_margin")),
                    maintenance_margin=_fopt(row.get("maintenance_margin")),
                )
            )

    return products
