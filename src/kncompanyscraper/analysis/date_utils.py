"""Shared date policies used by performance and valuation analysis."""

from calendar import monthrange
from datetime import date


MAX_PRICE_AGE_DAYS = 7


def add_months(value: date, months: int) -> date:
    """Advance a date by calendar months, clamping to the target month."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))
