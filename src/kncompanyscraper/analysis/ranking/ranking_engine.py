from kncompanyscraper.analysis.ranking.company_score import CompanyScore, WatchlistRanking
from kncompanyscraper.analysis.ranking.score_rules import (
    score_quality,
    score_growth,
    score_valuation,
    score_balance_sheet,
)


def _compute_flags(quality: dict, growth: dict, val: dict, balance: dict, missing_data: list[str]) -> list[str]:
    flags: list[str] = []

    q = quality["score"]
    g = growth["score"]
    v = val["score"]
    b = balance["score"]

    # Cross-category flags
    if q >= 75 and v >= 70:
        flags.append("cheap_quality")
    if q >= 75 and v <= 30:
        flags.append("high_quality_expensive")
    if g >= 75 and v <= 30:
        flags.append("strong_growth_expensive")
    if g < 25 and v >= 70:
        flags.append("cheap_but_weak_growth")
    if b <= 25:
        flags.append("balance_sheet_risk")

    # FCF quality flag
    if any("FCF margin" in p for p in quality["positives"]) and v >= 70:
        flags.append("fcf_quality")

    # Negative growth flag
    if g < 25:
        flags.append("negative_growth")

    # Data quality flag
    if len(missing_data) >= 4:
        flags.append("low_data_quality")

    return flags


def _compute_data_quality(missing_data: list[str]) -> str:
    missing_count = len(missing_data)
    if missing_count == 0:
        return "high"
    elif missing_count <= 3:
        return "medium"
    else:
        return "low"


def _compute_candidate_reason(quality: dict, growth: dict, val: dict, balance: dict) -> str:
    q = quality["score"]
    v = val["score"]

    if q >= 75 and v >= 70:
        return "High-quality company with attractive valuation."
    elif q >= 75 and v < 40:
        return "Strong business, but valuation looks demanding."
    elif v >= 70 and q < 40:
        return "Cheap valuation, but business quality is weak."
    elif q >= 75:
        return "High-quality business with moderate valuation."
    elif v >= 70:
        return "Attractive valuation with mixed quality."
    else:
        return "Mixed profile."


class RankingEngine:

    def rank(self, companies: list, results_by_company: dict[int, dict]) -> WatchlistRanking:
        scores: list[CompanyScore] = []

        for company in companies:
            results = results_by_company.get(company.id, {})
            financial = results.get("financial")
            valuation = results.get("valuation")

            quality = score_quality(financial)
            growth = score_growth(financial)
            balance = score_balance_sheet(financial)

            # Pass quality/growth/leverage context into valuation scoring so the
            # margin-of-safety component can adjust the required-return spread.
            dte = financial.debt_to_equity if financial else None
            val = score_valuation(
                valuation,
                debt_to_equity=dte,
                quality_score=quality["score"] if quality else None,
                growth_score=growth["score"] if growth else None,
            )

            total = (
                quality["score"] * 0.30
                + growth["score"] * 0.25
                + val["score"] * 0.30
                + balance["score"] * 0.15
            )

            missing_data = quality["missing"] + growth["missing"] + val["missing"] + balance["missing"]
            flags = _compute_flags(quality, growth, val, balance, missing_data)
            data_quality = _compute_data_quality(missing_data)
            candidate_reason = _compute_candidate_reason(quality, growth, val, balance)

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
                missing_data=missing_data,
                flags=flags,
                data_quality=data_quality,
                candidate_reason=candidate_reason,
            )
            scores.append(cs)

        scores.sort(key=lambda s: s.total_score, reverse=True)
        return WatchlistRanking(scores=scores)
