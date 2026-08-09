"""Ranking policy for market-implied reverse-DCF expectations."""

import math
from statistics import median


_MATERIAL_GAPS = {
    "revenue_growth": 0.10,
    "ebit_margin": 0.10,
    "terminal_growth": 0.02,
}


def _smooth_score(normalized_gap: float) -> float:
    """Map normalized headroom to 0-100 without finite-value saturation."""
    exponent = math.log(9.0) * normalized_gap
    if exponent >= 0:
        return 100.0 / (1.0 + math.exp(-exponent))
    exp_value = math.exp(exponent)
    return 100.0 * exp_value / (1.0 + exp_value)


def _outside_price_distance(current_price: float, modeled_endpoint: float) -> float:
    """Return a log-scaled endpoint distance relative to the positive market price."""
    return math.log2(1.0 + abs(modeled_endpoint - current_price) / current_price)


def score_reverse_dcf(analysis) -> dict:
    """Score how demanding market expectations are versus the DCF baseline.

    Each assumption has zero normalized headroom when its implied value matches
    the evidence-based baseline. The median keeps the three correlated
    one-variable solves from behaving like three independent signals. A smooth
    transform maps half a material gap to 75/25 and a full gap to 90/10 without
    clipping finite values to 100/0.
    """
    unavailable = {
        "score": None,
        "positives": [],
        "negatives": [],
        "flags": [],
    }
    if (
        analysis is None
        or getattr(analysis, "status", None) != "available"
        or analysis.assumptions is None
        or not analysis.implied_expectations
    ):
        return unavailable

    normalized_gaps: list[float] = []
    for assumption, material_gap in _MATERIAL_GAPS.items():
        expectation = analysis.implied_expectations.get(assumption)
        if expectation is None:
            continue
        if expectation.status == "solved" and expectation.implied_value is not None:
            baseline = getattr(analysis.assumptions, assumption)
            gap = baseline - expectation.implied_value
            normalized_gaps.append(gap / material_gap)
        elif expectation.status == "outside_bounds":
            price_range = expectation.modeled_price_range
            if price_range is None or analysis.current_price is None:
                continue
            if analysis.current_price < price_range[0]:
                boundary_gap = (
                    getattr(analysis.assumptions, assumption)
                    - expectation.lower_bound
                ) / material_gap
                price_distance = _outside_price_distance(
                    analysis.current_price, price_range[0]
                )
                normalized_gaps.append(boundary_gap + price_distance)
            elif analysis.current_price > price_range[1]:
                boundary_gap = (
                    getattr(analysis.assumptions, assumption)
                    - expectation.upper_bound
                ) / material_gap
                price_distance = _outside_price_distance(
                    analysis.current_price, price_range[1]
                )
                normalized_gaps.append(boundary_gap - price_distance)

    if not normalized_gaps:
        return unavailable

    score = _smooth_score(median(normalized_gaps))
    positives: list[str] = []
    negatives: list[str] = []
    flags: list[str] = []
    if score >= 70.0:
        positives.append(
            f"Reverse DCF expectation headroom {score:.0f}/100 — market assumptions look undemanding"
        )
        flags.append("undemanding_expectations")
    elif score <= 30.0:
        negatives.append(
            f"Reverse DCF expectation headroom {score:.0f}/100 — market assumptions look demanding"
        )
        flags.append("demanding_expectations")

    return {
        "score": score,
        "positives": positives,
        "negatives": negatives,
        "flags": flags,
    }
