"""Parse curated MXM futures product specifications from JSON.

Each JSON file represents one complete FuturesProductSpec containing:

- the exchange-defined FuturesProduct;
- MXM source lifecycle metadata;
- provenance;
- structured contract-construction rules.

The parser treats dictionaries returned by ``json.load`` as an untrusted
external representation and reconstructs typed domain objects immediately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.periods import PeriodType
from mxm.refdata.models.products.futures_product import (
    FuturesProduct,
    SettlementMethod,
)
from mxm.refdata.models.products.futures_product_spec import (
    ContractRules,
    FirstDayOfInterestRule,
    FirstDayOfInterestShiftRule,
    FuturesProductProvenance,
    FuturesProductSourceStatus,
    FuturesProductSpec,
    LastTradingRule,
)
from mxm.refdata.models.reference_events import ReferenceEvent
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.models.weekdays import Weekday
from mxm.refdata.utils.period_types_codec import decode_period_types
from mxm.types import JSONObj, JSONValue


@dataclass(frozen=True)
class LoadedFuturesProductSpec:
    """One validated futures-product specification with source identity."""

    specification: FuturesProductSpec
    source_relative_path: str
    canonical_document: JSONObj
    specification_digest: str


# ---------------------------------------------------------------------
# JSON BOUNDARY HELPERS
# ---------------------------------------------------------------------


def _load_json_object(file_path: Path) -> JSONObj:
    """Load a JSON file and require a top-level object."""

    with file_path.open("r", encoding="utf-8") as file:
        raw: JSONValue = json.load(file)

    if not isinstance(raw, dict):
        raise ValueError(
            "Invalid futures product specification: "
            f"expected top-level JSON object in {file_path}"
        )

    return raw


def _canonicalise_json_object(
    document: JSONObj,
) -> tuple[JSONObj, str]:
    """Return a canonical JSON document and its SHA-256 content digest."""

    canonical_json = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    canonical_value: JSONValue = json.loads(canonical_json)

    if not isinstance(canonical_value, dict):
        raise AssertionError("Canonical JSON object unexpectedly became non-object")

    specification_digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return canonical_value, specification_digest


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
    """Return an optional string, normalising empty strings to None."""

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
    """Return a required JSON number as float."""

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
    """Return an optional JSON number as float."""

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

    value = _require_str(data, field, context=context)

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
    try:
        return Currency[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown currency {value!r}") from exc


def _parse_product_unit(
    value: str,
    *,
    context: str,
) -> ProductUnit:
    try:
        return ProductUnit[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown product unit {value!r}") from exc


def _parse_settlement_method(
    value: str,
    *,
    context: str,
) -> SettlementMethod:
    try:
        return SettlementMethod[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown settlement method {value!r}") from exc


def _parse_period_type(
    value: str,
    *,
    context: str,
) -> PeriodType:
    try:
        return PeriodType[value]
    except KeyError as exc:
        raise ValueError(f"{context}: unknown period type {value!r}") from exc


def _parse_reference_event(
    value: str,
    *,
    context: str,
) -> ReferenceEvent:
    try:
        return ReferenceEvent(value)
    except ValueError as exc:
        raise ValueError(f"{context}: unknown reference event {value!r}") from exc


def _parse_weekday(
    value: str,
    *,
    context: str,
) -> Weekday:
    try:
        return Weekday.from_str(value)
    except ValueError as exc:
        raise ValueError(f"{context}: invalid weekday {value!r}") from exc


# ---------------------------------------------------------------------
# FUTURES PRODUCT
# ---------------------------------------------------------------------


def _parse_futures_product(
    data: JSONObj,
    *,
    context: str,
) -> FuturesProduct:
    """Construct the exchange-defined FuturesProduct."""

    period_types_raw = _require_str(
        data,
        "period_types",
        context=context,
    )

    try:
        period_types = decode_period_types(period_types_raw)
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"{context}: invalid period_types {period_types_raw!r}"
        ) from exc

    return FuturesProduct(
        product_id=_require_str(
            data,
            "product_id",
            context=context,
        ),
        venue=_require_str(
            data,
            "venue",
            context=context,
        ),
        description=_require_str(
            data,
            "description",
            context=context,
        ),
        currency=_parse_currency(
            _require_str(data, "currency", context=context),
            context=f"{context}.currency",
        ),
        unit=_parse_product_unit(
            _require_str(data, "unit", context=context),
            context=f"{context}.unit",
        ),
        contract_size=_require_number(
            data,
            "contract_size",
            context=context,
        ),
        valid_period_rule=_require_str(
            data,
            "valid_period_rule",
            context=context,
        ),
        listing_rule=_require_str(
            data,
            "listing_rule",
            context=context,
        ),
        period_types=period_types,
        settlement=_parse_settlement_method(
            _require_str(data, "settlement", context=context),
            context=f"{context}.settlement",
        ),
        last_trading_rule=_require_str(
            data,
            "last_trading_rule",
            context=context,
        ),
        expiry_rule=_require_str(
            data,
            "expiry_rule",
            context=context,
        ),
        trading_calendar=_require_str(
            data,
            "trading_calendar",
            context=context,
        ),
        trading_hours=_optional_str(
            data,
            "trading_hours",
            context=context,
        ),
        tick_size=_optional_number(
            data,
            "tick_size",
            context=context,
        ),
        tick_value=_optional_number(
            data,
            "tick_value",
            context=context,
        ),
        initial_margin=_optional_number(
            data,
            "initial_margin",
            context=context,
        ),
        maintenance_margin=_optional_number(
            data,
            "maintenance_margin",
            context=context,
        ),
    )


# ---------------------------------------------------------------------
# SOURCE STATUS AND PROVENANCE
# ---------------------------------------------------------------------


def _parse_source_status(
    data: JSONObj,
    *,
    context: str,
) -> FuturesProductSourceStatus:
    """Construct source lifecycle metadata."""

    return FuturesProductSourceStatus(
        created_at=_require_date(
            data,
            "created_at",
            context=context,
        ),
        updated_at=_require_date(
            data,
            "updated_at",
            context=context,
        ),
        review_status=_require_str(
            data,
            "review_status",
            context=context,
        ),
        curator=_require_str(
            data,
            "curator",
            context=context,
        ),
    )


def _parse_provenance(
    data: JSONObj,
    *,
    context: str,
) -> FuturesProductProvenance:
    """Construct product-specification provenance."""

    return FuturesProductProvenance(
        source_type=_require_str(
            data,
            "source_type",
            context=context,
        ),
        source_url=_require_str(
            data,
            "source_url",
            context=context,
        ),
        source_accessed_at=_require_date(
            data,
            "source_accessed_at",
            context=context,
        ),
        curation_method=_require_str(
            data,
            "curation_method",
            context=context,
        ),
        assistance=_require_str(
            data,
            "assistance",
            context=context,
        ),
        notes=_require_str_tuple(
            data,
            "notes",
            context=context,
        ),
    )


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
    """Construct the period-shift part of a first-day-of-interest rule."""

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
    """Construct a last-trading-day rule."""

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
    """Construct all contract-construction rules."""

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
# SPECIFICATION DOCUMENT CONSTRUCTION
# ---------------------------------------------------------------------


def _parse_futures_product_spec_document(
    raw: JSONObj,
    *,
    context: str,
) -> FuturesProductSpec:
    """Reconstruct a typed specification from a loaded JSON object."""

    product_data = _require_object(
        raw,
        "product",
        context=context,
    )
    source_status_data = _require_object(
        raw,
        "source_status",
        context=context,
    )
    provenance_data = _require_object(
        raw,
        "provenance",
        context=context,
    )
    parsed_rules_data = _require_object(
        raw,
        "parsed_rules",
        context=context,
    )

    product = _parse_futures_product(
        product_data,
        context=f"{context}.product",
    )

    return FuturesProductSpec(
        schema_version=_require_str(
            raw,
            "schema_version",
            context=context,
        ),
        product_id=_require_str(
            raw,
            "product_id",
            context=context,
        ),
        asset_class=_require_str(
            raw,
            "asset_class",
            context=context,
        ),
        source_status=_parse_source_status(
            source_status_data,
            context=f"{context}.source_status",
        ),
        provenance=_parse_provenance(
            provenance_data,
            context=f"{context}.provenance",
        ),
        product=product,
        contract_rules=_parse_contract_rules(
            parsed_rules_data,
            context=f"{context}.parsed_rules",
        ),
    )


# ---------------------------------------------------------------------
# PUBLIC LOADING AND PARSING API
# ---------------------------------------------------------------------


def load_futures_product_spec(
    file_path: Path,
    *,
    root_dir: Path,
) -> LoadedFuturesProductSpec:
    """Load one specification together with stable source identity."""

    root = root_dir.expanduser().resolve()
    path = file_path.expanduser().resolve()

    try:
        source_relative_path = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Futures product specification {path} is not below source root {root}"
        ) from exc

    raw = _load_json_object(path)
    canonical_document, specification_digest = _canonicalise_json_object(raw)
    specification = _parse_futures_product_spec_document(
        canonical_document,
        context=str(path),
    )

    return LoadedFuturesProductSpec(
        specification=specification,
        source_relative_path=source_relative_path,
        canonical_document=canonical_document,
        specification_digest=specification_digest,
    )


def load_futures_product_specs(
    root_dir: Path,
) -> list[LoadedFuturesProductSpec]:
    """Recursively load all specifications below a source root."""

    root = root_dir.expanduser().resolve()

    if not root.exists():
        raise ValueError(f"Futures product JSON root does not exist: {root}")

    if not root.is_dir():
        raise ValueError(f"Futures product JSON root is not a directory: {root}")

    file_paths = sorted(root.rglob("*.json"))

    if not file_paths:
        raise ValueError(f"No futures product JSON files found below: {root}")

    loaded_specs = [
        load_futures_product_spec(
            file_path,
            root_dir=root,
        )
        for file_path in file_paths
    ]

    seen_product_ids: set[str] = set()

    for loaded_spec in loaded_specs:
        product_id = loaded_spec.specification.product_id

        if product_id in seen_product_ids:
            raise ValueError(
                f"Duplicate futures product specification for product_id {product_id!r}"
            )

        seen_product_ids.add(product_id)

    return loaded_specs


def parse_futures_product_spec(
    file_path: Path,
) -> FuturesProductSpec:
    """Parse one curated futures-product JSON document."""

    path = file_path.expanduser()
    raw = _load_json_object(path)

    return _parse_futures_product_spec_document(
        raw,
        context=str(path),
    )


def parse_futures_product_specs(
    root_dir: Path,
) -> list[FuturesProductSpec]:
    """Recursively parse all futures-product JSON files below a root."""

    return [
        loaded_spec.specification
        for loaded_spec in load_futures_product_specs(root_dir)
    ]


def build_futures_products(
    root_dir: Path,
) -> list[FuturesProduct]:
    """Build exchange-defined products from curated specifications."""

    return [spec.product for spec in parse_futures_product_specs(root_dir)]
