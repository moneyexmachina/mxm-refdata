"""Unit tests for the Month class."""

import pytest

from mxm_refdata.models.months import Month


def test_month_initialization():
    """Test valid Month initialization."""
    month = Month(1)
    assert month.as_int == 1
    assert month.as_str == "Jan"
    assert month.as_cme_code == "F"


def test_invalid_month_initialization():
    """Test that invalid Month initialization raises a ValueError."""
    with pytest.raises(ValueError, match="Invalid month: 0. Must be between 1 and 12."):
        Month(0)
    with pytest.raises(
        ValueError, match="Invalid month: 13. Must be between 1 and 12."
    ):
        Month(13)


def test_month_as_int():
    """Test the as_int property."""
    for i in range(1, 13):
        month = Month(i)
        assert month.as_int == i


def test_month_as_str():
    """Test the as_str property with specific examples."""
    month = Month(1)
    assert month.as_str == "Jan"

    month = Month(6)
    assert month.as_str == "Jun"

    month = Month(12)
    assert month.as_str == "Dec"


def test_month_as_cme_code():
    """Test the as_cme_code property with specific examples."""
    month = Month(1)
    assert month.as_cme_code == "F"

    month = Month(6)
    assert month.as_cme_code == "M"

    month = Month(12)
    assert month.as_cme_code == "Z"


def test_month_from_str():
    """Test the from_str method of the Month class."""
    assert Month.from_str("Jan").as_int == 1
    assert Month.from_str("Feb").as_int == 2
    assert Month.from_str("Dec").as_int == 12

    with pytest.raises(ValueError, match="Invalid month abbreviation: Foo"):
        Month.from_str("Foo")
