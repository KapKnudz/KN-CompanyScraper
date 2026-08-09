from __future__ import annotations
import math
from typing import TYPE_CHECKING

from kncompanyscraper.borsdata.kpi_ids import KpiIds

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


def _growth_score(value: float | None, scale: float) -> float | None:
    """Smoothly reward positive growth without a hard 100-point ceiling."""
    if value is None:
        return None
    if value <= 0:
        return 0.0
    return min(99.9, 100.0 * (1.0 - math.exp(-value / scale)))


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

def score_quality(
    financial: FinancialResult | None,
    fundamental_kpis: dict[int, float | None] | None = None,
) -> dict:
    if financial is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["financial data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []
    has_fundamental_kpis = fundamental_kpis is not None
    fundamental_kpis = fundamental_kpis or {}

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

    roic_value = fundamental_kpis.get(KpiIds.ROIC)
    roic = roic_value / 100 if roic_value is not None else None
    s = _linear_score(roic, 0.0, 0.20)
    if s is None and has_fundamental_kpis:
        missing.append("ROIC not available")
    elif s is not None:
        metrics.append(s)
        if roic >= 0.15:
            positives.append(f"ROIC {roic:.0%} — strong")
        elif roic <= 0.05:
            negatives.append(f"ROIC {roic:.0%} — weak")

    cash_conversion = getattr(financial, "cash_conversion", None)
    s = _linear_score(cash_conversion, 0.0, 1.0)
    if s is None:
        missing.append("Operating cash conversion not available")
    else:
        metrics.append(s)
        if cash_conversion >= 1.0:
            positives.append(
                f"Operating cash conversion {cash_conversion:.1f}x — strong"
            )
        elif cash_conversion < 0.5:
            negatives.append(
                f"Operating cash conversion {cash_conversion:.1f}x — weak"
            )

    margin_volatility = getattr(financial, "operating_margin_volatility", None)
    s = _inverted_linear_score(margin_volatility, 0.0, 0.10)
    if s is None:
        missing.append("Operating margin stability not available")
    else:
        metrics.append(s)
        if margin_volatility <= 0.03:
            positives.append("Operating margin has been stable")
        elif margin_volatility >= 0.10:
            negatives.append("Operating margin has been volatile")

    positive_fcf_ratio = getattr(financial, "positive_fcf_ratio", None)
    s = _linear_score(positive_fcf_ratio, 0.0, 1.0)
    if s is None:
        missing.append("FCF consistency not available")
    else:
        metrics.append(s)
        if positive_fcf_ratio == 1.0:
            positives.append("Free cash flow positive in every observed year")
        elif positive_fcf_ratio < 0.5:
            negatives.append("Free cash flow positive in fewer than half of observed years")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}


def score_growth(financial: FinancialResult | None) -> dict:
    if financial is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["financial data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []
    flags: list[str] = []

    revenue_per_share_growth = getattr(financial, "revenue_per_share_growth", None)
    ebit_per_share_growth = getattr(financial, "ebit_per_share_growth", None)
    net_income_per_share_growth = getattr(financial, "net_income_per_share_growth", None)
    per_share_growth_years = getattr(financial, "per_share_growth_years", 1)
    revenue_growth = revenue_per_share_growth if revenue_per_share_growth is not None else financial.revenue_growth
    ebit_growth = ebit_per_share_growth if ebit_per_share_growth is not None else financial.ebit_growth
    net_income_growth = (
        net_income_per_share_growth
        if net_income_per_share_growth is not None
        else financial.net_income_growth
    )
    per_share_basis = revenue_per_share_growth is not None

    revenue_turnaround = getattr(financial, "revenue_turnaround", False)
    revenue_deterioration = getattr(financial, "revenue_deterioration", False)
    revenue_years = getattr(financial, "revenue_growth_years", 1)
    if revenue_turnaround:
        metrics.append(50.0)
        positives.append("Revenue returned to positive territory")
    elif revenue_deterioration:
        metrics.append(0.0)
        negatives.append("Revenue turned non-positive")
    else:
        s = _growth_score(revenue_growth, 0.20)
        if s is not None:
            metrics.append(s)
    if revenue_growth is None and not revenue_turnaround and not revenue_deterioration:
        missing.append("Revenue growth not available")
    elif revenue_growth is not None:
        years = per_share_growth_years if per_share_basis else revenue_years
        period = f"{years}y CAGR" if years > 1 else "YoY"
        label = "Revenue/share growth" if per_share_basis else "Revenue growth"
        if revenue_growth >= 0.15:
            positives.append(f"{label} {revenue_growth:.0%} ({period}) — strong")
        elif revenue_growth <= -0.05:
            negatives.append(f"{label} {revenue_growth:.0%} ({period}) — declining")

    ebit_turnaround = getattr(financial, "ebit_turnaround", False)
    ebit_deterioration = getattr(financial, "ebit_deterioration", False)
    ebit_years = getattr(financial, "ebit_growth_years", 1)
    if ebit_turnaround:
        metrics.append(50.0)
        positives.append("EBIT returned to profit; percentage growth is not meaningful")
    elif ebit_deterioration:
        metrics.append(0.0)
        negatives.append("EBIT turned negative")
    else:
        s = _growth_score(ebit_growth, 0.30)
        if s is not None:
            if getattr(financial, "earnings_growth_one_off_risk", False):
                s = min(s, 60.0)
            metrics.append(s)
    if ebit_growth is None and not ebit_turnaround and not ebit_deterioration:
        missing.append("EBIT growth not available")
    elif ebit_growth is not None:
        years = per_share_growth_years if ebit_per_share_growth is not None else ebit_years
        period = f"{years}y CAGR" if years > 1 else "YoY"
        label = "EBIT/share growth" if ebit_per_share_growth is not None else "EBIT growth"
        if ebit_growth >= 0.15:
            positives.append(f"{label} {ebit_growth:.0%} ({period}) — strong")
        elif ebit_growth <= -0.05:
            negatives.append(f"{label} {ebit_growth:.0%} ({period}) — declining")

    net_income_turnaround = getattr(financial, "net_income_turnaround", False)
    net_income_deterioration = getattr(financial, "net_income_deterioration", False)
    net_income_years = getattr(financial, "net_income_growth_years", 1)
    if net_income_turnaround:
        metrics.append(50.0)
        positives.append("Net income returned to profit; percentage growth is not meaningful")
    elif net_income_deterioration:
        metrics.append(0.0)
        negatives.append("Net income turned negative")
    else:
        s = _growth_score(net_income_growth, 0.30)
        if s is not None:
            if getattr(financial, "earnings_growth_one_off_risk", False):
                s = min(s, 60.0)
            metrics.append(s)
    if net_income_growth is None and not net_income_turnaround and not net_income_deterioration:
        missing.append("Net income growth not available")
    elif net_income_growth is not None:
        years = (
            per_share_growth_years
            if net_income_per_share_growth is not None
            else net_income_years
        )
        period = f"{years}y CAGR" if years > 1 else "YoY"
        label = (
            "Net income/share growth"
            if net_income_per_share_growth is not None
            else "Net income growth"
        )
        if net_income_growth >= 0.15:
            positives.append(f"{label} {net_income_growth:.0%} ({period}) — strong")
        elif net_income_growth <= -0.05:
            negatives.append(f"{label} {net_income_growth:.0%} ({period}) — declining")

    recent_revenue_growth = getattr(financial, "recent_revenue_growth", None)
    if recent_revenue_growth is not None:
        metrics.append(_growth_score(recent_revenue_growth, 0.20) or 0.0)
        if getattr(financial, "recent_growth_acceleration", False):
            positives.append(
                f"Latest-quarter revenue growth {recent_revenue_growth:.0%} — accelerating"
            )
        elif getattr(financial, "recent_growth_slowdown", False):
            negatives.append(
                f"Latest-quarter revenue growth {recent_revenue_growth:.0%} — slowing"
            )
            flags.append("recent_growth_slowdown")

    if getattr(financial, "share_dilution", False):
        negatives.append(
            f"Share count growth {getattr(financial, 'share_count_growth', 0.0):.0%} — dilution"
        )
        flags.append("share_dilution")

    if getattr(financial, "earnings_growth_one_off_risk", False):
        negatives.append("Exceptional earnings jump versus revenue — possible one-off or base effect")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {
        "score": score,
        "positives": positives,
        "negatives": negatives,
        "missing": missing,
        "flags": flags,
    }


def score_valuation(
    valuation: ValuationResult | None,
    debt_to_equity: float | None = None,
    quality_score: float | None = None,
    growth_score: float | None = None,
    reverse_dcf: dict | None = None,
) -> dict:
    if valuation is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["valuation data not available"]}

    scored: list[tuple[float | None, float]] = []  # (score, weight)
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    # Prefer raw-derived yields when available (fresher, from latest close).
    # Fall back to KPI-derived yields otherwise.
    raw_earnings_yield = getattr(valuation, "raw_earnings_yield", None)
    raw_fcf_yield = getattr(valuation, "raw_fcf_yield", None)
    earnings_yield = (
        raw_earnings_yield if raw_earnings_yield is not None else valuation.earnings_yield
    )
    fcf_yield = raw_fcf_yield if raw_fcf_yield is not None else valuation.free_cash_flow_yield

    # --- FCF yield: 0→0, 10%→100  (weight: 24%) ---
    s = _linear_score(fcf_yield, 0.0, 0.10)
    if s is None:
        missing.append("FCF yield not available")
    else:
        scored.append((s, 0.24))
        if fcf_yield >= 0.08:
            positives.append(f"FCF yield {fcf_yield:.1%} — attractive")
        elif fcf_yield < 0:
            negatives.append(f"Free cash flow is negative (yield {fcf_yield:.1%})")
        elif fcf_yield <= 0.02:
            negatives.append(f"FCF yield {fcf_yield:.1%} — expensive")

    # --- Earnings yield: 0→0, 10%→100  (weight: 16%) ---
    s = _linear_score(earnings_yield, 0.0, 0.10)
    if s is None:
        missing.append("Earnings yield not available")
    else:
        scored.append((s, 0.16))
        if earnings_yield >= 0.08:
            positives.append(f"Earnings yield {earnings_yield:.1%} — attractive")
        elif earnings_yield <= 0.02:
            negatives.append(f"Earnings yield {earnings_yield:.1%} — expensive")

    # --- EV/EBIT percentile (inverted)  (weight: 16%) ---
    s = _inverted_linear_score(valuation.ev_ebit_percentile, 0.0, 100.0)
    if s is None:
        missing.append("EV/EBIT percentile not available")
    else:
        scored.append((s, 0.16))
        if valuation.ev_ebit_percentile <= 20:
            positives.append(f"EV/EBIT at {valuation.ev_ebit_percentile:.0f}th percentile — cheap vs history")
        elif valuation.ev_ebit_percentile >= 80:
            negatives.append(f"EV/EBIT at {valuation.ev_ebit_percentile:.0f}th percentile — expensive vs history")

    # --- PE percentile (inverted)  (weight: 12%) ---
    s = _inverted_linear_score(valuation.pe_percentile, 0.0, 100.0)
    if s is None:
        missing.append("PE percentile not available")
    else:
        scored.append((s, 0.12))
        if valuation.pe_percentile <= 20:
            positives.append(f"PE at {valuation.pe_percentile:.0f}th percentile — cheap vs history")
        elif valuation.pe_percentile >= 80:
            negatives.append(f"PE at {valuation.pe_percentile:.0f}th percentile — expensive vs history")

    # --- Margin of safety  (weight: 12%) ---
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
        scored.append((s, 0.12))
        if mos >= 0.03:
            positives.append(f"Margin of safety {mos:.1%} — large discount to required return")
        elif fcf_yield is not None and fcf_yield < 0:
            negatives.append("No FCF-based margin of safety while free cash flow is negative")
        elif mos <= -0.03:
            negatives.append(f"Margin of safety {mos:.1%} — trading above required return")

    if reverse_dcf is not None and reverse_dcf.get("score") is not None:
        scored.append((reverse_dcf["score"], 0.20))
        positives.extend(reverse_dcf.get("positives", []))
        negatives.extend(reverse_dcf.get("negatives", []))

    # Weighted average. Without reverse DCF, the uniformly rescaled legacy
    # weights normalize back to exactly the prior valuation score.
    if scored:
        total_weight = sum(w for _, w in scored)
        score = sum(s * w for s, w in scored) / total_weight if total_weight > 0 else 0.0
    else:
        score = 0.0

    return {
        "score": score,
        "reverse_dcf_score": reverse_dcf.get("score") if reverse_dcf else None,
        "positives": positives,
        "negatives": negatives,
        "missing": missing,
        "flags": reverse_dcf.get("flags", []) if reverse_dcf else [],
    }


def score_balance_sheet(
    financial: FinancialResult | None,
    fundamental_kpis: dict[int, float | None] | None = None,
) -> dict:
    if financial is None:
        return {"score": 0.0, "positives": [], "negatives": [], "missing": ["financial data not available"]}

    metrics: list[float] = []
    missing: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []
    has_fundamental_kpis = fundamental_kpis is not None
    fundamental_kpis = fundamental_kpis or {}

    dte = financial.debt_to_equity
    net_debt = getattr(financial, "net_debt", None)
    equity = getattr(financial, "equity", None)
    if equity is not None and equity <= 0:
        metrics.append(0.0)
        negatives.append("Negative equity — balance-sheet risk")
    elif net_debt is not None and net_debt < 0:
        metrics.append(100.0)
        positives.append("Net cash position")
    elif dte is None:
        missing.append("Debt/equity not available")
    elif dte < 0:
        # Legacy/fallback path when the underlying signs are unavailable.
        metrics.append(0.0)
        negatives.append(f"D/E {dte:.1f}x — negative equity or invalid")
    elif dte == 0:
        # No debt — excellent
        metrics.append(100.0)
        positives.append("Net D/E 0.0x — no debt")
    else:
        s = _inverted_linear_score(dte, 0.0, 2.0)
        metrics.append(s)
        if dte <= 0.3:
            positives.append(f"Net D/E {dte:.1f}x — low leverage")
        elif dte >= 1.5:
            negatives.append(f"Net D/E {dte:.1f}x — high leverage")

    net_debt_ebitda = fundamental_kpis.get(KpiIds.NET_DEBT_EBITDA)
    if equity is None or equity > 0:
        s = _inverted_linear_score(net_debt_ebitda, 0.0, 4.0)
        if s is None and has_fundamental_kpis:
            missing.append("Net debt/EBITDA not available")
        elif s is not None:
            metrics.append(s)
            if net_debt_ebitda <= 1:
                positives.append(f"Net debt/EBITDA {net_debt_ebitda:.1f}x — low")
            elif net_debt_ebitda >= 3:
                negatives.append(f"Net debt/EBITDA {net_debt_ebitda:.1f}x — high")

    score = sum(metrics) / len(metrics) if metrics else 0.0
    return {"score": score, "positives": positives, "negatives": negatives, "missing": missing}
