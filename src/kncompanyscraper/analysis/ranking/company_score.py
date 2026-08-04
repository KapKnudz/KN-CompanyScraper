from dataclasses import dataclass, field
from typing import Literal


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

    data_quality: Literal["high", "medium", "low"] = "medium"
    candidate_reason: str | None = None


@dataclass
class WatchlistRanking:
    scores: list[CompanyScore]

    def top_n(self, n: int) -> list[CompanyScore]:
        return self.scores[:n]

    def shortlist_for_agent(
        self,
        top_n: int = 25,
        include_flags: bool = True,
        max_total: int = 30,
    ) -> list[CompanyScore]:
        shortlist = list(self.scores[:top_n])

        if include_flags:
            important_flags = {
                "cheap_quality",
                "fcf_quality",
                "cheap_but_weak_growth",
                "insider_buying_support",
                "major_recent_news",
                "ceo_outlook_positive",
                "turnaround_candidate",
            }

            for score in self.scores[top_n:]:
                if any(flag in important_flags for flag in score.flags):
                    shortlist.append(score)

                if len(shortlist) >= max_total:
                    break

        return shortlist
