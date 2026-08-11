"""Pure generation of calendar periods."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from mxm.refdata.models.months import Month
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.utils.regex_patterns import (
    PERIOD_TYPE_PARSING_MAP,
)

__all__ = [
    "generate_periods",
    "period_containing",
    "period_from_id",
    "shift_period_by_n",
]


def generate_periods(
    start_date: date,
    end_date: date,
    period_types: Iterable[PeriodType],
    *,
    include_partial_end_period: bool = False,
) -> list[Period]:
    """Generate calendar periods over an inclusive date range.

    Periods are grouped in the order supplied by ``period_types``. Within each
    type, periods are returned chronologically.

    The period containing ``start_date`` is included even when it begins before
    ``start_date``.

    By default, a final period extending beyond ``end_date`` is excluded.
    Set ``include_partial_end_period`` to include that trailing partial period.

    Args:
        start_date:
            First date covered by the requested range.
        end_date:
            Last date covered by the requested range.
        period_types:
            Period types to generate, in the desired output order.
        include_partial_end_period:
            Whether to include a final period whose last date is after
            ``end_date``.

    Returns:
        The generated immutable ``Period`` values.

    Raises:
        ValueError:
            If the date range is invalid, no period types are supplied,
            period types are repeated, or a period type is unsupported.
    """

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")

    selected_period_types = tuple(period_types)

    if not selected_period_types:
        raise ValueError("period_types must be non-empty")

    if len(set(selected_period_types)) != len(selected_period_types):
        raise ValueError("period_types must not contain duplicates")

    periods: list[Period] = []

    for period_type in selected_period_types:
        current_period = period_containing(
            start_date,
            period_type,
        )

        while current_period.first_date <= end_date:
            if current_period.last_date > end_date and not include_partial_end_period:
                break

            periods.append(current_period)

            current_period = period_containing(
                current_period.last_date + timedelta(days=1),
                period_type,
            )

    return periods


def shift_period_by_n(
    period: Period,
    n: int,
) -> Period:
    """Shift a period by ``n`` instances of its period type.

    Positive values move forward and negative values move backward. The
    returned period is a newly constructed immutable value; no interning or
    caching is performed.
    """

    shifted_date = _shift_date_by_n_periods(
        period.first_date,
        period.period_type,
        n,
    )

    return period_containing(
        shifted_date,
        period.period_type,
    )


def _shift_date_by_n_periods(
    value: date,
    period_type: PeriodType,
    n: int,
) -> date:
    """Shift a date by whole instances of one period type."""

    if period_type is PeriodType.YEAR:
        return date(
            value.year + n,
            1,
            1,
        )

    if period_type is PeriodType.MONTH:
        month_index = value.year * 12 + value.month - 1 + n

        year, zero_based_month = divmod(
            month_index,
            12,
        )

        return date(
            year,
            zero_based_month + 1,
            1,
        )

    if period_type is PeriodType.QUARTER:
        current_quarter = (value.month - 1) // 3

        quarter_index = value.year * 4 + current_quarter + n

        year, zero_based_quarter = divmod(
            quarter_index,
            4,
        )

        return date(
            year,
            zero_based_quarter * 3 + 1,
            1,
        )

    if period_type is PeriodType.WEEK:
        return value + timedelta(
            weeks=n,
        )

    raise ValueError(f"Unsupported period type: {period_type}")


def period_containing(
    value: date,
    period_type: PeriodType,
) -> Period:
    """Construct the period of ``period_type`` containing ``value``."""

    if period_type is PeriodType.YEAR:
        return _year_containing(value)

    if period_type is PeriodType.QUARTER:
        return _quarter_containing(value)

    if period_type is PeriodType.MONTH:
        return _month_containing(value)

    if period_type is PeriodType.WEEK:
        return _week_containing(value)

    raise ValueError(f"Unsupported period type: {period_type}")


def _year_containing(
    value: date,
) -> Period:
    """Construct the calendar year containing ``value``."""

    year = value.year

    return Period(
        period_id=str(year),
        period_type=PeriodType.YEAR,
        first_date=date(
            year,
            1,
            1,
        ),
        last_date=date(
            year,
            12,
            31,
        ),
    )


def _quarter_containing(
    value: date,
) -> Period:
    """Construct the calendar quarter containing ``value``."""

    quarter = ((value.month - 1) // 3) + 1

    first_month = ((quarter - 1) * 3) + 1

    first_date = date(
        value.year,
        first_month,
        1,
    )

    if quarter == 4:
        next_quarter = date(
            value.year + 1,
            1,
            1,
        )
    else:
        next_quarter = date(
            value.year,
            first_month + 3,
            1,
        )

    return Period(
        period_id=(f"{value.year}-Q{quarter}"),
        period_type=PeriodType.QUARTER,
        first_date=first_date,
        last_date=(next_quarter - timedelta(days=1)),
    )


def _month_containing(
    value: date,
) -> Period:
    """Construct the calendar month containing ``value``."""

    first_date = date(
        value.year,
        value.month,
        1,
    )

    if value.month == 12:
        next_month = date(
            value.year + 1,
            1,
            1,
        )
    else:
        next_month = date(
            value.year,
            value.month + 1,
            1,
        )

    return Period(
        period_id=first_date.strftime("%b-%Y"),
        period_type=PeriodType.MONTH,
        first_date=first_date,
        last_date=(next_month - timedelta(days=1)),
    )


def _week_containing(
    value: date,
) -> Period:
    """Construct the ISO calendar week containing ``value``."""

    iso_calendar = value.isocalendar()

    iso_year = iso_calendar.year
    iso_week = iso_calendar.week

    first_date = date.fromisocalendar(
        iso_year,
        iso_week,
        1,
    )

    return Period(
        period_id=(f"{iso_year}-W{iso_week}"),
        period_type=PeriodType.WEEK,
        first_date=first_date,
        last_date=(first_date + timedelta(days=6)),
    )


def period_from_id(
    period_id: str,
) -> Period:
    """Reconstruct a canonical period from its period ID."""

    period_type = _period_type_from_id(period_id)

    value = _period_value_from_id(
        period_id,
        period_type,
    )

    period = period_containing(
        value,
        period_type,
    )

    if period.period_id != period_id:
        raise ValueError(f"Non-canonical period_id: {period_id!r}")

    return period


def _period_value_from_id(
    period_id: str,
    period_type: PeriodType,
) -> date:
    """Parse the canonical anchor date represented by one period ID."""

    if period_type is PeriodType.YEAR:
        return _year_value_from_id(period_id)

    if period_type is PeriodType.MONTH:
        return _month_value_from_id(period_id)

    if period_type is PeriodType.QUARTER:
        return _quarter_value_from_id(period_id)

    if period_type is PeriodType.WEEK:
        return _week_value_from_id(period_id)

    raise ValueError(f"Unsupported period type: {period_type}")


def _year_value_from_id(
    period_id: str,
) -> date:
    """Parse the anchor date for a year period ID."""

    try:
        return date(
            int(period_id),
            1,
            1,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid year period_id: {period_id!r}") from exc


def _month_value_from_id(
    period_id: str,
) -> date:
    """Parse the anchor date for a month period ID."""

    try:
        month_name, raw_year = period_id.split("-")
        month = Month.from_str(month_name)

        return date(
            int(raw_year),
            month.as_int,
            1,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid month period_id: {period_id!r}") from exc


def _quarter_value_from_id(
    period_id: str,
) -> date:
    """Parse the anchor date for a quarter period ID."""

    try:
        raw_year, raw_quarter = period_id.split("-Q")
        quarter = int(raw_quarter)

        if quarter not in {
            1,
            2,
            3,
            4,
        }:
            raise ValueError

        return date(
            int(raw_year),
            (quarter - 1) * 3 + 1,
            1,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid quarter period_id: {period_id!r}") from exc


def _week_value_from_id(
    period_id: str,
) -> date:
    """Parse the anchor date for an ISO-week period ID."""

    try:
        raw_year, raw_week = period_id.split("-W")

        return date.fromisocalendar(
            int(raw_year),
            int(raw_week),
            1,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid week period_id: {period_id!r}") from exc


def _period_type_from_id(
    period_id: str,
) -> PeriodType:
    """Identify the period type encoded by a canonical period ID."""

    for (
        period_type,
        pattern,
    ) in PERIOD_TYPE_PARSING_MAP.items():
        if pattern.fullmatch(period_id):
            return period_type

    raise ValueError(f"Unrecognized period_id format: {period_id!r}")
