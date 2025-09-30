"""A data-class encapsulating calendar months and different representations."""

from dataclasses import dataclass

CME_MONTH_CODES = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}

MONTH_STRINGS = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

MONTH_STRINGS_REVERSE = {v: k for k, v in MONTH_STRINGS.items()}


@dataclass(frozen=True)
class Month:
    """Represents a month with various representations."""

    month: int  # 1 (January) to 12 (December)

    def __post_init__(self):
        if not (1 <= self.month <= 12):
            raise ValueError(f"Invalid month: {self.month}. Must be between 1 and 12.")

    @property
    def as_int(self) -> int:
        """Return the month as an integer."""
        return self.month

    @property
    def as_str(self) -> str:
        """Return the month as a three-letter abbreviation."""
        return MONTH_STRINGS[self.month]

    @property
    def as_cme_code(self) -> str:
        """Return the month as a CME code."""
        return CME_MONTH_CODES[self.month]

    @classmethod
    def from_str(cls, month_str: str) -> "Month":
        """Create a Month instance from a three-letter abbreviation."""
        month_int = MONTH_STRINGS_REVERSE.get(month_str)
        if not month_int:
            raise ValueError(
                f"Invalid month abbreviation: {month_str}. "
                f"Expected one of {list(MONTH_STRINGS_REVERSE.keys())}."
            )
        return cls(month_int)
