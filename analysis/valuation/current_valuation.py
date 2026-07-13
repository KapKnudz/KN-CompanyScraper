@dataclass
class CurrentValuation:

    market_cap: float | None
    enterprise_value: float | None

    pe: float | None
    ev_ebit: float | None
    ev_ebitda: float | None

    pb: float | None
    ps: float | None
    pfcf: float | None

    peg: float | None

    dividend_yield: float | None