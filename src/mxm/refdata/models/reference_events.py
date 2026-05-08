from enum import Enum


class ReferenceEvent(Enum):
    """Enum representing the possible reference events for last trading day rules."""

    BUSINESS_DAY_OF_PERIOD = "business_day_of_period"
    CALENDAR_DAY_OF_PERIOD = "calendar_day_of_period"
    WEEKDAY_OF_PERIOD = "weekday_of_period"
