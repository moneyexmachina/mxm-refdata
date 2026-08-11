"""Unit tests for pure calendar-period generation."""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest

from mxm.refdata.generation.periods import (
    generate_periods,
    shift_period_by_n,
)
from mxm.refdata.models.periods import Period, PeriodType


def _period_ids(
    periods: list[Period],
) -> list[str]:
    """Return period identities in result order."""

    return [period.period_id for period in periods]


# ---------------------------------------------------------------------
# MONTH GENERATION
# ---------------------------------------------------------------------


def test_generate_months_for_complete_range() -> None:
    """Complete calendar months are generated chronologically."""

    periods = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        period_types=(PeriodType.MONTH,),
    )

    assert _period_ids(periods) == [
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
    ]

    assert periods[0] == Period(
        period_id="Jan-2024",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 1, 1),
        last_date=date(2024, 1, 31),
    )

    assert periods[1] == Period(
        period_id="Feb-2024",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 2, 1),
        last_date=date(2024, 2, 29),
    )

    assert periods[2] == Period(
        period_id="Mar-2024",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 3, 1),
        last_date=date(2024, 3, 31),
    )


def test_generate_periods_includes_period_containing_start_date() -> None:
    """The first period may begin before the requested start date."""

    periods = generate_periods(
        start_date=date(2024, 1, 15),
        end_date=date(2024, 3, 31),
        period_types=(PeriodType.MONTH,),
    )

    assert _period_ids(periods) == [
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
    ]

    assert periods[0].first_date == date(
        2024,
        1,
        1,
    )


def test_generate_periods_excludes_partial_end_period_by_default() -> None:
    """A trailing period extending beyond the range is excluded."""

    periods = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 15),
        period_types=(PeriodType.MONTH,),
    )

    assert _period_ids(periods) == [
        "Jan-2024",
        "Feb-2024",
    ]


def test_generate_periods_includes_partial_end_period_when_requested() -> None:
    """A trailing partial period can be included explicitly."""

    periods = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 15),
        period_types=(PeriodType.MONTH,),
        include_partial_end_period=True,
    )

    assert _period_ids(periods) == [
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
    ]

    assert periods[-1].last_date == date(
        2024,
        3,
        31,
    )


def test_generate_periods_returns_empty_when_only_period_is_partial() -> None:
    """A range ending within its first period produces no complete period."""

    periods = generate_periods(
        start_date=date(2024, 2, 10),
        end_date=date(2024, 2, 20),
        period_types=(PeriodType.MONTH,),
    )

    assert periods == []


def test_generate_months_handles_leap_year() -> None:
    """February uses the correct leap-year boundary."""

    periods = generate_periods(
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 29),
        period_types=(PeriodType.MONTH,),
    )

    assert periods == [
        Period(
            period_id="Feb-2024",
            period_type=PeriodType.MONTH,
            first_date=date(2024, 2, 1),
            last_date=date(2024, 2, 29),
        )
    ]


# ---------------------------------------------------------------------
# QUARTER, YEAR, AND WEEK GENERATION
# ---------------------------------------------------------------------


def test_generate_quarters() -> None:
    """Calendar quarters have canonical IDs and date boundaries."""

    periods = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 9, 30),
        period_types=(PeriodType.QUARTER,),
    )

    assert periods == [
        Period(
            period_id="2024-Q1",
            period_type=PeriodType.QUARTER,
            first_date=date(2024, 1, 1),
            last_date=date(2024, 3, 31),
        ),
        Period(
            period_id="2024-Q2",
            period_type=PeriodType.QUARTER,
            first_date=date(2024, 4, 1),
            last_date=date(2024, 6, 30),
        ),
        Period(
            period_id="2024-Q3",
            period_type=PeriodType.QUARTER,
            first_date=date(2024, 7, 1),
            last_date=date(2024, 9, 30),
        ),
    ]


def test_generate_quarters_across_year_boundary() -> None:
    """Quarter generation advances correctly into the next year."""

    periods = generate_periods(
        start_date=date(2024, 10, 1),
        end_date=date(2025, 3, 31),
        period_types=(PeriodType.QUARTER,),
    )

    assert _period_ids(periods) == [
        "2024-Q4",
        "2025-Q1",
    ]


def test_generate_years() -> None:
    """Calendar years include the year containing the start date."""

    periods = generate_periods(
        start_date=date(2023, 6, 15),
        end_date=date(2024, 12, 31),
        period_types=(PeriodType.YEAR,),
    )

    assert periods == [
        Period(
            period_id="2023",
            period_type=PeriodType.YEAR,
            first_date=date(2023, 1, 1),
            last_date=date(2023, 12, 31),
        ),
        Period(
            period_id="2024",
            period_type=PeriodType.YEAR,
            first_date=date(2024, 1, 1),
            last_date=date(2024, 12, 31),
        ),
    ]


def test_generate_iso_weeks() -> None:
    """ISO weeks run from Monday through Sunday."""

    periods = generate_periods(
        start_date=date(2024, 3, 4),
        end_date=date(2024, 3, 17),
        period_types=(PeriodType.WEEK,),
    )

    assert periods == [
        Period(
            period_id="2024-W10",
            period_type=PeriodType.WEEK,
            first_date=date(2024, 3, 4),
            last_date=date(2024, 3, 10),
        ),
        Period(
            period_id="2024-W11",
            period_type=PeriodType.WEEK,
            first_date=date(2024, 3, 11),
            last_date=date(2024, 3, 17),
        ),
    ]


def test_generate_iso_week_uses_iso_year() -> None:
    """Week identity uses ISO year around the Gregorian year boundary."""

    periods = generate_periods(
        start_date=date(2024, 12, 30),
        end_date=date(2025, 1, 5),
        period_types=(PeriodType.WEEK,),
    )

    assert periods == [
        Period(
            period_id="2025-W1",
            period_type=PeriodType.WEEK,
            first_date=date(2024, 12, 30),
            last_date=date(2025, 1, 5),
        )
    ]


# ---------------------------------------------------------------------
# MULTIPLE PERIOD TYPES
# ---------------------------------------------------------------------


def test_generate_periods_preserves_requested_type_order() -> None:
    """Results are grouped in the order of the requested period types."""

    periods = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_types=(
            PeriodType.YEAR,
            PeriodType.QUARTER,
            PeriodType.MONTH,
        ),
    )

    assert [period.period_type for period in periods] == (
        [PeriodType.YEAR] + [PeriodType.QUARTER] * 4 + [PeriodType.MONTH] * 12
    )

    assert _period_ids(periods) == [
        "2024",
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
        "Apr-2024",
        "May-2024",
        "Jun-2024",
        "Jul-2024",
        "Aug-2024",
        "Sep-2024",
        "Oct-2024",
        "Nov-2024",
        "Dec-2024",
    ]


def test_generate_periods_accepts_general_iterable() -> None:
    """The period-types input need not be a concrete sequence."""

    period_types = (
        period_type
        for period_type in (
            PeriodType.MONTH,
            PeriodType.QUARTER,
        )
    )

    periods = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        period_types=period_types,
    )

    assert _period_ids(periods) == [
        "Jan-2024",
        "Feb-2024",
        "Mar-2024",
        "2024-Q1",
    ]


# ---------------------------------------------------------------------
# PURE VALUE SEMANTICS
# ---------------------------------------------------------------------


def test_generate_periods_is_deterministic_without_interning() -> None:
    """Repeated generation returns equal, independently constructed values."""

    first = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        period_types=(PeriodType.MONTH,),
    )

    second = generate_periods(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        period_types=(PeriodType.MONTH,),
    )

    assert first == second
    assert first is not second
    assert first[0] is not second[0]


# ---------------------------------------------------------------------
# INPUT VALIDATION
# ---------------------------------------------------------------------


def test_generate_periods_rejects_reversed_date_range() -> None:
    """The requested start date cannot follow the end date."""

    with pytest.raises(
        ValueError,
        match="start_date must not be after end_date",
    ):
        generate_periods(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 1, 31),
            period_types=(PeriodType.MONTH,),
        )


def test_generate_periods_rejects_empty_period_types() -> None:
    """At least one period type must be requested."""

    with pytest.raises(
        ValueError,
        match="period_types must be non-empty",
    ):
        generate_periods(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            period_types=(),
        )


def test_generate_periods_rejects_duplicate_period_types() -> None:
    """Repeated period types would create duplicate domain values."""

    with pytest.raises(
        ValueError,
        match="period_types must not contain duplicates",
    ):
        generate_periods(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            period_types=(
                PeriodType.MONTH,
                PeriodType.MONTH,
            ),
        )


def test_generate_periods_rejects_unsupported_period_type() -> None:
    """Unsupported values are rejected at the generation boundary."""

    unsupported = cast(
        PeriodType,
        object(),
    )

    with pytest.raises(
        ValueError,
        match="Unsupported period type",
    ):
        generate_periods(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            period_types=(unsupported,),
        )


# ---------------------------------------------------------------------
# PERIOD SHIFTING
# ---------------------------------------------------------------------


def test_shift_month_period_forward_and_backward() -> None:
    """Monthly periods can be shifted across month boundaries."""

    period = Period(
        period_id="Jun-2025",
        period_type=PeriodType.MONTH,
        first_date=date(2025, 6, 1),
        last_date=date(2025, 6, 30),
    )

    shifted_forward = shift_period_by_n(
        period,
        2,
    )
    shifted_backward = shift_period_by_n(
        period,
        -3,
    )

    assert shifted_forward == Period(
        period_id="Aug-2025",
        period_type=PeriodType.MONTH,
        first_date=date(2025, 8, 1),
        last_date=date(2025, 8, 31),
    )

    assert shifted_backward == Period(
        period_id="Mar-2025",
        period_type=PeriodType.MONTH,
        first_date=date(2025, 3, 1),
        last_date=date(2025, 3, 31),
    )


def test_shift_month_period_across_year_boundary() -> None:
    """Monthly shifting handles calendar-year transitions."""

    period = Period(
        period_id="Dec-2024",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 12, 1),
        last_date=date(2024, 12, 31),
    )

    assert (
        shift_period_by_n(
            period,
            2,
        ).period_id
        == "Feb-2025"
    )

    assert (
        shift_period_by_n(
            period,
            -12,
        ).period_id
        == "Dec-2023"
    )


def test_shift_quarter_period_forward_and_backward() -> None:
    """Quarterly periods can be shifted across years."""

    period = Period(
        period_id="2025-Q2",
        period_type=PeriodType.QUARTER,
        first_date=date(2025, 4, 1),
        last_date=date(2025, 6, 30),
    )

    assert (
        shift_period_by_n(
            period,
            1,
        ).period_id
        == "2025-Q3"
    )

    assert (
        shift_period_by_n(
            period,
            -2,
        ).period_id
        == "2024-Q4"
    )


def test_shift_year_period_forward_and_backward() -> None:
    """Year periods shift by complete calendar years."""

    period = Period(
        period_id="2025",
        period_type=PeriodType.YEAR,
        first_date=date(2025, 1, 1),
        last_date=date(2025, 12, 31),
    )

    assert (
        shift_period_by_n(
            period,
            1,
        ).period_id
        == "2026"
    )

    assert (
        shift_period_by_n(
            period,
            -2,
        ).period_id
        == "2023"
    )


def test_shift_week_period_forward_and_backward() -> None:
    """ISO weeks can be shifted in either direction."""

    period = Period(
        period_id="2025-W10",
        period_type=PeriodType.WEEK,
        first_date=date(2025, 3, 3),
        last_date=date(2025, 3, 9),
    )

    assert (
        shift_period_by_n(
            period,
            2,
        ).period_id
        == "2025-W12"
    )

    assert (
        shift_period_by_n(
            period,
            -3,
        ).period_id
        == "2025-W7"
    )


def test_shift_week_period_uses_iso_year_boundary() -> None:
    """Shifted week identity follows the ISO calendar year."""

    period = Period(
        period_id="2024-W52",
        period_type=PeriodType.WEEK,
        first_date=date(2024, 12, 23),
        last_date=date(2024, 12, 29),
    )

    shifted = shift_period_by_n(
        period,
        1,
    )

    assert shifted == Period(
        period_id="2025-W1",
        period_type=PeriodType.WEEK,
        first_date=date(2024, 12, 30),
        last_date=date(2025, 1, 5),
    )


def test_shift_period_by_zero_returns_equal_new_value() -> None:
    """A zero shift reconstructs an equal non-interned period."""

    period = Period(
        period_id="Feb-2024",
        period_type=PeriodType.MONTH,
        first_date=date(2024, 2, 1),
        last_date=date(2024, 2, 29),
    )

    shifted = shift_period_by_n(
        period,
        0,
    )

    assert shifted == period
    assert shifted is not period
