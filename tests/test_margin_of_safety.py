"""Tests for margin-of-safety computation and weighted valuation scoring."""

import pytest

from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.analysis.ranking.score_rules import (
    compute_margin_of_safety,
    score_valuation,
)


# ---------------------------------------------------------------------------
# Margin of safety
# ---------------------------------------------------------------------------

class TestMarginOfSafety:
    def test_basic_computation(self):
        """8% FCF yield vs 8% required → margin = 0%."""
        mos = compute_margin_of_safety(fcf_yield=0.08)
        assert mos == pytest.approx(0.0)

    def test_cheap_company(self):
        """12% FCF yield vs 8% required → margin = +4%."""
        mos = compute_margin_of_safety(fcf_yield=0.12)
        assert mos == pytest.approx(0.04)

    def test_expensive_company(self):
        """3% FCF yield vs 8% required → margin = -5%."""
        mos = compute_margin_of_safety(fcf_yield=0.03)
        assert mos == pytest.approx(-0.05)

    def test_quality_reduces_required_return(self):
        """High quality should lower the required yield."""
        mos_default = compute_margin_of_safety(fcf_yield=0.08)
        mos_quality = compute_margin_of_safety(fcf_yield=0.08, quality_score=100.0)
        assert mos_quality > mos_default  # lower required = higher margin

    def test_growth_reduces_required_return(self):
        """High growth should lower the required yield."""
        mos_default = compute_margin_of_safety(fcf_yield=0.08)
        mos_growth = compute_margin_of_safety(fcf_yield=0.08, growth_score=100.0)
        assert mos_growth > mos_default

    def test_leverage_increases_required_return(self):
        """High debt/equity should increase the required yield."""
        mos_no_debt = compute_margin_of_safety(fcf_yield=0.08, debt_to_equity=0.0)
        mos_high_debt = compute_margin_of_safety(fcf_yield=0.08, debt_to_equity=2.0)
        assert mos_high_debt < mos_no_debt  # higher required = lower margin

    def test_leverage_penalty_capped(self):
        """Leverage penalty should not exceed 5%."""
        mos_dte_2 = compute_margin_of_safety(fcf_yield=0.08, debt_to_equity=2.0)
        mos_dte_4 = compute_margin_of_safety(fcf_yield=0.08, debt_to_equity=4.0)
        assert mos_dte_2 == pytest.approx(mos_dte_4)

    def test_none_fcf_yield_returns_none(self):
        assert compute_margin_of_safety(None) is None

    def test_negative_debt_to_equity_no_penalty(self):
        """Negative D/E (insolvent) should not trigger leverage penalty."""
        mos = compute_margin_of_safety(fcf_yield=0.08, debt_to_equity=-0.5)
        assert mos == pytest.approx(0.0)

    def test_custom_rates(self):
        """Risk-free rate and ERP should be configurable."""
        mos = compute_margin_of_safety(
            fcf_yield=0.06,
            risk_free_rate=0.01,
            equity_risk_premium=0.03,
        )
        # required = 0.01 + 0.03 = 0.04, margin = 0.06 - 0.04 = 0.02
        assert mos == pytest.approx(0.02)

    def test_neutral_quality_no_bonus(self):
        """Quality = 50 (neutral) should give no bonus."""
        mos_neutral = compute_margin_of_safety(fcf_yield=0.08, quality_score=50.0)
        mos_default = compute_margin_of_safety(fcf_yield=0.08)
        assert mos_neutral == pytest.approx(mos_default)

    def test_poor_quality_no_penalty(self):
        """Quality below 50 should not increase required return (no penalty)."""
        mos_poor = compute_margin_of_safety(fcf_yield=0.08, quality_score=25.0)
        mos_default = compute_margin_of_safety(fcf_yield=0.08)
        assert mos_poor == pytest.approx(mos_default)


# ---------------------------------------------------------------------------
# Weighted valuation scoring
# ---------------------------------------------------------------------------

def _cheap_valuation(**overrides) -> ValuationResult:
    defaults = {
        "pe": 10.0,
        "ev_ebit": 8.0,
        "ev_ebitda": None,
        "pb": None,
        "ps": None,
        "pfcf": 12.5,
        "peg": None,
        "earnings_yield": 0.10,
        "free_cash_flow_yield": 0.08,
        "pe_vs_5y_avg": None,
        "ev_ebit_vs_5y_avg": None,
        "pb_vs_5y_avg": None,
        "pe_percentile": 10.0,
        "ev_ebit_percentile": 15.0,
        "raw_market_cap": None,
        "raw_enterprise_value": None,
        "raw_earnings_yield": None,
        "raw_fcf_yield": None,
        "raw_pe": None,
        "raw_pfcf": None,
        "raw_ev_ebit": None,
        "raw_ev_ebitda": None,
    }
    defaults.update(overrides)
    return ValuationResult(**defaults)


class TestWeightedValuationScoring:
    def test_cheap_valuation_scores_high(self):
        result = score_valuation(_cheap_valuation())
        assert result["score"] > 70
        assert len(result["positives"]) > 0

    def test_expensive_valuation_scores_low(self):
        expensive = ValuationResult(
            pe=50.0,
            ev_ebit=30.0,
            ev_ebitda=None,
            pb=None,
            ps=None,
            pfcf=100.0,
            peg=None,
            earnings_yield=0.02,
            free_cash_flow_yield=0.01,
            pe_vs_5y_avg=None,
            ev_ebit_vs_5y_avg=None,
            pb_vs_5y_avg=None,
            pe_percentile=95.0,
            ev_ebit_percentile=90.0,
        )
        result = score_valuation(expensive)
        assert result["score"] < 30
        assert len(result["negatives"]) > 0

    def test_margin_of_safety_contributes(self):
        """When quality/growth context is provided, MoS affects the score."""
        # High quality + growth → lower required return → higher MoS → higher score
        result_high = score_valuation(
            _cheap_valuation(),
            quality_score=100.0,
            growth_score=100.0,
        )
        result_neutral = score_valuation(
            _cheap_valuation(),
            quality_score=50.0,
            growth_score=50.0,
        )
        assert result_high["score"] > result_neutral["score"]

    def test_leverage_penalty_reduces_score(self):
        result_low_dte = score_valuation(
            _cheap_valuation(),
            debt_to_equity=0.1,
        )
        result_high_dte = score_valuation(
            _cheap_valuation(),
            debt_to_equity=2.0,
        )
        assert result_high_dte["score"] < result_low_dte["score"]

    def test_prefers_raw_yields(self):
        """Raw yields should be used when available."""
        kpi_only = _cheap_valuation(earnings_yield=0.05, free_cash_flow_yield=0.04)
        with_raw = _cheap_valuation(
            earnings_yield=0.05,
            free_cash_flow_yield=0.04,
            raw_earnings_yield=0.10,
            raw_fcf_yield=0.08,
        )
        result_kpi = score_valuation(kpi_only)
        result_raw = score_valuation(with_raw)
        # Raw yields are higher → score should be higher
        assert result_raw["score"] > result_kpi["score"]

    def test_all_metrics_none_scores_zero(self):
        empty = ValuationResult(
            pe=None, ev_ebit=None, ev_ebitda=None,
            pb=None, ps=None, pfcf=None, peg=None,
            earnings_yield=None, free_cash_flow_yield=None,
            pe_vs_5y_avg=None, ev_ebit_vs_5y_avg=None, pb_vs_5y_avg=None,
            pe_percentile=None, ev_ebit_percentile=None,
        )
        result = score_valuation(empty)
        assert result["score"] == 0.0

    def test_none_valuation_scores_zero(self):
        result = score_valuation(None)
        assert result["score"] == 0.0
        assert "valuation data not available" in result["missing"]

    def test_score_in_bounds(self):
        """Score should always be in [0, 100]."""
        result = score_valuation(_cheap_valuation())
        assert 0 <= result["score"] <= 100
