@dataclass
class HistoricalValuation:

    pe_history: list[float]
    ev_ebit_history: list[float]
    pb_history: list[float]

    avg_pe: float
    avg_ev_ebit: float
    avg_pb: float

    median_pe: float
    median_ev_ebit: float
    median_pb: float