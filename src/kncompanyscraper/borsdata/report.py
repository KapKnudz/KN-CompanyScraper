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
    financing_cash_flow: float | None = None
    cash: float | None = None
    eps: float | None = None
    dividend_per_share: float | None = None

    year: int | None = None
    period: int | None = None
    period_end: date | None = None
    report_date: date | None = None
    broken_fiscal_year: bool | None = None
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


@dataclass(frozen=True)
class InstrumentReportBundle:
    instrument_id: int
    annual: tuple[Report, ...]
    r12: tuple[Report, ...]
    quarterly: tuple[Report, ...]
    error: str | None = None
