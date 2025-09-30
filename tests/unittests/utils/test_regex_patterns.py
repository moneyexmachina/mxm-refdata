"""Unit tests for regex_patterns in the utils module."""

from mxm_refdata.models.periods import PeriodType
from mxm_refdata.utils.regex_patterns import PERIOD_TYPE_PARSING_MAP


def test_period_type_parsing_map_keys():
    """Ensure PERIOD_TYPE_PARSING_MAP keys match PeriodType values."""
    # Check that all PeriodType values are represented in PERIOD_TYPE_PARSING_MAP
    period_types = set(PeriodType)
    regex_map_keys = set(PERIOD_TYPE_PARSING_MAP.keys())

    assert period_types == regex_map_keys, (
        f"Mismatch between PeriodType values and PERIOD_TYPE_PARSING_MAP keys.\n"
        f"Missing in regex map: {period_types - regex_map_keys}\n"
        f"Extra in regex map: {regex_map_keys - period_types}"
    )
