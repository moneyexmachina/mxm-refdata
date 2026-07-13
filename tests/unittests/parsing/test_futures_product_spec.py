"""Tests for parsing curated futures product specifications from JSON."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.parsing.futures_product import (
    build_futures_products,
    parse_futures_product_spec,
    parse_futures_product_specs,
)

# ---------------------------------------------------------------------
# FIXTURES AND HELPERS
# ---------------------------------------------------------------------


@pytest.fixture
def valid_product_spec_json() -> dict[str, Any]:
    """Return a complete representative product specification document."""

    return {
        "schema_version": "futures_product.v1",
        "product_id": "comex_aluminum_futures",
        "asset_class": "futures",
        "source_status": {
            "created_at": "2026-06-23",
            "updated_at": "2026-06-23",
            "review_status": "draft",
            "curator": "mxm",
        },
        "provenance": {
            "source_type": "manual_curation",
            "source_url": (
                "https://www.cmegroup.com/markets/metals/base/"
                "aluminum.contractSpecs.html"
            ),
            "source_accessed_at": "2026-06-23",
            "curation_method": ("human_interpreted_from_exchange_contract_specs"),
            "assistance": "llm_assisted_drafting",
            "notes": [
                (
                    "Primary tick_size and tick_value use CME Globex "
                    "outright futures increment."
                ),
                ("Listing horizon interpreted as 60 consecutive monthly contracts."),
            ],
        },
        "product": {
            "product_id": "comex_aluminum_futures",
            "venue": "COMEX",
            "description": "Aluminum Futures",
            "currency": "USD",
            "unit": "METRIC_TON",
            "contract_size": 25,
            "valid_period_rule": "FGHJKMNQUVXZ",
            "listing_rule": ("Monthly contracts listed for 60 consecutive months"),
            "period_types": "MONTH",
            "settlement": "PHYSICAL",
            "last_trading_rule": (
                "Trading terminates on the third last business day "
                "of the contract month."
            ),
            "expiry_rule": ("Third last business day of the contract month."),
            "trading_calendar": "CMES",
            "trading_hours": (
                "Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a "
                "60-minute break each day beginning at 4:00 p.m."
            ),
            "tick_size": 0.25,
            "tick_value": 6.25,
            "initial_margin": None,
            "maintenance_margin": None,
        },
        "parsed_rules": {
            "first_day_of_interest_rule": {
                "shift_rule": {
                    "shift_period_type": "MONTH",
                    "n_shift": {
                        "Jan": 60,
                        "Feb": 60,
                        "Mar": 60,
                        "Apr": 60,
                        "May": 60,
                        "Jun": 60,
                        "Jul": 60,
                        "Aug": 60,
                        "Sep": 60,
                        "Oct": 60,
                        "Nov": 60,
                        "Dec": 60,
                    },
                },
                "reference_rule": "next_b_day_after_period",
            },
            "last_trading_rule": {
                "period_offset": 0,
                "reference_event": "business_day_of_period",
                "n_reference": -3,
                "business_day_offset": 0,
            },
        },
    }


def write_json(
    file_path: Path,
    document: object,
) -> Path:
    """Write a JSON-compatible document and return its path."""

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )
    return file_path


def write_valid_spec(
    tmp_path: Path,
    document: dict[str, Any],
    *,
    relative_path: str = "product.json",
) -> Path:
    """Write a valid product specification below tmp_path."""

    return write_json(
        tmp_path / relative_path,
        document,
    )


# ---------------------------------------------------------------------
# COMPLETE SPECIFICATION PARSING
# ---------------------------------------------------------------------


def test_parse_futures_product_spec_constructs_complete_spec(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    file_path = write_valid_spec(
        tmp_path,
        valid_product_spec_json,
    )

    spec = parse_futures_product_spec(file_path)

    assert spec.schema_version == "futures_product.v1"
    assert spec.product_id == "comex_aluminum_futures"
    assert spec.asset_class == "futures"

    assert spec.source_status.created_at == date(2026, 6, 23)
    assert spec.source_status.updated_at == date(2026, 6, 23)
    assert spec.source_status.review_status == "draft"
    assert spec.source_status.curator == "mxm"

    assert spec.provenance.source_type == "manual_curation"
    assert spec.provenance.source_accessed_at == date(2026, 6, 23)
    assert spec.provenance.curation_method == (
        "human_interpreted_from_exchange_contract_specs"
    )
    assert spec.provenance.assistance == "llm_assisted_drafting"
    assert len(spec.provenance.notes) == 2
    assert isinstance(spec.provenance.notes, tuple)

    product = spec.product

    assert product.product_id == "comex_aluminum_futures"
    assert product.venue == "COMEX"
    assert product.description == "Aluminum Futures"
    assert product.currency is Currency.USD
    assert product.unit is ProductUnit.METRIC_TON
    assert product.contract_size == 25.0
    assert product.valid_period_rule == "FGHJKMNQUVXZ"
    assert product.period_types == (PeriodType.MONTH,)
    assert product.settlement is SettlementMethod.PHYSICAL
    assert product.trading_calendar == "CMES"
    assert product.tick_size == 0.25
    assert product.tick_value == 6.25
    assert product.initial_margin is None
    assert product.maintenance_margin is None

    last_trading_rule = spec.contract_rules.last_trading_rule

    assert last_trading_rule.period_offset == 0
    assert last_trading_rule.reference_event is ReferenceEvent.BUSINESS_DAY_OF_PERIOD
    assert last_trading_rule.n_reference == -3
    assert last_trading_rule.business_day_offset == 0
    assert last_trading_rule.weekday is None

    first_day_rule = spec.contract_rules.first_day_of_interest_rule

    assert first_day_rule.shift_rule.shift_period_type is PeriodType.MONTH
    assert first_day_rule.shift_rule.n_shift["Jan"] == 60
    assert first_day_rule.shift_rule.n_shift["Dec"] == 60
    assert first_day_rule.reference_rule == "next_b_day_after_period"


def test_parse_futures_product_spec_parses_nullable_product_fields(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    product = document["product"]

    product["trading_hours"] = None
    product["tick_size"] = None
    product["tick_value"] = None
    product["initial_margin"] = None
    product["maintenance_margin"] = None

    file_path = write_valid_spec(tmp_path, document)

    spec = parse_futures_product_spec(file_path)

    assert spec.product.trading_hours is None
    assert spec.product.tick_size is None
    assert spec.product.tick_value is None
    assert spec.product.initial_margin is None
    assert spec.product.maintenance_margin is None


def test_parse_futures_product_spec_normalises_empty_optional_string(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product"]["trading_hours"] = "   "

    file_path = write_valid_spec(tmp_path, document)

    spec = parse_futures_product_spec(file_path)

    assert spec.product.trading_hours is None


def test_parse_futures_product_spec_parses_weekday_rule(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["last_trading_rule"] = {
        "period_offset": 0,
        "reference_event": "weekday_of_period",
        "n_reference": 3,
        "business_day_offset": 0,
        "weekday": "Friday",
    }

    file_path = write_valid_spec(tmp_path, document)

    spec = parse_futures_product_spec(file_path)
    rule = spec.contract_rules.last_trading_rule

    assert rule.reference_event is ReferenceEvent.WEEKDAY_OF_PERIOD
    assert rule.n_reference == 3
    assert rule.weekday == Weekday(4)


@pytest.mark.parametrize(
    ("raw_event", "expected_event"),
    [
        (
            "business_day_of_period",
            ReferenceEvent.BUSINESS_DAY_OF_PERIOD,
        ),
        (
            "calendar_day_of_period",
            ReferenceEvent.CALENDAR_DAY_OF_PERIOD,
        ),
    ],
)
def test_parse_futures_product_spec_parses_reference_events(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
    raw_event: str,
    expected_event: ReferenceEvent,
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["last_trading_rule"]["reference_event"] = raw_event

    file_path = write_valid_spec(tmp_path, document)

    spec = parse_futures_product_spec(file_path)

    assert spec.contract_rules.last_trading_rule.reference_event is expected_event


# ---------------------------------------------------------------------
# TOP-LEVEL STRUCTURAL VALIDATION
# ---------------------------------------------------------------------


def test_parse_futures_product_spec_rejects_non_object_top_level_json(
    tmp_path: Path,
) -> None:
    file_path = write_json(
        tmp_path / "product.json",
        ["not", "an", "object"],
    )

    with pytest.raises(
        ValueError,
        match="expected top-level JSON object",
    ):
        parse_futures_product_spec(file_path)


@pytest.mark.parametrize(
    "missing_field",
    [
        "product",
        "source_status",
        "provenance",
        "parsed_rules",
    ],
)
def test_parse_futures_product_spec_rejects_missing_top_level_section(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
    missing_field: str,
) -> None:
    document = deepcopy(valid_product_spec_json)
    del document[missing_field]

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match=rf"field '{missing_field}' must be a JSON object",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_non_object_nested_section(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["provenance"] = "not-an-object"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="field 'provenance' must be a JSON object",
    ):
        parse_futures_product_spec(file_path)


# ---------------------------------------------------------------------
# SCALAR AND ENUM VALIDATION
# ---------------------------------------------------------------------


def test_parse_futures_product_spec_rejects_empty_required_string(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product"]["venue"] = "   "

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="field 'venue' must be a non-empty string",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_invalid_iso_date(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["source_status"]["created_at"] = "23-06-2026"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="must be an ISO date",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_unknown_currency(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product"]["currency"] = "UNKNOWN"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="unknown currency",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_unknown_product_unit(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product"]["unit"] = "UNKNOWN"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="unknown product unit",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_unknown_settlement_method(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product"]["settlement"] = "UNKNOWN"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="unknown settlement method",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_unknown_period_type(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["first_day_of_interest_rule"]["shift_rule"][
        "shift_period_type"
    ] = "UNKNOWN"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="unknown period type",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_unknown_reference_event(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["last_trading_rule"]["reference_event"] = "unknown_event"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="unknown reference event",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_invalid_weekday(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["last_trading_rule"] = {
        "period_offset": 0,
        "reference_event": "weekday_of_period",
        "n_reference": 3,
        "business_day_offset": 0,
        "weekday": "Notaday",
    }

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="invalid weekday",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_boolean_integer(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["last_trading_rule"]["period_offset"] = True

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="field 'period_offset' must be an integer",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_non_numeric_product_value(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product"]["contract_size"] = "twenty-five"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="field 'contract_size' must be numeric",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_non_string_provenance_note(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["provenance"]["notes"] = [
        "Valid note",
        123,
    ]

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="field 'notes' must contain only strings",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_non_integer_month_shift(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["first_day_of_interest_rule"]["shift_rule"]["n_shift"][
        "Jan"
    ] = "sixty"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="shift for 'Jan' must be an integer",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_boolean_month_shift(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["first_day_of_interest_rule"]["shift_rule"]["n_shift"][
        "Jan"
    ] = True

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="shift for 'Jan' must be an integer",
    ):
        parse_futures_product_spec(file_path)


# ---------------------------------------------------------------------
# DOMAIN INVARIANTS THROUGH THE PARSER
# ---------------------------------------------------------------------


def test_parse_futures_product_spec_rejects_missing_weekday_for_weekday_rule(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["parsed_rules"]["last_trading_rule"] = {
        "period_offset": 0,
        "reference_event": "weekday_of_period",
        "n_reference": 3,
        "business_day_offset": 0,
    }

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="weekday is required",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_mismatched_product_ids(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["product_id"] = "different_product"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="product_id does not match",
    ):
        parse_futures_product_spec(file_path)


def test_parse_futures_product_spec_rejects_invalid_source_date_order(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    document = deepcopy(valid_product_spec_json)
    document["source_status"]["created_at"] = "2026-07-01"
    document["source_status"]["updated_at"] = "2026-06-23"

    file_path = write_valid_spec(tmp_path, document)

    with pytest.raises(
        ValueError,
        match="updated_at cannot precede created_at",
    ):
        parse_futures_product_spec(file_path)


# ---------------------------------------------------------------------
# DIRECTORY PARSING
# ---------------------------------------------------------------------


def test_parse_futures_product_specs_recurses_and_orders_by_path(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    product_a = deepcopy(valid_product_spec_json)
    product_a["product_id"] = "product_a"
    product_a["product"]["product_id"] = "product_a"

    product_b = deepcopy(valid_product_spec_json)
    product_b["product_id"] = "product_b"
    product_b["product"]["product_id"] = "product_b"

    write_valid_spec(
        tmp_path,
        product_b,
        relative_path="z/product_b.json",
    )
    write_valid_spec(
        tmp_path,
        product_a,
        relative_path="a/product_a.json",
    )

    specs = parse_futures_product_specs(tmp_path)

    assert [spec.product_id for spec in specs] == [
        "product_a",
        "product_b",
    ]


def test_parse_futures_product_specs_rejects_duplicate_product_ids(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    write_valid_spec(
        tmp_path,
        deepcopy(valid_product_spec_json),
        relative_path="venue_a/product.json",
    )
    write_valid_spec(
        tmp_path,
        deepcopy(valid_product_spec_json),
        relative_path="venue_b/product.json",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate futures product specification",
    ):
        parse_futures_product_specs(tmp_path)


def test_parse_futures_product_specs_rejects_missing_root(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "does-not-exist"

    with pytest.raises(
        ValueError,
        match="JSON root does not exist",
    ):
        parse_futures_product_specs(missing_root)


def test_parse_futures_product_specs_rejects_non_directory_root(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "not-a-directory.json"
    file_path.write_text("{}", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="JSON root is not a directory",
    ):
        parse_futures_product_specs(file_path)


def test_parse_futures_product_specs_rejects_empty_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="No futures product JSON files found",
    ):
        parse_futures_product_specs(tmp_path)


# ---------------------------------------------------------------------
# PRODUCT-ONLY PROJECTION
# ---------------------------------------------------------------------


def test_build_futures_products_projects_nested_products(
    tmp_path: Path,
    valid_product_spec_json: dict[str, Any],
) -> None:
    product_a = deepcopy(valid_product_spec_json)
    product_a["product_id"] = "product_a"
    product_a["product"]["product_id"] = "product_a"

    product_b = deepcopy(valid_product_spec_json)
    product_b["product_id"] = "product_b"
    product_b["product"]["product_id"] = "product_b"

    write_valid_spec(
        tmp_path,
        product_a,
        relative_path="a.json",
    )
    write_valid_spec(
        tmp_path,
        product_b,
        relative_path="b.json",
    )

    products = build_futures_products(tmp_path)

    assert [product.product_id for product in products] == [
        "product_a",
        "product_b",
    ]
    assert all(isinstance(product, FuturesProduct) for product in products)
