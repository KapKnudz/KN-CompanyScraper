from kncompanyscraper.analysis.ranking.company_score import WatchlistRanking


class WatchlistAnalysisService:

    def __init__(self, company_repository, analysis_engine, ranking_engine):
        self.company_repository = company_repository
        self.analysis_engine = analysis_engine
        self.ranking_engine = ranking_engine

    def rank_watchlist(self) -> WatchlistRanking:
        companies = self.company_repository.get_active_companies()

        results_by_company = {}
        for company in companies:
            results_by_company[company.id] = self.analysis_engine.analyze(company)

        return self.ranking_engine.rank(companies, results_by_company)

    def shortlist_for_agent(self, top_n: int = 25, max_total: int = 30) -> list:
        ranking = self.rank_watchlist()
        return ranking.shortlist_for_agent(top_n=top_n, max_total=max_total)
