"""A data-class encapsulating weekdays and different representations."""

from dataclasses import dataclass

WEEKDAY_STRINGS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

WEEKDAY_STRINGS_ABBR = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun",
}

WEEKDAY_LOOKUP = {
    **{v.lower(): k for k, v in WEEKDAY_STRINGS.items()},  # Full names
    **{v.lower(): k for k, v in WEEKDAY_STRINGS_ABBR.items()},  # Abbreviations
}


@dataclass(frozen=True)
class Weekday:
    """Represents a weekday with various representations."""

    weekday: int  # 0 (Monday) to 6 (Sunday)

    def __post_init__(self):
        if not (0 <= self.weekday <= 6):
            raise ValueError(
                f"Invalid weekday: {self.weekday}. Must be between 0 (Monday) and 6 (Sunday)."
            )

    @property
    def as_int(self) -> int:
        """Return the weekday as an integer."""
        return self.weekday

    @property
    def as_str(self) -> str:
        """Return the weekday as a full name."""
        return WEEKDAY_STRINGS[self.weekday]

    @property
    def as_abbr(self) -> str:
        """Return the weekday as a three-letter abbreviation."""
        return WEEKDAY_STRINGS_ABBR[self.weekday]

    @classmethod
    def from_str(cls, weekday_str: str) -> "Weekday":
        """Create a Weekday instance from a full name or abbreviation."""
        weekday_int = WEEKDAY_LOOKUP.get(weekday_str.lower())
        if weekday_int is None:
            raise ValueError(
                f"Invalid weekday name: {weekday_str}. Expected one of {list(WEEKDAY_LOOKUP.keys())}."
            )
        return cls(weekday_int)
