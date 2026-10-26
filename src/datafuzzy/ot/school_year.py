"""School years as the school form writes them: "09/2026-06/2027", first month to last."""

from __future__ import annotations

import re
from datetime import date

_SCHOOL_YEAR = re.compile(r"^\s*(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{4})\s*$")


def default_school_year(today: date) -> tuple[date, date]:
    """September to June of the school year `today` belongs to; from August on, the coming one."""
    start = today.year if today.month >= 8 else today.year - 1
    return date(start, 9, 1), date(start + 1, 6, 1)


def parse_school_year(text: str) -> tuple[date, date] | None:
    """"09/2026-06/2027" as the first days of both months; None if it does not read so."""
    m = _SCHOOL_YEAR.match(text)
    if not m:
        return None
    m1, y1, m2, y2 = (int(g) for g in m.groups())
    if not (1 <= m1 <= 12 and 1 <= m2 <= 12):
        return None
    return date(y1, m1, 1), date(y2, m2, 1)


def format_school_year(start: date, end: date) -> str:
    return f"{start.month:02d}/{start.year}-{end.month:02d}/{end.year}"
