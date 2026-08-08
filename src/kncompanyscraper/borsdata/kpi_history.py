from dataclasses import dataclass


@dataclass
class KpiHistoryPoint:

    year: int
    value: float
    period: int | None = None


@dataclass
class KpiHistory:

    kpi_id: int
    values: list[KpiHistoryPoint]
