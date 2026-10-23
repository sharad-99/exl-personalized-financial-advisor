from __future__ import annotations

import calendar
from datetime import UTC, date, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_today() -> date:
    return utc_now().date()


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def months_between(start: date, end: date) -> int:
    """Whole calendar months from start to end (end exclusive of partial month)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)
