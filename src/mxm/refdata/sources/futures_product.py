"""Source-provider API for curated futures products.

This module reads futures-product source documents and returns:

- one complete operational ``FuturesProduct`` domain object;
- source and curation metadata describing the input record.

The source-document representation remains private to this adapter. Callers do
not receive raw or canonical JSON documents.

Repository revision is source-snapshot metadata and is resolved separately from
the individual product records.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProduct,
    LastTradingRule,
)
from mxm.refdata.models.products.settlement import SettlementMethod
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.utils.period_types_codec import decode_period_types
from mxm.types import JSONObj, JSONValue

_SOURCE_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class FuturesProductSourceMetadata:
    """Source and curation metadata for one futures product.

    These values describe the source artifact and curation process. They are
    not part of the operational ``FuturesProduct`` definition.
    """

    schema_version: str
    source_relative_path: str
    source_digest: str

    created_at: date
    updated_at: date
    review_status: str
    curator: str

    source_type: str
    source_url: str
    source_accessed_at: date
    curation_method: str
    assistance: str
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate source-metadata invariants."""

        if not self.schema_version:
            raise ValueError(
                "FuturesProductSourceMetadata.schema_version must be non-empty"
            )

        if not self.source_relative_path:
            raise ValueError(
                "FuturesProductSourceMetadata.source_relative_path must be non-empty"
            )

        if not _SOURCE_DIGEST_PATTERN.fullmatch(self.source_digest):
            raise ValueError(
                "FuturesProductSourceMetadata.source_digest must be a "
                "64-character lowercase hexadecimal SHA-256 digest"
            )

        if self.updated_at < self.created_at:
            raise ValueError(
                "FuturesProductSourceMetadata.updated_at cannot precede created_at"
            )


@dataclass(frozen=True)
class FuturesProductSourceRecord:
    """One futures product returned by the configured source provider."""

    product: FuturesProduct
    metadata: FuturesProductSourceMetadata


class FuturesProductSourceRevisionError(RuntimeError):
    """Raised when the futures-product source revision cannot be resolved."""


# ---------------------------------------------------------------------
# JSON BOUNDARY HELPERS
# ---------------------------------------------------------------------


def _load_json_object(
    file_path: Path,
) -> JSONObj:
    """Load a JSON file and require a top-level object."""

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        raw: JSONValue = json.load(file)

    if not isinstance(raw, dict):
        raise ValueError(
            "Invalid futures-product source document: "
            f"expected top-level JSON object in {file_path}"
        )

    return raw


def _calculate_source_digest(
    document: JSONObj,
) -> str:
    """Return a deterministic SHA-256 digest of one JSON document."""

    canonical_json = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _require_object(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> JSONObj:
    """Return a required nested JSON object."""

    value = data.get(field)

    if not isinstance(value, dict):
        raise ValueError(f"{context}: field {field!r} must be a JSON object")

    return value


def _require_str(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> str:
    """Return a required non-empty string."""

    value = data.get(field)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: field {field!r} must be a non-empty string")

    return value.strip()


def _optional_str(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> str | None:
    """Return an optional string, normalising an empty string to ``None``."""

    value = data.get(field)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{context}: field {field!r} must be a string or null")

    return value.strip() or None


def _require_int(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> int:
    """Return a required integer."""

    value = data.get(field)

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}: field {field!r} must be an integer")

    return value


def _require_number(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> float:
    """Return a required JSON number as a float."""

    value = data.get(field)

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context}: field {field!r} must be numeric")

    return float(value)


def _optional_number(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> float | None:
    """Return an optional JSON number as a float."""

    value = data.get(field)

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context}: field {field!r} must be numeric or null")

    return float(value)


def _require_date(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> date:
    """Return a required ISO-8601 date."""

    value = _require_str(
        data,
        field,
        context=context,
    )

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{context}: field {field!r} must be an ISO date, got {value!r}"
        ) from exc


def _require_str_tuple(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> tuple[str, ...]:
    """Return a required JSON string array as an immutable tuple."""

    value = data.get(field)

    if not isinstance(value, list):
        raise ValueError(f"{context}: field {field!r} must be a JSON array")

    items: list[str] = []

    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{context}: field {field!r} must contain only strings")

        items.append(item)

    return tuple(items)


# ---------------------------------------------------------------------
# ENUM AND VALUE-OBJECT CONSTRUCTION
# ---------------------------------------------------------------------


def _parse_currency(
    value: str,
    *,
    context: str,
) -> Currency:
    """Parse a currency enum name."""

    try:
        return Currency[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown currency {value!r}") from exc


def _parse_product_unit(
    value: str,
    *,
    context: str,
) -> ProductUnit:
    """Parse a product-unit enum name."""

    try:
        return ProductUnit[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown product unit {value!r}") from exc


def _parse_settlement_method(
    value: str,
    *,
    context: str,
) -> SettlementMethod:
    """Parse a settlement-method enum name."""

    try:
        return SettlementMethod[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown settlement method {value!r}") from exc


def _parse_period_type(
    value: str,
    *,
    context: str,
) -> PeriodType:
    """Parse a period-type enum name."""

    try:
        return PeriodType[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown period type {value!r}") from exc


def _parse_reference_event(
    value: str,
    *,
    context: str,
) -> ReferenceEvent:
    """Parse a reference-event value."""

    try:
        return ReferenceEvent(value)
    except ValueError as exc:
        raise ValueError(f"{context}: unknown reference event {value!r}") from exc


def _parse_weekday(
    value: str,
    *,
    context: str,
) -> Weekday:
    """Parse a weekday value."""

    try:
        return Weekday.from_str(value)
    except ValueError as exc:
        raise ValueError(f"{context}: invalid weekday {value!r}") from exc


# ---------------------------------------------------------------------
# CONTRACT RULES
# ---------------------------------------------------------------------


def _parse_shift_mapping(
    data: JSONObj,
    field: str,
    *,
    context: str,
) -> dict[str, int]:
    """Parse a month-name-to-period-shift mapping."""

    value = data.get(field)

    if not isinstance(value, dict):
        raise ValueError(f"{context}: field {field!r} must be a JSON object")

    shifts: dict[str, int] = {}

    for month, shift in value.items():
        if isinstance(shift, bool) or not isinstance(shift, int):
            raise ValueError(f"{context}: shift for {month!r} must be an integer")

        shifts[month] = shift

    return shifts


def _parse_first_day_of_interest_shift_rule(
    data: JSONObj,
    *,
    context: str,
) -> FirstDayOfInterestShiftRule:
    """Construct the period-shift rule for first day of interest."""

    return FirstDayOfInterestShiftRule(
        shift_period_type=_parse_period_type(
            _require_str(
                data,
                "shift_period_type",
                context=context,
            ),
            context=f"{context}.shift_period_type",
        ),
        n_shift=_parse_shift_mapping(
            data,
            "n_shift",
            context=context,
        ),
    )


def _parse_first_day_of_interest_rule(
    data: JSONObj,
    *,
    context: str,
) -> FirstDayOfInterestRule:
    """Construct a first-day-of-interest rule."""

    shift_rule_data = _require_object(
        data,
        "shift_rule",
        context=context,
    )

    return FirstDayOfInterestRule(
        shift_rule=_parse_first_day_of_interest_shift_rule(
            shift_rule_data,
            context=f"{context}.shift_rule",
        ),
        reference_rule=_require_str(
            data,
            "reference_rule",
            context=context,
        ),
    )


def _parse_last_trading_rule(
    data: JSONObj,
    *,
    context: str,
) -> LastTradingRule:
    """Construct a structured last-trading-day rule."""

    reference_event = _parse_reference_event(
        _require_str(
            data,
            "reference_event",
            context=context,
        ),
        context=f"{context}.reference_event",
    )

    weekday_raw = _optional_str(
        data,
        "weekday",
        context=context,
    )

    weekday = (
        _parse_weekday(
            weekday_raw,
            context=f"{context}.weekday",
        )
        if weekday_raw is not None
        else None
    )

    return LastTradingRule(
        period_offset=_require_int(
            data,
            "period_offset",
            context=context,
        ),
        reference_event=reference_event,
        n_reference=_require_int(
            data,
            "n_reference",
            context=context,
        ),
        business_day_offset=_require_int(
            data,
            "business_day_offset",
            context=context,
        ),
        weekday=weekday,
    )


def _parse_contract_rules(
    data: JSONObj,
    *,
    context: str,
) -> ContractRules:
    """Construct all contract-generation rules."""

    last_trading_rule_data = _require_object(
        data,
        "last_trading_rule",
        context=context,
    )

    first_day_of_interest_rule_data = _require_object(
        data,
        "first_day_of_interest_rule",
        context=context,
    )

    return ContractRules(
        last_trading_rule=_parse_last_trading_rule(
            last_trading_rule_data,
            context=f"{context}.last_trading_rule",
        ),
        first_day_of_interest_rule=(
            _parse_first_day_of_interest_rule(
                first_day_of_interest_rule_data,
                context=(f"{context}.first_day_of_interest_rule"),
            )
        ),
    )


# ---------------------------------------------------------------------
# FUTURES PRODUCT
# ---------------------------------------------------------------------


def _parse_futures_product(
    document: JSONObj,
    *,
    context: str,
) -> FuturesProduct:
    """Construct one complete operational futures product."""

    top_level_product_id = _require_str(
        document,
        "product_id",
        context=context,
    )

    asset_class = _require_str(
        document,
        "asset_class",
        context=context,
    )

    product_data = _require_object(
        document,
        "product",
        context=context,
    )

    parsed_rules_data = _require_object(
        document,
        "parsed_rules",
        context=context,
    )

    nested_product_id = _require_str(
        product_data,
        "product_id",
        context=f"{context}.product",
    )

    if top_level_product_id != nested_product_id:
        raise ValueError(
            f"{context}: top-level product_id "
            f"{top_level_product_id!r} does not match "
            f"product.product_id {nested_product_id!r}"
        )

    period_types_raw = _require_str(
        product_data,
        "period_types",
        context=f"{context}.product",
    )

    try:
        period_types = decode_period_types(period_types_raw)
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"{context}.product: invalid period_types {period_types_raw!r}"
        ) from exc

    return FuturesProduct(
        product_id=nested_product_id,
        asset_class=asset_class,
        venue=_require_str(
            product_data,
            "venue",
            context=f"{context}.product",
        ),
        description=_require_str(
            product_data,
            "description",
            context=f"{context}.product",
        ),
        currency=_parse_currency(
            _require_str(
                product_data,
                "currency",
                context=f"{context}.product",
            ),
            context=f"{context}.product.currency",
        ),
        unit=_parse_product_unit(
            _require_str(
                product_data,
                "unit",
                context=f"{context}.product",
            ),
            context=f"{context}.product.unit",
        ),
        contract_size=_require_number(
            product_data,
            "contract_size",
            context=f"{context}.product",
        ),
        valid_period_rule=_require_str(
            product_data,
            "valid_period_rule",
            context=f"{context}.product",
        ),
        listing_rule=_require_str(
            product_data,
            "listing_rule",
            context=f"{context}.product",
        ),
        period_types=period_types,
        settlement=_parse_settlement_method(
            _require_str(
                product_data,
                "settlement",
                context=f"{context}.product",
            ),
            context=f"{context}.product.settlement",
        ),
        last_trading_rule=_require_str(
            product_data,
            "last_trading_rule",
            context=f"{context}.product",
        ),
        expiry_rule=_require_str(
            product_data,
            "expiry_rule",
            context=f"{context}.product",
        ),
        trading_calendar=_require_str(
            product_data,
            "trading_calendar",
            context=f"{context}.product",
        ),
        contract_rules=_parse_contract_rules(
            parsed_rules_data,
            context=f"{context}.parsed_rules",
        ),
        trading_hours=_optional_str(
            product_data,
            "trading_hours",
            context=f"{context}.product",
        ),
        tick_size=_optional_number(
            product_data,
            "tick_size",
            context=f"{context}.product",
        ),
        tick_value=_optional_number(
            product_data,
            "tick_value",
            context=f"{context}.product",
        ),
        initial_margin=_optional_number(
            product_data,
            "initial_margin",
            context=f"{context}.product",
        ),
        maintenance_margin=_optional_number(
            product_data,
            "maintenance_margin",
            context=f"{context}.product",
        ),
    )


# ---------------------------------------------------------------------
# SOURCE METADATA
# ---------------------------------------------------------------------


def _parse_source_metadata(
    document: JSONObj,
    *,
    source_relative_path: str,
    source_digest: str,
    context: str,
) -> FuturesProductSourceMetadata:
    """Construct source metadata for one futures product."""

    source_status_data = _require_object(
        document,
        "source_status",
        context=context,
    )

    provenance_data = _require_object(
        document,
        "provenance",
        context=context,
    )

    return FuturesProductSourceMetadata(
        schema_version=_require_str(
            document,
            "schema_version",
            context=context,
        ),
        source_relative_path=source_relative_path,
        source_digest=source_digest,
        created_at=_require_date(
            source_status_data,
            "created_at",
            context=f"{context}.source_status",
        ),
        updated_at=_require_date(
            source_status_data,
            "updated_at",
            context=f"{context}.source_status",
        ),
        review_status=_require_str(
            source_status_data,
            "review_status",
            context=f"{context}.source_status",
        ),
        curator=_require_str(
            source_status_data,
            "curator",
            context=f"{context}.source_status",
        ),
        source_type=_require_str(
            provenance_data,
            "source_type",
            context=f"{context}.provenance",
        ),
        source_url=_require_str(
            provenance_data,
            "source_url",
            context=f"{context}.provenance",
        ),
        source_accessed_at=_require_date(
            provenance_data,
            "source_accessed_at",
            context=f"{context}.provenance",
        ),
        curation_method=_require_str(
            provenance_data,
            "curation_method",
            context=f"{context}.provenance",
        ),
        assistance=_require_str(
            provenance_data,
            "assistance",
            context=f"{context}.provenance",
        ),
        notes=_require_str_tuple(
            provenance_data,
            "notes",
            context=f"{context}.provenance",
        ),
    )


# ---------------------------------------------------------------------
# PUBLIC SOURCE API
# ---------------------------------------------------------------------


def load_futures_product(
    file_path: Path,
    *,
    root_dir: Path,
) -> FuturesProductSourceRecord:
    """Load one futures product and its source metadata."""

    root = root_dir.expanduser().resolve()
    path = file_path.expanduser().resolve()

    if not root.exists():
        raise ValueError(f"Futures-product source root does not exist: {root}")

    if not root.is_dir():
        raise ValueError(f"Futures-product source root is not a directory: {root}")

    if not path.exists():
        raise ValueError(f"Futures-product source document does not exist: {path}")

    if not path.is_file():
        raise ValueError(f"Futures-product source document is not a file: {path}")

    try:
        source_relative_path = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Futures-product source document {path} is not below source root {root}"
        ) from exc

    document = _load_json_object(path)
    source_digest = _calculate_source_digest(document)

    context = str(path)

    return FuturesProductSourceRecord(
        product=_parse_futures_product(
            document,
            context=context,
        ),
        metadata=_parse_source_metadata(
            document,
            source_relative_path=source_relative_path,
            source_digest=source_digest,
            context=context,
        ),
    )


def load_futures_products(
    root_dir: Path,
) -> list[FuturesProductSourceRecord]:
    """Load the complete futures-product universe below a source root."""

    root = root_dir.expanduser().resolve()

    if not root.exists():
        raise ValueError(f"Futures-product source root does not exist: {root}")

    if not root.is_dir():
        raise ValueError(f"Futures-product source root is not a directory: {root}")

    file_paths = sorted(root.rglob("*.json"))

    if not file_paths:
        raise ValueError(f"No futures-product JSON files found below: {root}")

    records = [
        load_futures_product(
            file_path,
            root_dir=root,
        )
        for file_path in file_paths
    ]

    seen_product_paths: dict[str, str] = {}

    for record in records:
        product_id = record.product.product_id
        source_relative_path = record.metadata.source_relative_path

        existing_path = seen_product_paths.get(product_id)

        if existing_path is not None:
            raise ValueError(
                "Duplicate futures product for product_id "
                f"{product_id!r}: "
                f"{existing_path!r} and "
                f"{source_relative_path!r}"
            )

        seen_product_paths[product_id] = source_relative_path

    return records


def resolve_futures_product_source_revision(
    root_dir: Path,
) -> str:
    """Return the full Git HEAD revision containing the source root.

    This function identifies the committed repository snapshot. Whether
    materialisation also requires a clean working tree is a separate policy
    decision and is intentionally not enforced here.
    """

    root = root_dir.expanduser().resolve()

    if not root.exists():
        raise FuturesProductSourceRevisionError(
            f"Futures-product source root does not exist: {root}"
        )

    if not root.is_dir():
        raise FuturesProductSourceRevisionError(
            f"Futures-product source root is not a directory: {root}"
        )

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "rev-parse",
                "--verify",
                "HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise FuturesProductSourceRevisionError(
            "Could not execute Git while resolving futures-product "
            f"source revision for {root}"
        ) from exc

    if result.returncode != 0:
        error = result.stderr.strip()

        raise FuturesProductSourceRevisionError(
            "Could not resolve futures-product source revision for "
            f"{root}: {error or 'git rev-parse failed'}"
        )

    revision = result.stdout.strip().lower()

    if not _GIT_REVISION_PATTERN.fullmatch(revision):
        raise FuturesProductSourceRevisionError(
            "Git returned an invalid futures-product source revision "
            f"for {root}: {revision!r}"
        )

    return revision
