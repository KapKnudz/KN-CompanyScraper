from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CashDividend:
    ex_date: date
    amount: float
    currency: str
    dividend_type: int
    distribution_frequency: str | None = None
