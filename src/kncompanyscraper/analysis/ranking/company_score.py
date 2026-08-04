from dataclasses import dataclass, field


@dataclass
class CompanyScore:
    company_id: int
    ticker: str
    name: str

    quality_score: float = 0.0
    growth_score: float = 0.0
    valuation_score: float = 0.0
    balance_sheet_score: float = 0.0

    total_score: float = 0.0

    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class WatchlistRanking:
    scores: list[CompanyScore]

    def top_n(self, n: int) -> list[CompanyScore]:
        return self.scores[:n]
