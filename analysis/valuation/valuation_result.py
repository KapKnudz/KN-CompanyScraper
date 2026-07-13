from dataclasses import dataclass


@dataclass
class ValuationResult:

    # Current multiples
    pe: float | None
    ev_ebit: float | None
    ev_ebitda: float | None
    pb: float | None
    ps: float | None
    pfcf: float | None
    peg: float | None

    # Derived values
    earnings_yield: float | None
    free_cash_flow_yield: float | None

    # Historical comparison
    pe_vs_5y_avg: float | None
    ev_ebit_vs_5y_avg: float | None
    pb_vs_5y_avg: float | None

    # Percentile
    pe_percentile: float | None
    ev_ebit_percentile: float |None