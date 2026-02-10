from __future__ import annotations

from mxm_refdata.models.periods import PeriodType


def encode_period_types(values: tuple[PeriodType, ...]) -> str:
    if not values:
        raise ValueError("period_types must be non-empty")
    return ",".join(v.name for v in values)


def decode_period_types(value: str) -> tuple[PeriodType, ...]:
    parts = [p.strip() for p in value.replace("|", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError(f"invalid period_types string: {value!r}")
    return tuple(PeriodType[p] for p in parts)
