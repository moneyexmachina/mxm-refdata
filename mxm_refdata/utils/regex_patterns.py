"""Pre-computed regex patterns for use in the refData package."""

import re
from types import MappingProxyType

from mxm_refdata.models.periods import PeriodType

PERIOD_TYPE_PARSING_MAP = MappingProxyType(
    {
        PeriodType.YEAR: re.compile(r"^\d{4}$"),
        PeriodType.MONTH: re.compile(
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{4}$"
        ),
        PeriodType.QUARTER: re.compile(r"^\d{4}-Q[1-4]$"),
        PeriodType.WEEK: re.compile(r"^\d{4}-W\d{1,2}$"),
        PeriodType.DAY: re.compile(r"^\d{4}\d{2}\d{2}$"),
    }
)
