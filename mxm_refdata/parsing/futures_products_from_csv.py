"""Parse csv file containing futures_product data to normalised internal data."""

import csv

from mxm_refdata.models.currencies import Currency
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.models.products.futures_product import SettlementMethod
from mxm_refdata.models.units import ProductUnit


def parse_futures_products_csv_to_normalised_data(csv_file_path: str) -> list[dict]:
    """Parse CSV into a normalized format."""
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
    }

    with open(csv_file_path, mode="r", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        products = []
        for row in reader:
            # Validate presence of required fields
            missing_fields = required_fields - set(row.keys())
            if missing_fields:
                raise ValueError(f"Missing required fields in CSV: {missing_fields}")

            # Normalize and validate field values
            normalized = {
                "product_id": row["product_id"],
                "venue": row["venue"],
                "description": row["description"],
                "currency": Currency[row["currency"]],
                "unit": ProductUnit[row["unit"]],
                "contract_size": float(row["contract_size"]),
                "valid_period_rule": row["valid_period_rule"],
                "listing_rule": row["listing_rule"],
                "period_types": PeriodType[row["period_types"]],
                "settlement": SettlementMethod[row["settlement"]],
                "last_trading_rule": row["last_trading_rule"],
                "expiry_rule": row["expiry_rule"],
                "trading_calendar": row["trading_calendar"],
                "trading_hours": row["trading_hours"],
                "tick_size": float(row["tick_size"]),
                "tick_value": float(row["tick_value"]),
                "initial_margin": float(row["initial_margin"])
                if row.get("initial_margin")
                else None,
                "maintenance_margin": float(row["maintenance_margin"])
                if row.get("maintenance_margin")
                else None,
            }
            products.append(normalized)

    return products
