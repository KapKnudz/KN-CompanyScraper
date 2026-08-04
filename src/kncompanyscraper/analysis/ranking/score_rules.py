from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kncompanyscraper.analysis.financial.financial_result import FinancialResult
    from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _linear_score(value: float | None, floor: float, ceiling: float) -> float | None:
    """Score value linearly: 0 at floor, 100 at ceiling. None → None."""
    if value is None:
        return None
    if value <= floor:
        return 0.0
    if value >= ceiling:
        return 100.0
    return (value - floor) / (ceiling - floor) * 100.0


def _inverted_linear_score(value: float | None, floor: float, ceiling: float) -> float | None:
    """Inverted linear: 100 at floor (best), 0 at ceiling (worst). None → None."""
    if value is None:
        return None
    if value <= floor:
        return 100.0
    if value >= ceiling:
        return 0.0
    return (ceiling - value) / (ceiling - floor) * 100.0


# ---------------------------------------------------------------------------
# Category scoring
# ---------------------------------------------------------------------------

def score_quality(financial: FinancialResult | None) -> dict:
    if financial is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["financial data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    # ROE: 0→0, 25%→100
    s = _linear_score(financial.roe, 0.0, 0.25)
    if s is None:
        missing.append("ROE not available")
    else:
        metrics.append(s)
        if financial.roe >= 0.20:
            positives.append(f"ROE {financial.roe:.0%} — strong")
        elif financial.roe <= 0.05:
            negatives.append(f"ROE {financial.roe:.0%} — weak")

    # ROA: 0→0, 15%→100
    s = _linear_score(financial.roa, 0.0, 0.15)
    if s is None:
        missing.append("ROA not available")
    else:
        metrics.append(s)
        if financial.roa >= 0.10:
            positives.append(f"ROA {financial.roa:.0%} — strong")
        elif financial.roa <= 0.02:
            negatives.append(f"ROA {financial.roa:.0%} — weak")

    # Net margin: 0→0, 20%→100
    s = _linear_score(financial.net_margin, 0.0, 0.20)
    if s is None:
        missing.append("Net margin not available")
    else:
        metrics.append(s)
        if financial.net_margin >= 0.15:
            positives.append(f"Net margin {financial.net_margin:.0%} — strong")
        elif financial.net_margin <= 0.03:
            negatives.append(f"Net margin {financial.net_margin:.0%} — low")

    # FCF margin: 0→0, 20%→100
    s = _linear_score(financial.fcf_margin, 0.0, 0.20)
    if s is None:
        missing.append("FCF margin not available")
    else:
        metrics.append(s)
        if financial.fcf_margin >= 0.15:
            positives.append(f"FCF margin {financial.fcf_margin:.0%} — strong")
        elif financial.fcf_margin <= 0.03:
            negatives.append(f"FCF margin {financial.fcf_margin:.0%} — low")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}


def score_growth(financial: FinancialResult | None) -> dict:
    if financial is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["financial data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    # Revenue growth: 0→0, 20%→100
    s = _linear_score(financial.revenue_growth, 0.0, 0.20)
    if s is None:
        missing.append("Revenue growth not available")
    else:
        metrics.append(s)
        if financial.revenue_growth >= 0.15:
            positives.append(f"Revenue growth {financial.revenue_growth:.0%} — strong")
        elif financial.revenue_growth <= -0.05:
            negatives.append(f"Revenue growth {financial.revenue_growth:.0%} — declining")

    # EBIT growth: 0→0, 20%→100
    s = _linear_score(financial.ebit_growth, 0.0, 0.20)
    if s is None:
        missing.append("EBIT growth not available")
    else:
        metrics.append(s)
        if financial.ebit_growth >= 0.15:
            positives.append(f"EBIT growth {financial.ebit_growth:.0%} — strong")
        elif financial.ebit_growth <= -0.05:
            negatives.append(f"EBIT growth {financial.ebit_growth:.0%} — declining")

    # Net income growth: 0→0, 20%→100
    s = _linear_score(financial.net_income_growth, 0.0, 0.20)
    if s is None:
        missing.append("Net income growth not available")
    else:
        metrics.append(s)
        if financial.net_income_growth >= 0.15:
            positives.append(f"Net income growth {financial.net_income_growth:.0%} — strong")
        elif financial.net_income_growth <= -0.05:
            negatives.append(f"Net income growth {financial.net_income_growth:.0%} — declining")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}


def score_valuation(valuation: ValuationResult | None) -> dict:
    if valuation is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["valuation data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    # Earnings yield: 0→0, 10%→100
    s = _linear_score(valuation.earnings_yield, 0.0, 0.10)
    if s is None:
        missing.append("Earnings yield not available")
    else:
        metrics.append(s)
        if valuation.earnings_yield >= 0.08:
            positives.append(f"Earnings yield {valuation.earnings_yield:.1%} — attractive")
        elif valuation.earnings_yield <= 0.02:
            negatives.append(f"Earnings yield {valuation.earnings_yield:.1%} — expensive")

    # FCF yield: 0→0, 10%→100
    s = _linear_score(valuation.free_cash_flow_yield, 0.0, 0.10)
    if s is None:
        missing.append("FCF yield not available")
    else:
        metrics.append(s)
        if valuation.free_cash_flow_yield >= 0.08:
            positives.append(f"FCF yield {valuation.free_cash_flow_yield:.1%} — attractive")
        elif valuation.free_cash_flow_yield <= 0.02:
            negatives.append(f"FCF yield {valuation.free_cash_flow_yield:.1%} — expensive")

    # PE percentile (inverted): 0=cheapest→100, 100=most expensive→0
    s = _inverted_linear_score(valuation.pe_percentile, 0.0, 100.0)
    if s is None:
        missing.append("PE percentile not available")
    else:
        metrics.append(s)
        if valuation.pe_percentile <= 20:
            positives.append(f"PE at {valuation.pe_percentile:.0f}th percentile — cheap vs history")
        elif valuation.pe_percentile >= 80:
            negatives.append(f"PE at {valuation.pe_percentile:.0f}th percentile — expensive vs history")

    # EV/EBIT percentile (inverted)
    s = _inverted_linear_score(valuation.ev_ebit_percentile, 0.0, 100.0)
    if s is None:
        missing.append("EV/EBIT percentile not available")
    else:
        metrics.append(s)
        if valuation.ev_ebit_percentile <= 20:
            positives.append(f"EV/EBIT at {valuation.ev_ebit_percentile:.0f}th percentile — cheap vs history")
        elif valuation.ev_ebit_percentile >= 80:
            negatives.append(f"EV/EBIT at {valuation.ev_ebit_percentile:.0f}th percentile — expensive vs history")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}


def score_balance_sheet(financial: FinancialResult | None) -> dict:
    if financial is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["financial data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    dte = financial.debt_to_equity
    if dte is None:
        missing.append("Debt/equity not available")
    elif dte <= 0:
        # Negative equity = insolvent, worst case
        metrics.append(0.0)
        negatives.append(f"D/E {dte:.1f}x — negative equity")
    else:
        s = _inverted_linear_score(dte, 0.0, 2.0)
        metrics.append(s)
        if dte <= 0.3:
            positives.append(f"D/E {dte:.1f}x — low leverage")
        elif dte >= 1.5:
            negatives.append(f"D/E {dte:.1f}x — high leverage")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}
