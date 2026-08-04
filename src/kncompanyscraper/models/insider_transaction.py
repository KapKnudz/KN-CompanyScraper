from dataclasses import dataclass
from datetime import date
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
