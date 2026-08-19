from dataclasses import dataclass, field


@dataclass
class DecilePerformance:
    decile: int  # 1 = top decile
    avg_6m_return: float | None = None
    avg_12m_return: float | None = None
    avg_24m_return: float | None = None
    avg_36m_return: float | None = None
    avg_48m_return: float | None = None
    hit_rate_6m: float | None = None  # fraction with a positive return
    hit_rate_12m: float | None = None
    hit_rate_24m: float | None = None
    hit_rate_36m: float | None = None
    hit_rate_48m: float | None = None
    count: int = 0
    count_6m: int = 0
    count_12m: int = 0
    count_24m: int = 0
    count_36m: int = 0
    count_48m: int = 0


@dataclass
class CategoryCorrelation:
    category: str
    correlation_6m: float | None = None
    correlation_12m: float | None = None
    correlation_24m: float | None = None
    correlation_36m: float | None = None
    correlation_48m: float | None = None


@dataclass
class CompanyAttribution:
    observation_date: str
    company_id: int
    company_name: str
    ticker: str
    rank: int
    decile: int | None
    quality_score: float | None
    growth_score: float | None
    valuation_score: float | None
    balance_sheet_score: float | None
    total_score: float
    return_6m: float | None
    return_12m: float | None
    return_24m: float | None = None
    return_36m: float | None = None
    return_48m: float | None = None
    price_return_6m: float | None = None
    price_return_12m: float | None = None
    price_return_24m: float | None = None
    price_return_36m: float | None = None
    price_return_48m: float | None = None
    contribution_6m: float | None = None
    contribution_12m: float | None = None
    contribution_24m: float | None = None
    contribution_36m: float | None = None
    contribution_48m: float | None = None
    return_issue_6m: str | None = None
    return_issue_12m: str | None = None
    return_issue_24m: str | None = None
    return_issue_36m: str | None = None
    return_issue_48m: str | None = None
    return_end_date_6m: str | None = None
    return_end_date_12m: str | None = None
    return_end_date_24m: str | None = None
    return_end_date_36m: str | None = None
    return_end_date_48m: str | None = None
    sector_id: int | None = None
    ranking_model: str | None = None
    market_cap: float | None = None
    benchmark_6m_return: float | None = None
    benchmark_12m_return: float | None = None
    benchmark_24m_return: float | None = None
    benchmark_36m_return: float | None = None
    benchmark_48m_return: float | None = None


@dataclass
class MetricAttribution:
    observation_date: str
    company_id: int
    company_name: str
    ticker: str
    ranking_model: str
    category: str
    metric: str
    raw_value: float | None
    normalized_score: float | None
    configured_weight: float
    effective_weight: float
    category_contribution: float
    category_score: float
    reconstruction_error: float
    total_category_weight: float
    total_contribution: float
    available: bool
    transformation: str
    dependencies: str
    cross_category_dependencies: str
    provenance: str
    return_6m: float | None = None
    return_12m: float | None = None
    return_24m: float | None = None
    return_36m: float | None = None
    return_48m: float | None = None
    benchmark_6m_return: float | None = None
    benchmark_12m_return: float | None = None
    benchmark_24m_return: float | None = None
    benchmark_36m_return: float | None = None
    benchmark_48m_return: float | None = None


@dataclass
class PeriodResult:
    """Result for a single backtest date."""

    observation_date: str
    deciles: list[DecilePerformance] = field(default_factory=list)
    attributions: list[CompanyAttribution] = field(default_factory=list)
    metric_attributions: list[MetricAttribution] = field(default_factory=list)
    correlations: list[CategoryCorrelation] = field(default_factory=list)
    top_decile_spread_6m: float | None = None
    top_decile_spread_12m: float | None = None
    top_decile_spread_24m: float | None = None
    top_decile_spread_36m: float | None = None
    top_decile_spread_48m: float | None = None
    benchmark_6m_return: float | None = None
    benchmark_12m_return: float | None = None
    benchmark_24m_return: float | None = None
    benchmark_36m_return: float | None = None
    benchmark_48m_return: float | None = None
    top_decile_excess_6m: float | None = None
    top_decile_excess_12m: float | None = None
    top_decile_excess_24m: float | None = None
    top_decile_excess_36m: float | None = None
    top_decile_excess_48m: float | None = None
    return_basis: str = "gross_total_return"
    return_coverage_6m_count: int = 0
    return_coverage_12m_count: int = 0
    return_coverage_24m_count: int = 0
    return_coverage_36m_count: int = 0
    return_coverage_48m_count: int = 0
    missing_return_company_ids_6m: tuple[int, ...] = ()
    missing_return_company_ids_12m: tuple[int, ...] = ()
    missing_return_company_ids_24m: tuple[int, ...] = ()
    missing_return_company_ids_36m: tuple[int, ...] = ()
    missing_return_company_ids_48m: tuple[int, ...] = ()
    company_count: int = 0
    eligible_count: int = 0
