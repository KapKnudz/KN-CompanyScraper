from dataclasses import dataclass, field


@dataclass
class DecilePerformance:
    decile: int  # 1 = top decile
    avg_6m_return: float | None = None
    avg_12m_return: float | None = None
    hit_rate_6m: float | None = None  # fraction with a positive return
    hit_rate_12m: float | None = None
    count: int = 0
    count_6m: int = 0
    count_12m: int = 0


@dataclass
class CategoryCorrelation:
    category: str
    correlation_6m: float | None = None
    correlation_12m: float | None = None


@dataclass
class PeriodResult:
    """Result for a single backtest date."""

    observation_date: str
    deciles: list[DecilePerformance] = field(default_factory=list)
    correlations: list[CategoryCorrelation] = field(default_factory=list)
    top_decile_spread_6m: float | None = None
    top_decile_spread_12m: float | None = None
    company_count: int = 0
    eligible_count: int = 0
