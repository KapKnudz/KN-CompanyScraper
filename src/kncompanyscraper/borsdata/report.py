from dataclasses import dataclass
from datetime import date


@dataclass
class Report:

    revenue: float
    operating_profit: float
    ebit: float
    ebitda: float
    net_income: float

    free_cash_flow: float

    equity: float
    total_assets: float
    total_debt: float

    shares_outstanding: float

    year: int | None = None
    period: int | None = None
    period_end: date | None = None
    currency: str | None = None
    raw_payload: dict | None = None
