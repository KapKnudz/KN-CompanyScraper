from dataclasses import dataclass


@dataclass
class ValuationResult:
    # Key Metrics
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

    # Percentiles
    pe_percentile: float | None
    ev_ebit_percentile: float | None

    # Raw-derived fields (computed from latest close × report fundamentals).
    # These are independent of Börsdata's pre-computed KPIs and typically
    # fresher. When available, prefer these for yield/multiple scoring.
    raw_market_cap: float | None = None
    raw_enterprise_value: float | None = None
    raw_earnings_yield: float | None = None
    raw_fcf_yield: float | None = None
    raw_pe: float | None = None
    raw_pfcf: float | None = None
    raw_ev_ebit: float | None = None
    raw_ev_ebitda: float | None = None