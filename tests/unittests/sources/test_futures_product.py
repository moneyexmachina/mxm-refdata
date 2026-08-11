"""Unit tests for the futures-product source-provider API."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

import mxm.refdata.sources.futures_product as source_module
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct
from mxm.refdata.models.products.settlement import SettlementMethod
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.sources.futures_product import (
    FuturesProductSourceMetadata,
    FuturesProductSourceRevisionError,
    load_futures_product,
    load_futures_products,
    resolve_futures_product_source_revision,
)

# ---------------------------------------------------------------------
# FIXTURES AND HELPERS
# ---------------------------------------------------------------------


@pytest.fixture
def valid_futures_product_json() -> dict[str, Any]:
    """Return a complete representative futures-product source document."""

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

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    return file_path


def write_valid_product(
    root_dir: Path,
    document: dict[str, Any],
    *,
    relative_path: str = "product.json",
) -> Path:
    """Write one futures-product document below a source root."""

    return write_json(
        root_dir / relative_path,
        document,
    )


def set_product_id(
    document: dict[str, Any],
    product_id: str,
) -> None:
    """Change both source-document product identity fields."""

    document["product_id"] = product_id
    document["product"]["product_id"] = product_id


def load_document(
    root_dir: Path,
    document: dict[str, Any],
    *,
    relative_path: str = "product.json",
):
    """Write and load one futures-product source document."""

    file_path = write_valid_product(
        root_dir,
        document,
        relative_path=relative_path,
    )

    return load_futures_product(
        file_path,
        root_dir=root_dir,
    )


def valid_source_metadata() -> FuturesProductSourceMetadata:
    """Return representative valid source metadata."""

    return FuturesProductSourceMetadata(
        schema_version="futures_product.v1",
        source_relative_path="cme/metals/aluminum.json",
        source_digest="a" * 64,
        created_at=date(2026, 6, 23),
        updated_at=date(2026, 6, 23),
        review_status="draft",
        curator="mxm",
        source_type="manual_curation",
        source_url="https://example.com/product",
        source_accessed_at=date(2026, 6, 23),
        curation_method="human_interpreted",
        assistance="llm_assisted_drafting",
        notes=(),
    )


# ---------------------------------------------------------------------
# SOURCE METADATA MODEL
# ---------------------------------------------------------------------


def test_source_metadata_accepts_valid_values() -> None:
    """Valid source metadata constructs successfully."""

    metadata = valid_source_metadata()

    assert metadata.schema_version == "futures_product.v1"
    assert metadata.source_relative_path == "cme/metals/aluminum.json"
    assert metadata.source_digest == "a" * 64


def test_source_metadata_rejects_empty_schema_version() -> None:
    """Source schema identity must be present."""

    metadata = valid_source_metadata()

    with pytest.raises(
        ValueError,
        match="schema_version must be non-empty",
    ):
        replace(
            metadata,
            schema_version="",
        )


def test_source_metadata_rejects_empty_relative_path() -> None:
    """Each record must retain a source-relative path."""

    metadata = valid_source_metadata()

    with pytest.raises(
        ValueError,
        match="source_relative_path must be non-empty",
    ):
        replace(
            metadata,
            source_relative_path="",
        )


@pytest.mark.parametrize(
    "invalid_digest",
    [
        "",
        "a" * 63,
        "a" * 65,
        "g" * 64,
        "A" * 64,
    ],
)
def test_source_metadata_rejects_invalid_digest(
    invalid_digest: str,
) -> None:
    """The source digest must be lowercase hexadecimal SHA-256."""

    metadata = valid_source_metadata()

    with pytest.raises(
        ValueError,
        match="64-character lowercase hexadecimal SHA-256 digest",
    ):
        replace(
            metadata,
            source_digest=invalid_digest,
        )


def test_source_metadata_rejects_updated_before_created() -> None:
    """Source updates cannot predate source creation."""

    metadata = valid_source_metadata()

    with pytest.raises(
        ValueError,
        match="updated_at cannot precede created_at",
    ):
        replace(
            metadata,
            created_at=date(2026, 7, 1),
            updated_at=date(2026, 6, 23),
        )


# ---------------------------------------------------------------------
# COMPLETE SOURCE-RECORD CONSTRUCTION
# ---------------------------------------------------------------------


def test_load_futures_product_constructs_complete_source_record(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """One source document produces a product and separate metadata."""

    record = load_document(
        tmp_path,
        valid_futures_product_json,
        relative_path="cme/metals/aluminum.json",
    )

    product = record.product

    assert isinstance(
        product,
        FuturesProduct,
    )

    assert product.product_id == "comex_aluminum_futures"
    assert product.asset_class == "futures"
    assert product.venue == "COMEX"
    assert product.description == "Aluminum Futures"
    assert product.currency is Currency.USD
    assert product.unit is ProductUnit.METRIC_TON
    assert product.contract_size == 25.0
    assert product.valid_period_rule == "FGHJKMNQUVXZ"
    assert product.listing_rule == (
        "Monthly contracts listed for 60 consecutive months"
    )
    assert product.period_types == (PeriodType.MONTH,)
    assert product.settlement is SettlementMethod.PHYSICAL
    assert product.trading_calendar == "CMES"
    assert product.tick_size == 0.25
    assert product.tick_value == 6.25
    assert product.initial_margin is None
    assert product.maintenance_margin is None

    last_trading_rule = product.contract_rules.last_trading_rule

    assert last_trading_rule.period_offset == 0
    assert last_trading_rule.reference_event is ReferenceEvent.BUSINESS_DAY_OF_PERIOD
    assert last_trading_rule.n_reference == -3
    assert last_trading_rule.business_day_offset == 0
    assert last_trading_rule.weekday is None

    first_day_rule = product.contract_rules.first_day_of_interest_rule

    assert first_day_rule.shift_rule.shift_period_type is PeriodType.MONTH
    assert first_day_rule.shift_rule.n_shift["Jan"] == 60
    assert first_day_rule.shift_rule.n_shift["Dec"] == 60
    assert first_day_rule.reference_rule == "next_b_day_after_period"

    metadata = record.metadata

    assert metadata.schema_version == "futures_product.v1"
    assert metadata.source_relative_path == "cme/metals/aluminum.json"
    assert metadata.created_at == date(2026, 6, 23)
    assert metadata.updated_at == date(2026, 6, 23)
    assert metadata.review_status == "draft"
    assert metadata.curator == "mxm"
    assert metadata.source_type == "manual_curation"
    assert metadata.source_accessed_at == date(2026, 6, 23)
    assert metadata.curation_method == (
        "human_interpreted_from_exchange_contract_specs"
    )
    assert metadata.assistance == "llm_assisted_drafting"
    assert len(metadata.notes) == 2
    assert isinstance(
        metadata.notes,
        tuple,
    )

    assert len(metadata.source_digest) == 64
    assert set(metadata.source_digest) <= set("0123456789abcdef")


def test_load_futures_product_parses_nullable_product_fields(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Nullable operational fields remain optional."""

    document = deepcopy(valid_futures_product_json)

    product = document["product"]
    product["trading_hours"] = None
    product["tick_size"] = None
    product["tick_value"] = None
    product["initial_margin"] = None
    product["maintenance_margin"] = None

    record = load_document(
        tmp_path,
        document,
    )

    assert record.product.trading_hours is None
    assert record.product.tick_size is None
    assert record.product.tick_value is None
    assert record.product.initial_margin is None
    assert record.product.maintenance_margin is None


def test_load_futures_product_normalises_empty_optional_string(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Blank optional strings are normalised to None."""

    document = deepcopy(valid_futures_product_json)

    document["product"]["trading_hours"] = "   "

    record = load_document(
        tmp_path,
        document,
    )

    assert record.product.trading_hours is None


def test_load_futures_product_parses_multiple_period_types(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """The source adapter reconstructs all configured period types."""

    document = deepcopy(valid_futures_product_json)

    document["product"]["period_types"] = "MONTH,QUARTER"

    record = load_document(
        tmp_path,
        document,
    )

    assert record.product.period_types == (
        PeriodType.MONTH,
        PeriodType.QUARTER,
    )


def test_load_futures_product_parses_weekday_rule(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Weekday-based last-trading rules retain their weekday."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["last_trading_rule"] = {
        "period_offset": 0,
        "reference_event": "weekday_of_period",
        "n_reference": 3,
        "business_day_offset": 0,
        "weekday": "Friday",
    }

    record = load_document(
        tmp_path,
        document,
    )

    rule = record.product.contract_rules.last_trading_rule

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
def test_load_futures_product_parses_reference_events(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
    raw_event: str,
    expected_event: ReferenceEvent,
) -> None:
    """Supported reference-event values reconstruct domain enums."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["last_trading_rule"]["reference_event"] = raw_event

    record = load_document(
        tmp_path,
        document,
    )

    assert (
        record.product.contract_rules.last_trading_rule.reference_event
        is expected_event
    )


# ---------------------------------------------------------------------
# PRODUCT AND SOURCE-METADATA SEPARATION
# ---------------------------------------------------------------------


def test_metadata_only_change_does_not_change_product(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Curation changes do not alter the operational product."""

    original_document = deepcopy(valid_futures_product_json)
    changed_document = deepcopy(valid_futures_product_json)

    changed_document["source_status"]["review_status"] = "approved"
    changed_document["provenance"]["notes"].append("Reviewed again.")

    original = load_document(
        tmp_path,
        original_document,
        relative_path="original.json",
    )
    changed = load_document(
        tmp_path,
        changed_document,
        relative_path="changed.json",
    )

    assert original.product == changed.product
    assert original.metadata != changed.metadata
    assert original.metadata.review_status == "draft"
    assert changed.metadata.review_status == "approved"
    assert original.metadata.source_digest != changed.metadata.source_digest


def test_operational_change_changes_product_and_digest(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """An operational source change alters the product and source digest."""

    original_document = deepcopy(valid_futures_product_json)
    changed_document = deepcopy(valid_futures_product_json)

    changed_document["product"]["tick_size"] = 0.5

    original = load_document(
        tmp_path,
        original_document,
        relative_path="original.json",
    )
    changed = load_document(
        tmp_path,
        changed_document,
        relative_path="changed.json",
    )

    assert original.product != changed.product
    assert original.product.tick_size == 0.25
    assert changed.product.tick_size == 0.5
    assert original.metadata.source_digest != changed.metadata.source_digest


def test_source_digest_ignores_formatting_and_key_order(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Equivalent JSON documents have equal source-content digests."""

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    first_path.write_text(
        json.dumps(
            valid_futures_product_json,
            indent=2,
        ),
        encoding="utf-8",
    )

    reordered_document = {
        key: valid_futures_product_json[key]
        for key in reversed(valid_futures_product_json)
    }

    second_path.write_text(
        json.dumps(
            reordered_document,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    first = load_futures_product(
        first_path,
        root_dir=tmp_path,
    )
    second = load_futures_product(
        second_path,
        root_dir=tmp_path,
    )

    assert first.product == second.product
    assert first.metadata.source_digest == second.metadata.source_digest


def test_same_document_at_different_paths_has_same_product_and_digest(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Source location is distinct from document-content identity."""

    first = load_document(
        tmp_path,
        deepcopy(valid_futures_product_json),
        relative_path="venue_a/product.json",
    )
    second = load_document(
        tmp_path,
        deepcopy(valid_futures_product_json),
        relative_path="venue_b/product.json",
    )

    assert first.product == second.product
    assert first.metadata.source_digest == second.metadata.source_digest
    assert first.metadata.source_relative_path != second.metadata.source_relative_path


# ---------------------------------------------------------------------
# FILESYSTEM SOURCE BOUNDARY
# ---------------------------------------------------------------------


def test_load_futures_product_rejects_missing_root(
    tmp_path: Path,
) -> None:
    """A source document cannot be loaded without its source root."""

    missing_root = tmp_path / "missing"

    with pytest.raises(
        ValueError,
        match="source root does not exist",
    ):
        load_futures_product(
            missing_root / "product.json",
            root_dir=missing_root,
        )


def test_load_futures_product_rejects_non_directory_root(
    tmp_path: Path,
) -> None:
    """The configured source root must be a directory."""

    root_file = tmp_path / "root.json"
    root_file.write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="source root is not a directory",
    ):
        load_futures_product(
            root_file,
            root_dir=root_file,
        )


def test_load_futures_product_rejects_missing_document(
    tmp_path: Path,
) -> None:
    """The requested source document must exist."""

    with pytest.raises(
        ValueError,
        match="source document does not exist",
    ):
        load_futures_product(
            tmp_path / "missing.json",
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_non_file_document(
    tmp_path: Path,
) -> None:
    """The requested source document cannot be a directory."""

    directory = tmp_path / "product.json"
    directory.mkdir()

    with pytest.raises(
        ValueError,
        match="source document is not a file",
    ):
        load_futures_product(
            directory,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_document_outside_root(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Source-relative identity requires containment below the root."""

    root = tmp_path / "root"
    root.mkdir()

    outside = write_json(
        tmp_path / "outside.json",
        valid_futures_product_json,
    )

    with pytest.raises(
        ValueError,
        match="is not below source root",
    ):
        load_futures_product(
            outside,
            root_dir=root,
        )


def test_load_futures_product_uses_posix_relative_path(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Source paths use stable POSIX separators."""

    record = load_document(
        tmp_path,
        valid_futures_product_json,
        relative_path="cme/metals/aluminum.json",
    )

    assert record.metadata.source_relative_path == "cme/metals/aluminum.json"


# ---------------------------------------------------------------------
# TOP-LEVEL STRUCTURAL VALIDATION
# ---------------------------------------------------------------------


def test_load_futures_product_rejects_non_object_top_level_json(
    tmp_path: Path,
) -> None:
    """The source document must contain a top-level JSON object."""

    file_path = write_json(
        tmp_path / "product.json",
        [
            "not",
            "an",
            "object",
        ],
    )

    with pytest.raises(
        ValueError,
        match="expected top-level JSON object",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


@pytest.mark.parametrize(
    "missing_field",
    [
        "product",
        "source_status",
        "provenance",
        "parsed_rules",
    ],
)
def test_load_futures_product_rejects_missing_top_level_section(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
    missing_field: str,
) -> None:
    """Required nested source-document sections must be objects."""

    document = deepcopy(valid_futures_product_json)
    del document[missing_field]

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match=rf"field '{missing_field}' must be a JSON object",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


@pytest.mark.parametrize(
    "missing_field",
    [
        "schema_version",
        "product_id",
        "asset_class",
    ],
)
def test_load_futures_product_rejects_missing_top_level_string(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
    missing_field: str,
) -> None:
    """Required top-level scalar fields must be present."""

    document = deepcopy(valid_futures_product_json)
    del document[missing_field]

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match=rf"field '{missing_field}' must be a non-empty string",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_non_object_nested_section(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Nested source structures cannot be scalar values."""

    document = deepcopy(valid_futures_product_json)
    document["provenance"] = "not-an-object"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="field 'provenance' must be a JSON object",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


# ---------------------------------------------------------------------
# SCALAR AND ENUM VALIDATION
# ---------------------------------------------------------------------


def test_load_futures_product_rejects_empty_required_string(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Required source strings cannot be blank."""

    document = deepcopy(valid_futures_product_json)
    document["product"]["venue"] = "   "

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="field 'venue' must be a non-empty string",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_invalid_iso_date(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Source dates must use ISO-8601 form."""

    document = deepcopy(valid_futures_product_json)
    document["source_status"]["created_at"] = "23-06-2026"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="must be an ISO date",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


@pytest.mark.parametrize(
    ("field", "value", "error_match"),
    [
        (
            "currency",
            "UNKNOWN",
            "unknown currency",
        ),
        (
            "unit",
            "UNKNOWN",
            "unknown product unit",
        ),
        (
            "settlement",
            "UNKNOWN",
            "unknown settlement method",
        ),
    ],
)
def test_load_futures_product_rejects_unknown_product_enum(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
    field: str,
    value: str,
    error_match: str,
) -> None:
    """Unknown product-level enum values are rejected."""

    document = deepcopy(valid_futures_product_json)
    document["product"][field] = value

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match=error_match,
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_unknown_period_type(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Unknown rule period types are rejected."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["first_day_of_interest_rule"]["shift_rule"][
        "shift_period_type"
    ] = "UNKNOWN"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="unknown period type",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_unknown_reference_event(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Unknown rule reference events are rejected."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["last_trading_rule"]["reference_event"] = "unknown_event"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="unknown reference event",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_invalid_weekday(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Invalid weekday names cannot enter the domain."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["last_trading_rule"] = {
        "period_offset": 0,
        "reference_event": "weekday_of_period",
        "n_reference": 3,
        "business_day_offset": 0,
        "weekday": "Notaday",
    }

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="invalid weekday",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_boolean_integer(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Booleans cannot masquerade as structured-rule integers."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["last_trading_rule"]["period_offset"] = True

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="field 'period_offset' must be an integer",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_non_numeric_product_value(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Required numeric product fields must be JSON numbers."""

    document = deepcopy(valid_futures_product_json)

    document["product"]["contract_size"] = "twenty-five"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="field 'contract_size' must be numeric",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_boolean_numeric_product_value(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Booleans cannot masquerade as product numbers."""

    document = deepcopy(valid_futures_product_json)

    document["product"]["contract_size"] = True

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="field 'contract_size' must be numeric",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_non_string_provenance_note(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Provenance notes must contain only strings."""

    document = deepcopy(valid_futures_product_json)

    document["provenance"]["notes"] = [
        "Valid note",
        123,
    ]

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="field 'notes' must contain only strings",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


@pytest.mark.parametrize(
    "invalid_shift",
    [
        "sixty",
        True,
    ],
)
def test_load_futures_product_rejects_invalid_month_shift(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
    invalid_shift: object,
) -> None:
    """Month-shift mappings accept integers only."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["first_day_of_interest_rule"]["shift_rule"]["n_shift"][
        "Jan"
    ] = invalid_shift

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="shift for 'Jan' must be an integer",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


# ---------------------------------------------------------------------
# CROSS-FIELD AND DOMAIN INVARIANTS
# ---------------------------------------------------------------------


def test_load_futures_product_rejects_missing_weekday_for_weekday_rule(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Weekday reference events require an explicit weekday."""

    document = deepcopy(valid_futures_product_json)

    document["parsed_rules"]["last_trading_rule"] = {
        "period_offset": 0,
        "reference_event": "weekday_of_period",
        "n_reference": 3,
        "business_day_offset": 0,
    }

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="weekday is required",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_mismatched_product_ids(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Top-level and nested product identities must agree."""

    document = deepcopy(valid_futures_product_json)
    document["product_id"] = "different_product"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match=r"top-level product_id .* does not match product.product_id",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


def test_load_futures_product_rejects_invalid_source_date_order(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Updated source records cannot predate their creation."""

    document = deepcopy(valid_futures_product_json)

    document["source_status"]["created_at"] = "2026-07-01"
    document["source_status"]["updated_at"] = "2026-06-23"

    file_path = write_valid_product(
        tmp_path,
        document,
    )

    with pytest.raises(
        ValueError,
        match="updated_at cannot precede created_at",
    ):
        load_futures_product(
            file_path,
            root_dir=tmp_path,
        )


# ---------------------------------------------------------------------
# BULK SOURCE LOADING
# ---------------------------------------------------------------------


def test_load_futures_products_recurses_and_orders_by_path(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Bulk source loading is recursive and deterministic."""

    product_a = deepcopy(valid_futures_product_json)
    set_product_id(
        product_a,
        "product_a",
    )

    product_b = deepcopy(valid_futures_product_json)
    set_product_id(
        product_b,
        "product_b",
    )

    write_valid_product(
        tmp_path,
        product_b,
        relative_path="z/product_b.json",
    )
    write_valid_product(
        tmp_path,
        product_a,
        relative_path="a/product_a.json",
    )

    records = load_futures_products(tmp_path)

    assert [record.metadata.source_relative_path for record in records] == [
        "a/product_a.json",
        "z/product_b.json",
    ]

    assert [record.product.product_id for record in records] == [
        "product_a",
        "product_b",
    ]


def test_load_futures_products_rejects_duplicate_product_ids(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Two source documents cannot define the same product identity."""

    write_valid_product(
        tmp_path,
        deepcopy(valid_futures_product_json),
        relative_path="venue_a/product.json",
    )
    write_valid_product(
        tmp_path,
        deepcopy(valid_futures_product_json),
        relative_path="venue_b/product.json",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate futures product for product_id",
    ) as exc_info:
        load_futures_products(tmp_path)

    error = str(exc_info.value)

    assert "venue_a/product.json" in error
    assert "venue_b/product.json" in error


def test_load_futures_products_rejects_missing_root(
    tmp_path: Path,
) -> None:
    """Bulk loading requires an existing source root."""

    missing_root = tmp_path / "does-not-exist"

    with pytest.raises(
        ValueError,
        match="source root does not exist",
    ):
        load_futures_products(missing_root)


def test_load_futures_products_rejects_non_directory_root(
    tmp_path: Path,
) -> None:
    """Bulk loading requires a directory source root."""

    file_path = tmp_path / "not-a-directory.json"
    file_path.write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="source root is not a directory",
    ):
        load_futures_products(file_path)


def test_load_futures_products_rejects_empty_directory(
    tmp_path: Path,
) -> None:
    """The source universe must contain at least one JSON document."""

    with pytest.raises(
        ValueError,
        match="No futures-product JSON files found",
    ):
        load_futures_products(tmp_path)


def test_load_futures_products_ignores_non_json_files(
    tmp_path: Path,
    valid_futures_product_json: dict[str, Any],
) -> None:
    """Only JSON documents participate in source-universe loading."""

    write_valid_product(
        tmp_path,
        valid_futures_product_json,
        relative_path="product.json",
    )

    (tmp_path / "README.md").write_text(
        "Source notes",
        encoding="utf-8",
    )

    records = load_futures_products(tmp_path)

    assert len(records) == 1
    assert records[0].product.product_id == "comex_aluminum_futures"


# ---------------------------------------------------------------------
# GIT SOURCE-REVISION RESOLUTION
# ---------------------------------------------------------------------


def test_resolve_source_revision_returns_full_git_revision(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """The source adapter resolves and validates the full Git HEAD."""

    calls: list[
        tuple[
            list[str],
            dict[str, object],
        ]
    ] = []

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            (
                command,
                kwargs,
            )
        )

        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=("a" * 40) + "\n",
            stderr="",
        )

    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        fake_run,
    )

    revision = resolve_futures_product_source_revision(tmp_path)

    assert revision == "a" * 40

    assert len(calls) == 1

    command, kwargs = calls[0]

    assert command == [
        "git",
        "-C",
        str(tmp_path.resolve()),
        "rev-parse",
        "--verify",
        "HEAD",
    ]

    assert kwargs == {
        "check": False,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
    }


def test_resolve_source_revision_strips_and_normalises_output(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Git output is stripped and normalised to lowercase."""

    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=("ABCDEF" * 6) + "ABCD\n",
            stderr="",
        )

    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        fake_run,
    )

    revision = resolve_futures_product_source_revision(tmp_path)

    assert revision == (("abcdef" * 6) + "abcd")


def test_resolve_source_revision_rejects_missing_root(
    tmp_path: Path,
) -> None:
    """Revision resolution requires an existing source root."""

    missing_root = tmp_path / "missing"

    with pytest.raises(
        FuturesProductSourceRevisionError,
        match="source root does not exist",
    ):
        resolve_futures_product_source_revision(missing_root)


def test_resolve_source_revision_rejects_non_directory_root(
    tmp_path: Path,
) -> None:
    """Revision resolution requires a directory source root."""

    file_path = tmp_path / "source.json"
    file_path.write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        FuturesProductSourceRevisionError,
        match="source root is not a directory",
    ):
        resolve_futures_product_source_revision(file_path)


def test_resolve_source_revision_reports_git_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Git diagnostics are preserved when revision resolution fails."""

    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository\n",
        )

    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(
        FuturesProductSourceRevisionError,
        match="fatal: not a git repository",
    ):
        resolve_futures_product_source_revision(tmp_path)


def test_resolve_source_revision_handles_empty_git_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A failed Git process without stderr still yields a useful error."""

    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=128,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(
        FuturesProductSourceRevisionError,
        match="git rev-parse failed",
    ):
        resolve_futures_product_source_revision(tmp_path)


def test_resolve_source_revision_wraps_os_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """An unavailable Git executable is translated to a source error."""

    def fake_run(
        _: list[str],
        **__: object,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(
        FuturesProductSourceRevisionError,
        match="Could not execute Git",
    ):
        resolve_futures_product_source_revision(tmp_path)


@pytest.mark.parametrize(
    "git_output",
    [
        "",
        "a" * 39,
        "a" * 41,
        "g" * 40,
    ],
)
def test_resolve_source_revision_rejects_invalid_git_output(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    git_output: str,
) -> None:
    """Git must return one full 40-character hexadecimal revision."""

    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=git_output,
            stderr="",
        )

    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(
        FuturesProductSourceRevisionError,
        match=("Git returned an invalid futures-product source revision"),
    ):
        resolve_futures_product_source_revision(tmp_path)
