from dataclasses import dataclass


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