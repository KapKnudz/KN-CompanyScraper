from dataclasses import dataclass


@dataclass
class CurrentFinancials:
    revenue: float | None
    operating_profit: float | None
    ebit: float | None
    ebitda: float | None
    net_income: float | None
    free_cash_flow: float | None
    equity: float | None
    total_assets: float | None
    total_debt: float | None


@dataclass
class HistoricalFinancials:
    revenue_history: list[float | None]
    ebit_history: list[float | None]
    fcf_history: list[float | None]
    net_income_history: list[float | None]


@dataclass
class FinancialResult:
    # Margins
    operating_margin: float | None
    net_margin: float | None
    fcf_margin: float | None

    # Growth (Year-over-Year)
    revenue_growth: float | None
    ebit_growth: float | None
    net_income_growth: float | None

    # Returns
    roe: float | None
    roa: float | None

    # Health
    debt_to_equity: float | None
