from dataclasses import dataclass


@dataclass
class ValuationResult:

    # Derived values
    earnings_yield: float | None
    free_cash_flow_yield: float | None

    # Historical comparison
    pe_vs_5y_avg: float | None
    ev_ebit_vs_5y_avg: float | None
    pb_vs_5y_avg: float | None