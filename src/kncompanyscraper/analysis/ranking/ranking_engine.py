from kncompanyscraper.analysis.ranking.company_score import CompanyScore, WatchlistRanking
from kncompanyscraper.analysis.ranking.score_rules import (
    score_quality,
    score_growth,
    score_valuation,
    score_balance_sheet,
)


class RankingEngine:

    def rank(self, companies: list, results_by_company: dict[int, dict]) -> WatchlistRanking:
        scores: list[CompanyScore] = []

        for company in companies:
            results = results_by_company.get(company.id, {})
            financial = results.get("financial")
            valuation = results.get("valuation")

            quality = score_quality(financial)
            growth = score_growth(financial)
            val = score_valuation(valuation)
            balance = score_balance_sheet(financial)

            total = (
                quality["score"] * 0.30
                + growth["score"] * 0.25
                + val["score"] * 0.30
                + balance["score"] * 0.15
            )

            cs = CompanyScore(
                company_id=company.id,
                ticker=company.ticker,
                name=company.name,
                quality_score=round(quality["score"], 1),
                growth_score=round(growth["score"], 1),
                valuation_score=round(val["score"], 1),
                balance_sheet_score=round(balance["score"], 1),
                total_score=round(total, 1),
                positives=quality["positives"] + growth["positives"] + val["positives"] + balance["positives"],
                negatives=quality["negatives"] + growth["negatives"] + val["negatives"] + balance["negatives"],
                missing_data=quality["missing"] + growth["missing"] + val["missing"] + balance["missing"],
                flags=[],
            )
            scores.append(cs)

        scores.sort(key=lambda s: s.total_score, reverse=True)
        return WatchlistRanking(scores=scores)
