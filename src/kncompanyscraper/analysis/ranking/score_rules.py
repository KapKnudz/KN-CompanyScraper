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
# Margin of safety
# ---------------------------------------------------------------------------

# Calibrated for the Swedish market. Adjust if applying to other markets.
RISK_FREE_RATE = 0.03       # ~Swedish 10Y government bond
EQUITY_RISK_PREMIUM = 0.05  # standard ERP


def compute_margin_of_safety(
    fcf_yield: float | None,
    debt_to_equity: float | None = None,
    quality_score: float = 50.0,
    growth_score: float = 50.0,
    risk_free_rate: float = RISK_FREE_RATE,
    equity_risk_premium: float = EQUITY_RISK_PREMIUM,
) -> float | None:
    """Required-return spread: actual FCF yield minus required yield.

    A large positive margin suggests undervaluation; a negative margin
    means the stock is expensive unless quality or growth is exceptional.

    required_yield = risk_free_rate + equity_risk_premium
                     + leverage_penalty - quality_bonus - growth_bonus
    """
    if fcf_yield is None:
        return None

    # Leverage penalty: 0% at D/E=0, scaling linearly to ~5% at D/E=2.0
    if debt_to_equity is not None and debt_to_equity > 0:
        leverage_penalty = min(debt_to_equity * 0.025, 0.05)
    else:
        leverage_penalty = 0.0

    # Quality bonus: high-quality companies deserve a lower required return.
    # Scales from 0% at quality=50 (neutral) to 3% at quality=100.
    quality_bonus = max(0.0, (quality_score - 50.0) / 50.0 * 0.03)

    # Growth bonus: fast growers deserve a lower required return.
    # Scales from 0% at growth=50 (neutral) to 2% at growth=100.
    growth_bonus = max(0.0, (growth_score - 50.0) / 50.0 * 0.02)

    required_yield = (
        risk_free_rate
        + equity_risk_premium
        + leverage_penalty
        - quality_bonus
        - growth_bonus
    )

    return fcf_yield - required_yield


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


def score_valuation(
    valuation: ValuationResult | None,
    debt_to_equity: float | None = None,
    quality_score: float | None = None,
    growth_score: float | None = None,
) -> dict:
    if valuation is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["valuation data not available"]}

    scored: list[tuple[float | None, float]] = []  # (score, weight)
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    # Prefer raw-derived yields when available (fresher, from latest close).
    # Fall back to KPI-derived yields otherwise.
    earnings_yield = valuation.raw_earnings_yield or valuation.earnings_yield
    fcf_yield = valuation.raw_fcf_yield or valuation.free_cash_flow_yield
    earnings_yield = getattr(valuation, "raw_earnings_yield", None) or valuation.earnings_yield
    fcf_yield = getattr(valuation, "raw_fcf_yield", None) or valuation.free_cash_flow_yield

    # --- FCF yield: 0→0, 10%→100  (weight: 30%) ---
    s = _linear_score(fcf_yield, 0.0, 0.10)
    if s is None:
        missing.append("FCF yield not available")
    else:
        scored.append((s, 0.30))
        if fcf_yield >= 0.08:
            positives.append(f"FCF yield {fcf_yield:.1%} — attractive")
        elif fcf_yield <= 0.02:
            negatives.append(f"FCF yield {fcf_yield:.1%} — expensive")

    # --- Earnings yield: 0→0, 10%→100  (weight: 20%) ---
    s = _linear_score(earnings_yield, 0.0, 0.10)
    if s is None:
        missing.append("Earnings yield not available")
    else:
        scored.append((s, 0.20))
        if earnings_yield >= 0.08:
            positives.append(f"Earnings yield {earnings_yield:.1%} — attractive")
        elif earnings_yield <= 0.02:
            negatives.append(f"Earnings yield {earnings_yield:.1%} — expensive")

    # --- EV/EBIT percentile (inverted)  (weight: 20%) ---
    s = _inverted_linear_score(valuation.ev_ebit_percentile, 0.0, 100.0)
    if s is None:
        missing.append("EV/EBIT percentile not available")
    else:
        scored.append((s, 0.20))
        if valuation.ev_ebit_percentile <= 20:
            positives.append(f"EV/EBIT at {valuation.ev_ebit_percentile:.0f}th percentile — cheap vs history")
        elif valuation.ev_ebit_percentile >= 80:
            negatives.append(f"EV/EBIT at {valuation.ev_ebit_percentile:.0f}th percentile — expensive vs history")

    # --- PE percentile (inverted)  (weight: 15%) ---
    s = _inverted_linear_score(valuation.pe_percentile, 0.0, 100.0)
    if s is None:
        missing.append("PE percentile not available")
    else:
        scored.append((s, 0.15))
        if valuation.pe_percentile <= 20:
            positives.append(f"PE at {valuation.pe_percentile:.0f}th percentile — cheap vs history")
        elif valuation.pe_percentile >= 80:
            negatives.append(f"PE at {valuation.pe_percentile:.0f}th percentile — expensive vs history")

    # --- Margin of safety  (weight: 15%) ---
    mos = compute_margin_of_safety(
        fcf_yield,
        debt_to_equity=debt_to_equity,
        quality_score=quality_score if quality_score is not None else 50.0,
        growth_score=growth_score if growth_score is not None else 50.0,
    )
    # Margin of safety: -5% → 0, +5% → 100
    s = _linear_score(mos, -0.05, 0.05)
    if s is None:
        missing.append("Margin of safety not available")
    else:
        scored.append((s, 0.15))
        if mos >= 0.03:
            positives.append(f"Margin of safety {mos:.1%} — large discount to required return")
        elif mos <= -0.03:
            negatives.append(f"Margin of safety {mos:.1%} — trading above required return")

    # Weighted average
    if scored:
        total_weight = sum(w for _, w in scored)
        score = sum(s * w for s, w in scored) / total_weight if total_weight > 0 else 0.0
    else:
        score = 0.0

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
    elif dte < 0:
        # Negative equity — insolvent or invalid data
        metrics.append(0.0)
        negatives.append(f"D/E {dte:.1f}x — negative equity or invalid")
    elif dte == 0:
        # No debt — excellent
        metrics.append(100.0)
        positives.append("D/E 0.0x — no debt")
    else:
        s = _inverted_linear_score(dte, 0.0, 2.0)
        metrics.append(s)
        if dte <= 0.3:
            positives.append(f"D/E {dte:.1f}x — low leverage")
        elif dte >= 1.5:
            negatives.append(f"D/E {dte:.1f}x — high leverage")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}
