from dataclasses import dataclass


@dataclass
class KpiHistoryPoint:

    year: int
    value: float


@dataclass
class KpiHistory:

    kpi_id: int
    values: list[KpiHistoryPoint]