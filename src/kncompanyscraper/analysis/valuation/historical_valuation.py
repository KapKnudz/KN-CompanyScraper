from dataclasses import dataclass


@dataclass
class HistoricalValuation:

    pe_history: list[float]
    ev_ebit_history: list[float]
    pb_history: list[float]

    avg_pe: float | None
    avg_ev_ebit: float | None
    avg_pb: float | None

    median_pe: float | None
    median_ev_ebit: float | None
    median_pb: float | None