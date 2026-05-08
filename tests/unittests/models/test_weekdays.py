import pytest

from mxm.refdata.models.weekdays import Weekday


@pytest.mark.parametrize(
    "input_value, expected_int, expected_str, expected_abbr",
    [
        (0, 0, "Monday", "Mon"),
        (1, 1, "Tuesday", "Tue"),
        (2, 2, "Wednesday", "Wed"),
        (3, 3, "Thursday", "Thu"),
        (4, 4, "Friday", "Fri"),
        (5, 5, "Saturday", "Sat"),
        (6, 6, "Sunday", "Sun"),
        ("Monday", 0, "Monday", "Mon"),
        ("Tuesday", 1, "Tuesday", "Tue"),
        ("Wednesday", 2, "Wednesday", "Wed"),
        ("Thursday", 3, "Thursday", "Thu"),
        ("Friday", 4, "Friday", "Fri"),
        ("Saturday", 5, "Saturday", "Sat"),
        ("Sunday", 6, "Sunday", "Sun"),
        ("Mon", 0, "Monday", "Mon"),
        ("Tue", 1, "Tuesday", "Tue"),
        ("Wed", 2, "Wednesday", "Wed"),
        ("Thu", 3, "Thursday", "Thu"),
        ("Fri", 4, "Friday", "Fri"),
        ("Sat", 5, "Saturday", "Sat"),
        ("Sun", 6, "Sunday", "Sun"),
        ("mon", 0, "Monday", "Mon"),  # Case-insensitive
        ("tue", 1, "Tuesday", "Tue"),
        ("wed", 2, "Wednesday", "Wed"),
        ("thu", 3, "Thursday", "Thu"),
        ("fri", 4, "Friday", "Fri"),
        ("sat", 5, "Saturday", "Sat"),
        ("sun", 6, "Sunday", "Sun"),
    ],
)
def test_weekday_parsing(input_value, expected_int, expected_str, expected_abbr):
    """Test that Weekday correctly parses integers, full names, and abbreviations."""
    weekday = (
        Weekday.from_str(input_value)
        if isinstance(input_value, str)
        else Weekday(input_value)
    )
    assert weekday.as_int == expected_int
    assert weekday.as_str == expected_str
    assert weekday.as_abbr == expected_abbr


def test_invalid_weekday():
    """Test that invalid weekday names or numbers raise ValueError."""
    with pytest.raises(ValueError):
        Weekday(7)  # Invalid integer
    with pytest.raises(ValueError):
        Weekday(-1)  # Invalid integer
    with pytest.raises(ValueError):
        Weekday.from_str("Funday")  # Nonexistent weekday
    with pytest.raises(ValueError):
        Weekday.from_str("Tuesd")  # Misspelled abbreviation
