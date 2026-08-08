from kncompanyscraper.analysis.ranking.score_rules import (
    _growth_score,
    _inverted_linear_score,
    _linear_score,
)
from kncompanyscraper.borsdata.kpi_ids import KpiIds


def ranking_model_for_branch(branch_id: int | None) -> str:
    if branch_id == 75:
        return "property"
    if branch_id in (68, 69, 70):
        return "bank"
    return "general"


def _result(scored, positives=None, negatives=None, missing=None, flags=None):
    available = [(score, weight) for score, weight in scored if score is not None]
    total_weight = sum(weight for _, weight in available)
    score = (
        sum(score * weight for score, weight in available) / total_weight
        if total_weight
        else 0.0
    )
    return {
        "score": score,
        "positives": positives or [],
        "negatives": negatives or [],
        "missing": missing or [],
        "flags": flags or [],
        "available": bool(available),
    }


def score_property(financial, valuation, kpis: dict[int, float | None]):
    occupancy = kpis.get(KpiIds.PROPERTY_OCCUPANCY)
    interest_coverage = kpis.get(KpiIds.PROPERTY_INTEREST_COVERAGE)
    ltv = kpis.get(KpiIds.PROPERTY_LTV)
    nav_discount = kpis.get(KpiIds.PROPERTY_NAV_DISCOUNT)
    price_to_income = kpis.get(KpiIds.PROPERTY_PRICE_TO_INCOME)

    quality_missing = [] if occupancy is not None else ["Property occupancy not available"]
    quality_positives = []
    quality_negatives = []
    quality_flags = []
    if occupancy is not None:
        if occupancy >= 95:
            quality_positives.append(f"Occupancy {occupancy:.1f}% — strong")
        elif occupancy < 90:
            quality_negatives.append(f"Occupancy {occupancy:.1f}% — low")
            quality_flags.append("low_occupancy")
    quality = _result(
        [(_linear_score(occupancy, 85.0, 100.0), 1.0)],
        quality_positives,
        quality_negatives,
        quality_missing,
        quality_flags,
    )

    revenue_growth = None
    if financial:
        revenue_growth = (
            financial.revenue_per_share_growth
            if financial.revenue_per_share_growth is not None
            else financial.revenue_growth
        )
    growth_missing = [] if revenue_growth is not None else ["Property revenue growth not available"]
    growth_positives = []
    growth_negatives = []
    if revenue_growth is not None:
        years = getattr(financial, "revenue_growth_years", 1)
        period = f"{years}y CAGR" if years > 1 else "YoY"
        label = (
            "Property revenue/share growth"
            if financial.revenue_per_share_growth is not None
            else "Property revenue growth"
        )
        if revenue_growth >= 0.10:
            growth_positives.append(
                f"{label} {revenue_growth:.0%} ({period}) — strong"
            )
        elif revenue_growth < 0:
            growth_negatives.append(
                f"{label} {revenue_growth:.0%} ({period}) — declining"
            )
    growth_flags = []
    if financial and financial.share_dilution:
        growth_negatives.append(
            f"Share count growth {financial.share_count_growth:.0%} — dilution"
        )
        growth_flags.append("share_dilution")
    growth = _result(
        [(_growth_score(revenue_growth, 0.15), 1.0)],
        growth_positives,
        growth_negatives,
        growth_missing,
        growth_flags,
    )

    dividend_yield = valuation.dividend_yield if valuation else None
    valuation_scored = [
        (_inverted_linear_score(nav_discount, -30.0, 20.0), 0.45),
        (_inverted_linear_score(price_to_income, 8.0, 25.0), 0.35),
        (_linear_score(dividend_yield, 0.0, 8.0), 0.20),
    ]
    valuation_missing = []
    if nav_discount is None:
        valuation_missing.append("Property NAV discount not available")
    if price_to_income is None:
        valuation_missing.append("P/property income not available")
    if dividend_yield is None:
        valuation_missing.append("Dividend yield not available")
    valuation_positives = []
    valuation_negatives = []
    valuation_flags = []
    if nav_discount is not None:
        if nav_discount <= -15:
            valuation_positives.append(f"NAV discount {-nav_discount:.1f}% — attractive")
        elif nav_discount > 0:
            valuation_negatives.append(f"NAV premium {nav_discount:.1f}%")
            valuation_flags.append("nav_premium")
    if price_to_income is not None:
        if price_to_income <= 12:
            valuation_positives.append(f"P/property income {price_to_income:.1f}x — attractive")
        elif price_to_income >= 22:
            valuation_negatives.append(f"P/property income {price_to_income:.1f}x — demanding")
    valuation_result = _result(
        valuation_scored,
        valuation_positives,
        valuation_negatives,
        valuation_missing,
        valuation_flags,
    )

    balance_scored = [
        (_inverted_linear_score(ltv, 30.0, 65.0), 0.60),
        (_linear_score(interest_coverage, 1.0, 4.0), 0.40),
    ]
    balance_missing = []
    if ltv is None:
        balance_missing.append("Property LTV not available")
    if interest_coverage is None:
        balance_missing.append("Property interest coverage not available")
    balance_positives = []
    balance_negatives = []
    balance_flags = []
    if ltv is not None:
        if ltv <= 40:
            balance_positives.append(f"LTV {ltv:.1f}% — conservative")
        elif ltv >= 55:
            balance_negatives.append(f"LTV {ltv:.1f}% — high")
            balance_flags.append("high_ltv")
    if interest_coverage is not None:
        if interest_coverage >= 3:
            balance_positives.append(f"Interest coverage {interest_coverage:.1f}x — strong")
        elif interest_coverage < 1.5:
            balance_negatives.append(f"Interest coverage {interest_coverage:.1f}x — weak")
            balance_flags.append("weak_interest_coverage")
    balance = _result(
        balance_scored,
        balance_positives,
        balance_negatives,
        balance_missing,
        balance_flags,
    )

    return quality, growth, valuation_result, balance


def score_bank(financial, valuation, kpis: dict[int, float | None]):
    roe = financial.roe if financial else None
    cost_income = kpis.get(KpiIds.BANK_COST_INCOME)
    credit_losses = kpis.get(KpiIds.BANK_CREDIT_LOSSES)

    quality_scored = [
        (_linear_score(roe, 0.0, 0.20), 0.40),
        (_inverted_linear_score(cost_income, 30.0, 70.0), 0.35),
        (_inverted_linear_score(credit_losses, 0.0, 1.0), 0.25),
    ]
    quality_missing = []
    if roe is None:
        quality_missing.append("Bank ROE not available")
    if cost_income is None:
        quality_missing.append("Bank cost/income not available")
    if credit_losses is None:
        quality_missing.append("Bank credit losses not available")
    quality_positives = []
    quality_negatives = []
    quality_flags = []
    if roe is not None:
        if roe >= 0.15:
            quality_positives.append(f"ROE {roe:.0%} — strong")
        elif roe < 0.08:
            quality_negatives.append(f"ROE {roe:.0%} — weak")
    if cost_income is not None:
        if cost_income <= 40:
            quality_positives.append(f"Cost/income {cost_income:.1f}% — efficient")
        elif cost_income >= 60:
            quality_negatives.append(f"Cost/income {cost_income:.1f}% — high")
            quality_flags.append("poor_cost_efficiency")
    if credit_losses is not None and credit_losses >= 0.75:
        quality_negatives.append(f"Credit losses {credit_losses:.2f}% — elevated")
        quality_flags.append("high_credit_losses")
    quality = _result(
        quality_scored,
        quality_positives,
        quality_negatives,
        quality_missing,
        quality_flags,
    )

    earnings_growth = None
    if financial:
        earnings_growth = (
            financial.net_income_per_share_growth
            if financial.net_income_per_share_growth is not None
            else financial.net_income_growth
        )
    growth_missing = [] if earnings_growth is not None else ["Bank earnings growth not available"]
    growth_positives = []
    growth_negatives = []
    if earnings_growth is not None:
        years = getattr(financial, "net_income_growth_years", 1)
        period = f"{years}y CAGR" if years > 1 else "YoY"
        label = (
            "Bank earnings/share growth"
            if financial.net_income_per_share_growth is not None
            else "Bank earnings growth"
        )
        if earnings_growth >= 0.10:
            growth_positives.append(f"{label} {earnings_growth:.0%} ({period}) — strong")
        elif earnings_growth < 0:
            growth_negatives.append(f"{label} {earnings_growth:.0%} ({period}) — declining")
    growth_flags = []
    if financial and financial.share_dilution:
        growth_negatives.append(
            f"Share count growth {financial.share_count_growth:.0%} — dilution"
        )
        growth_flags.append("share_dilution")
    growth = _result(
        [(_growth_score(earnings_growth, 0.20), 1.0)],
        growth_positives,
        growth_negatives,
        growth_missing,
        growth_flags,
    )

    pb_relative = valuation.pb_vs_5y_avg if valuation else None
    pe_percentile = valuation.pe_percentile if valuation else None
    dividend_yield = valuation.dividend_yield if valuation else None
    valuation_missing = []
    if pb_relative is None:
        valuation_missing.append("P/B relative to history not available")
    if pe_percentile is None:
        valuation_missing.append("P/E percentile not available")
    if dividend_yield is None:
        valuation_missing.append("Dividend yield not available")
    valuation_result = _result(
        [
            (_inverted_linear_score(pb_relative, 0.6, 1.4), 0.40),
            (_inverted_linear_score(pe_percentile, 0.0, 100.0), 0.35),
            (_linear_score(dividend_yield, 0.0, 8.0), 0.25),
        ],
        missing=valuation_missing,
    )

    cet1 = kpis.get(KpiIds.BANK_CET1)
    capital_adequacy = kpis.get(KpiIds.BANK_CAPITAL_ADEQUACY)
    lcr = kpis.get(KpiIds.BANK_LCR)
    balance_missing = []
    if cet1 is None:
        balance_missing.append("Bank CET1 not available")
    if capital_adequacy is None:
        balance_missing.append("Bank capital adequacy not available")
    if lcr is None:
        balance_missing.append("Bank LCR not available")
    balance_positives = []
    balance_negatives = []
    balance_flags = []
    if cet1 is not None:
        if cet1 >= 18:
            balance_positives.append(f"CET1 {cet1:.1f}% — strong absolute ratio")
        elif cet1 < 12:
            balance_negatives.append(f"CET1 {cet1:.1f}% — low absolute ratio")
            balance_flags.append("weak_capital")
    if lcr is not None:
        if lcr >= 150:
            balance_positives.append(f"LCR {lcr:.0f}% — strong")
        elif lcr < 100:
            balance_negatives.append(f"LCR {lcr:.0f}% — below 100%")
            balance_flags.append("weak_liquidity")
    balance = _result(
        [
            (_linear_score(cet1, 10.0, 20.0), 0.45),
            (_linear_score(capital_adequacy, 15.0, 25.0), 0.25),
            (_linear_score(lcr, 100.0, 200.0), 0.30),
        ],
        balance_positives,
        balance_negatives,
        balance_missing,
        balance_flags,
    )

    return quality, growth, valuation_result, balance
