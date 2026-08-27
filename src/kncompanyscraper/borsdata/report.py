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

    gross_income: float | None = None
    operating_cash_flow: float | None = None
    investing_cash_flow: float | None = None

    year: int | None = None
    period: int | None = None
    period_end: date | None = None
    currency: str | None = None
    raw_payload: dict | None = None

    def __post_init__(self) -> None:
        """Keep the legacy operating-profit name aligned with canonical EBIT."""
        if self.ebit is None:
            self.ebit = self.operating_profit
        elif self.operating_profit is None:
            self.operating_profit = self.ebit
        elif self.operating_profit != self.ebit:
            # EBIT is canonical; normalize legacy callers that still provide a
            # separately named operating-profit value.
            self.operating_profit = self.ebit
