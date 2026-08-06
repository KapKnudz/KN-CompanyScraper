from dataclasses import dataclass

from kncompanyscraper.analysis.ranking.company_score import WatchlistRanking


@dataclass(frozen=True)
class WatchlistAnalysisRun:
    ranking: WatchlistRanking
    results_by_company: dict[int, dict]


class WatchlistAnalysisService:

    def __init__(self, company_repository, analysis_engine, ranking_engine):
        self.company_repository = company_repository
        self.analysis_engine = analysis_engine
        self.ranking_engine = ranking_engine

    def analyze_watchlist(self) -> WatchlistAnalysisRun:
        companies = self.company_repository.get_active_companies()

        results_by_company = {}
        for company in companies:
            results_by_company[company.id] = self.analysis_engine.analyze(company)

        ranking = self.ranking_engine.rank(companies, results_by_company)
        return WatchlistAnalysisRun(ranking=ranking, results_by_company=results_by_company)

    def rank_watchlist(self) -> WatchlistRanking:
        return self.analyze_watchlist().ranking

    def shortlist_for_agent(self, top_n: int = 25, max_total: int = 30) -> list:
        ranking = self.rank_watchlist()
        return ranking.shortlist_for_agent(top_n=top_n, max_total=max_total)
