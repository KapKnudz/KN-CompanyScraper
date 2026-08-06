from dataclasses import dataclass
from datetime import date


@dataclass
class Report:

    revenue: float | None
    operating_profit: float | None
    ebit: float | None
    ebitda: float | None
    net_income: float | None

    free_cash_flow: float | None

    equity: float | None
    total_assets: float | None
    total_debt: float | None

    shares_outstanding: float | None

    year: int | None = None
    period: int | None = None
    period_end: date | None = None
    currency: str | None = None
    raw_payload: dict | None = None
