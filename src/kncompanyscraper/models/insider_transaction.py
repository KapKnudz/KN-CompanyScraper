from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class InsiderTransaction:
    person_name: str
    person_role: Optional[str]
    transaction_type: str
    shares: int
    price_per_share: Optional[float]
    total_value: Optional[float]
    transaction_date: date
    source: Optional[str] = None
    reported_at: Optional[datetime] = None
    currency: Optional[str] = None
