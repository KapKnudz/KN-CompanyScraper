import math
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.ranking.reverse_dcf_score import score_reverse_dcf
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
from kncompanyscraper.analysis.ranking.score_rules import score_valuation
from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.valuation.reverse_dcf import DcfAssumptions
from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.models.company import Company


def _analysis(*, revenue_growth, ebit_margin, terminal_growth, confidence="high"):
    assumptions = DcfAssumptions(
        projection_years=5,
        revenue_growth=0.10,
        ebit_margin=0.20,
        tax_rate=0.21,
        discount_rate=0.10,
        terminal_growth=0.02,
    )
    implied = {
        "revenue_growth": revenue_growth,
        "ebit_margin": ebit_margin,
        "terminal_growth": terminal_growth,
    }
    return SimpleNamespace(
        status="available",
        assumptions=assumptions,
        current_price=100.0,
        normalization=SimpleNamespace(confidence=confidence),
        implied_expectations={
            name: SimpleNamespace(
                status="solved",
                implied_value=value,
                lower_bound={
                    "revenue_growth": -0.10,
                    "ebit_margin": 0.0,
                    "terminal_growth": -0.01,
                }[name],
                upper_bound={
                    "revenue_growth": 0.30,
                    "ebit_margin": 0.50,
                    "terminal_growth": 0.04,
                }[name],
                modeled_price_range=None,
            )
            for name, value in implied.items()
        },
    )


def _valuation():
    return ValuationResult(
        pe=15.0,
        ev_ebit=12.0,
        ev_ebitda=None,
        pb=None,
        ps=None,
        pfcf=None,
        peg=None,
        earnings_yield=0.05,
        free_cash_flow_yield=0.05,
        pe_vs_5y_avg=None,
        ev_ebit_vs_5y_avg=None,
        pb_vs_5y_avg=None,
        pe_percentile=50.0,
        ev_ebit_percentile=50.0,
    )


def test_baseline_matching_expectations_are_neutral():
    result = score_reverse_dcf(
        _analysis(revenue_growth=0.10, ebit_margin=0.20, terminal_growth=0.02)
    )

    assert result["score"] == pytest.approx(50.0)
    assert result["flags"] == ["diagnostic_only_expectations"]


def test_undemanding_expectations_score_high_on_materiality_scaled_median():
    result = score_reverse_dcf(
        _analysis(revenue_growth=0.05, ebit_margin=0.15, terminal_growth=0.01)
    )

    assert result["score"] == pytest.approx(75.0)
    assert result["flags"] == [
        "undemanding_expectations",
        "diagnostic_only_expectations",
    ]


def test_terminal_growth_is_diagnostic_only_and_does_not_change_score():
    result = score_reverse_dcf(
        _analysis(revenue_growth=0.10, ebit_margin=0.20, terminal_growth=-0.50)
    )

    assert result["score"] == pytest.approx(50.0)


def test_low_normalization_confidence_is_preserved_in_diagnostic_output():
    result = score_reverse_dcf(
        _analysis(
            revenue_growth=0.05,
            ebit_margin=0.15,
            terminal_growth=0.01,
            confidence="low",
        )
    )

    assert result["score"] == pytest.approx(75.0)
    assert result["ranking_weight"] == 0.0
    assert "low_confidence_expectations" in result["flags"]


def test_price_below_entire_bounded_range_is_scored_as_censored_headroom():
    analysis = _analysis(
        revenue_growth=0.10,
        ebit_margin=0.20,
        terminal_growth=0.02,
    )
    analysis.implied_expectations = {
        "revenue_growth": SimpleNamespace(
            status="outside_bounds",
            implied_value=None,
            lower_bound=-0.10,
            upper_bound=0.30,
            modeled_price_range=(120.0, 200.0),
        )
    }

    result = score_reverse_dcf(analysis)

    boundary_gap = (0.10 - (-0.10)) / 0.10
    price_distance = math.log2(120.0 / 100.0)
    expected = 100.0 / (1.0 + 9.0 ** -(boundary_gap + price_distance))
    assert result["score"] == pytest.approx(expected)
    assert result["score"] < 100.0
    assert result["flags"] == [
        "undemanding_expectations",
        "diagnostic_only_expectations",
    ]


def test_smooth_mapping_differentiates_scores_that_previously_saturated():
    one_gap = score_reverse_dcf(
        _analysis(revenue_growth=0.00, ebit_margin=0.10, terminal_growth=0.00)
    )
    two_gaps = score_reverse_dcf(
        _analysis(revenue_growth=-0.10, ebit_margin=0.00, terminal_growth=-0.02)
    )

    assert one_gap["score"] == pytest.approx(90.0)
    assert two_gaps["score"] == pytest.approx(100.0 / (1.0 + 9.0**-2.0))
    assert one_gap["score"] < two_gaps["score"] < 100.0


def test_farther_outside_bound_price_has_more_headroom():
    nearer = _analysis(revenue_growth=0.10, ebit_margin=0.20, terminal_growth=0.02)
    farther = _analysis(revenue_growth=0.10, ebit_margin=0.20, terminal_growth=0.02)
    nearer.implied_expectations = {
        "revenue_growth": SimpleNamespace(
            status="outside_bounds",
            implied_value=None,
            lower_bound=-0.10,
            upper_bound=0.30,
            modeled_price_range=(120.0, 200.0),
        )
    }
    farther.implied_expectations = {
        "revenue_growth": SimpleNamespace(
            status="outside_bounds",
            implied_value=None,
            lower_bound=-0.10,
            upper_bound=0.30,
            modeled_price_range=(200.0, 300.0),
        )
    }

    nearer_score = score_reverse_dcf(nearer)["score"]
    farther_score = score_reverse_dcf(farther)["score"]

    assert nearer_score < farther_score < 100.0


def test_outside_bound_with_negative_modeled_equity_value_is_scored():
    analysis = _analysis(revenue_growth=0.10, ebit_margin=0.20, terminal_growth=0.02)
    analysis.implied_expectations = {
        "ebit_margin": SimpleNamespace(
            status="outside_bounds",
            implied_value=None,
            lower_bound=0.0,
            upper_bound=0.50,
            modeled_price_range=(-200.0, -50.0),
        )
    }

    result = score_reverse_dcf(analysis)

    assert 0.0 < result["score"] < 50.0
    assert result["flags"] == [
        "demanding_expectations",
        "diagnostic_only_expectations",
    ]


def test_unavailable_reverse_dcf_preserves_legacy_valuation_score():
    legacy = score_valuation(_valuation())
    unavailable = score_valuation(
        _valuation(),
        reverse_dcf={"score": None, "positives": [], "negatives": [], "flags": []},
    )

    assert unavailable["score"] == pytest.approx(legacy["score"])


def test_available_reverse_dcf_is_exposed_but_does_not_change_valuation_score():
    legacy = score_valuation(_valuation())
    low = score_valuation(
        _valuation(),
        reverse_dcf={"score": 0.0, "positives": [], "negatives": [], "flags": []},
    )
    high = score_valuation(
        _valuation(),
        reverse_dcf={"score": 100.0, "positives": [], "negatives": [], "flags": []},
    )

    assert low["score"] == pytest.approx(legacy["score"])
    assert high["score"] == pytest.approx(legacy["score"])
    assert high["reverse_dcf_score"] == 100.0


def test_reverse_dcf_confidence_does_not_change_diagnostic_only_weight():
    legacy = score_valuation(_valuation())["score"]
    full = score_valuation(
        _valuation(),
        reverse_dcf={
            "score": 0.0,
            "confidence_weight": 1.0,
            "positives": [],
            "negatives": [],
            "flags": [],
        },
    )["score"]
    reduced = score_valuation(
        _valuation(),
        reverse_dcf={
            "score": 0.0,
            "confidence_weight": 0.25,
            "positives": [],
            "negatives": [],
            "flags": [],
        },
    )["score"]

    assert full == pytest.approx(legacy)
    assert reduced == pytest.approx(legacy)


def test_ranking_exposes_diagnostic_expectation_headroom():
    company = Company(1, "Test", "TST", None, None, None)
    financial = FinancialResult(
        operating_margin=0.20,
        net_margin=0.10,
        fcf_margin=0.10,
        revenue_growth=0.10,
        ebit_growth=0.10,
        net_income_growth=0.10,
        roe=0.15,
        roa=0.08,
        debt_to_equity=0.50,
    )
    reverse_dcf = _analysis(
        revenue_growth=0.05,
        ebit_margin=0.15,
        terminal_growth=0.01,
    )

    score = RankingEngine().rank(
        [company],
        {
            company.id: {
                "financial": financial,
                "valuation": _valuation(),
                "reverse_dcf": reverse_dcf,
            }
        },
    ).scores[0]

    assert score.reverse_dcf_score == 75.0
    assert "undemanding_expectations" in score.flags
    assert "diagnostic_only_expectations" in score.flags
    assert any("expectation headroom" in item for item in score.positives)
