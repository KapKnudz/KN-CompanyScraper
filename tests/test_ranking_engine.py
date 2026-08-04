"""
Tests for the deterministic watchlist ranking engine.

Run with: python -m pytest tests/test_ranking_engine.py -v
"""

import pytest

from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
from kncompanyscraper.analysis.ranking.company_score import CompanyScore, WatchlistRanking
from kncompanyscraper.models.company import Company


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def make_company(id_: int, ticker: str, name: str) -> Company:
    return Company(id=id_, name=name, ticker=ticker, mfn_slug=None, borsdata_id=None, last_updated=None)


def make_strong_financial() -> FinancialResult:
    """A company with excellent financials across the board."""
    return FinancialResult(
        operating_margin=0.22,
        net_margin=0.18,
        fcf_margin=0.16,
        revenue_growth=0.18,
        ebit_growth=0.20,
        net_income_growth=0.22,
        roe=0.28,
        roa=0.12,
        debt_to_equity=0.25,
    )


def make_weak_financial() -> FinancialResult:
    """A company with poor financials."""
    return FinancialResult(
        operating_margin=0.03,
        net_margin=0.01,
        fcf_margin=-0.02,
        revenue_growth=-0.03,
        ebit_growth=-0.08,
        net_income_growth=-0.15,
        roe=0.02,
        roa=0.005,
        debt_to_equity=2.5,
    )


def make_cheap_valuation() -> ValuationResult:
    """A company trading cheaply relative to history."""
    return ValuationResult(
        pe=10.0,
        ev_ebit=8.0,
        ev_ebitda=None,
        pb=None,
        ps=None,
        pfcf=None,
        peg=None,
        earnings_yield=0.10,
        free_cash_flow_yield=0.08,
        pe_vs_5y_avg=None,
        ev_ebit_vs_5y_avg=None,
        pb_vs_5y_avg=None,
        pe_percentile=10.0,
        ev_ebit_percentile=15.0,
    )


def make_expensive_valuation() -> ValuationResult:
    """A company trading expensively relative to history."""
    return ValuationResult(
        pe=50.0,
        ev_ebit=30.0,
        ev_ebitda=None,
        pb=None,
        ps=None,
        pfcf=None,
        peg=None,
        earnings_yield=0.02,
        free_cash_flow_yield=0.01,
        pe_vs_5y_avg=None,
        ev_ebit_vs_5y_avg=None,
        pb_vs_5y_avg=None,
        pe_percentile=95.0,
        ev_ebit_percentile=90.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCompanyScore:
    def test_defaults(self):
        cs = CompanyScore(company_id=1, ticker="TST", name="Test")
        assert cs.quality_score == 0.0
        assert cs.total_score == 0.0
        assert cs.positives == []
        assert cs.negatives == []
        assert cs.missing_data == []
        assert cs.flags == []


class TestWatchlistRanking:
    def test_top_n(self):
        scores = [
            CompanyScore(company_id=1, ticker="A", name="A", total_score=80),
            CompanyScore(company_id=2, ticker="B", name="B", total_score=60),
            CompanyScore(company_id=3, ticker="C", name="C", total_score=40),
        ]
        ranking = WatchlistRanking(scores=scores)
        assert ranking.top_n(2) == scores[:2]
        assert ranking.top_n(5) == scores


class TestScoringBounded:
    """Every score must be in [0, 100]."""

    def test_strong_company_scores_in_bounds(self):
        company = make_company(1, "STRONG", "Strong Co")
        results = {
            1: {
                "financial": make_strong_financial(),
                "valuation": make_cheap_valuation(),
            }
        }
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        for label, value in [
            ("quality_score", cs.quality_score),
            ("growth_score", cs.growth_score),
            ("valuation_score", cs.valuation_score),
            ("balance_sheet_score", cs.balance_sheet_score),
            ("total_score", cs.total_score),
        ]:
            assert 0 <= value <= 100, f"{label} = {value} out of [0, 100]"

    def test_weak_company_scores_in_bounds(self):
        company = make_company(1, "WEAK", "Weak Co")
        results = {
            1: {
                "financial": make_weak_financial(),
                "valuation": make_expensive_valuation(),
            }
        }
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        for label, value in [
            ("quality_score", cs.quality_score),
            ("growth_score", cs.growth_score),
            ("valuation_score", cs.valuation_score),
            ("balance_sheet_score", cs.balance_sheet_score),
            ("total_score", cs.total_score),
        ]:
            assert 0 <= value <= 100, f"{label} = {value} out of [0, 100]"


class TestScoringRelative:
    """Strong companies score higher than weak ones."""

    def test_strong_beats_weak(self):
        strong = make_company(1, "STRONG", "Strong Co")
        weak = make_company(2, "WEAK", "Weak Co")
        results = {
            1: {"financial": make_strong_financial(), "valuation": make_cheap_valuation()},
            2: {"financial": make_weak_financial(), "valuation": make_expensive_valuation()},
        }
        engine = RankingEngine()
        ranking = engine.rank([strong, weak], results)

        assert ranking.scores[0].ticker == "STRONG"
        assert ranking.scores[1].ticker == "WEAK"
        assert ranking.scores[0].total_score > ranking.scores[1].total_score

    def test_strong_quality_beats_weak(self):
        strong = make_company(1, "S", "S")
        weak = make_company(2, "W", "W")
        results = {
            1: {"financial": make_strong_financial(), "valuation": make_cheap_valuation()},
            2: {"financial": make_weak_financial(), "valuation": make_cheap_valuation()},
        }
        engine = RankingEngine()
        ranking = engine.rank([strong, weak], results)
        strong_cs = ranking.scores[0]
        weak_cs = ranking.scores[1]

        assert strong_cs.quality_score > weak_cs.quality_score
        assert strong_cs.growth_score > weak_cs.growth_score
        assert strong_cs.balance_sheet_score > weak_cs.balance_sheet_score

    def test_cheap_valuation_beats_expensive(self):
        company_a = make_company(1, "CHEAP", "Cheap")
        company_b = make_company(2, "DEAR", "Dear")
        same_financial = make_strong_financial()
        results = {
            1: {"financial": same_financial, "valuation": make_cheap_valuation()},
            2: {"financial": same_financial, "valuation": make_expensive_valuation()},
        }
        engine = RankingEngine()
        ranking = engine.rank([company_a, company_b], results)

        cheap_cs = next(cs for cs in ranking.scores if cs.ticker == "CHEAP")
        dear_cs = next(cs for cs in ranking.scores if cs.ticker == "DEAR")
        assert cheap_cs.valuation_score > dear_cs.valuation_score


class TestMissingSkillResult:
    """None skill results should not crash, should score 0 in that category."""

    def test_missing_financial_scores_zero(self):
        company = make_company(1, "TST", "Test")
        results = {1: {"valuation": make_cheap_valuation()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert cs.quality_score == 0.0
        assert cs.growth_score == 0.0
        assert cs.balance_sheet_score == 0.0
        assert cs.valuation_score > 0
        assert "financial data not available" in cs.missing_data

    def test_missing_valuation_scores_zero(self):
        company = make_company(1, "TST", "Test")
        results = {1: {"financial": make_strong_financial()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert cs.valuation_score == 0.0
        assert cs.quality_score > 0
        assert "valuation data not available" in cs.missing_data

    def test_all_missing_scores_zero(self):
        company = make_company(1, "TST", "Test")
        results = {1: {}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert cs.total_score == 0.0
        assert cs.quality_score == 0.0
        assert cs.growth_score == 0.0
        assert cs.valuation_score == 0.0
        assert cs.balance_sheet_score == 0.0
        assert len(cs.missing_data) >= 2


class TestRankingSorting:
    def test_sorted_by_total_descending(self):
        companies = [
            make_company(1, "MID", "Middle Co"),
            make_company(2, "TOP", "Top Co"),
            make_company(3, "LOW", "Low Co"),
        ]
        results = {
            1: {"financial": make_weak_financial(), "valuation": make_cheap_valuation()},
            2: {"financial": make_strong_financial(), "valuation": make_cheap_valuation()},
            3: {"financial": make_weak_financial(), "valuation": make_expensive_valuation()},
        }
        engine = RankingEngine()
        ranking = engine.rank(companies, results)

        tickers = [cs.ticker for cs in ranking.scores]
        assert tickers == ["TOP", "MID", "LOW"]
        for i in range(len(ranking.scores) - 1):
            assert ranking.scores[i].total_score >= ranking.scores[i + 1].total_score

    def test_empty_companies(self):
        engine = RankingEngine()
        ranking = engine.rank([], {})
        assert ranking.scores == []
        assert ranking.top_n(5) == []


class TestPositivesAndNegatives:
    def test_strong_company_has_positives(self):
        company = make_company(1, "S", "S")
        results = {1: {"financial": make_strong_financial(), "valuation": make_cheap_valuation()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert len(cs.positives) > 0
        assert any("ROE" in p for p in cs.positives)
        assert any("ROA" in p for p in cs.positives)
        assert any("D/E" in p for p in cs.positives)

    def test_weak_company_has_negatives(self):
        company = make_company(1, "W", "W")
        results = {1: {"financial": make_weak_financial(), "valuation": make_expensive_valuation()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert len(cs.negatives) > 0
        assert any("leverage" in n for n in cs.negatives)


class TestWeightedTotal:
    def test_total_matches_weighted_formula(self):
        company = make_company(1, "TST", "Test")
        results = {1: {"financial": make_strong_financial(), "valuation": make_cheap_valuation()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        expected = (
            cs.quality_score * 0.30
            + cs.growth_score * 0.25
            + cs.valuation_score * 0.30
            + cs.balance_sheet_score * 0.15
        )
        assert cs.total_score == pytest.approx(round(expected, 1))


class TestEdgeCases:
    def test_negative_equity_scores_zero(self):
        """D/E negative (negative equity) should score 0 on balance sheet."""
        financial = make_strong_financial()
        financial.debt_to_equity = -0.5

        company = make_company(1, "TST", "Test")
        results = {1: {"financial": financial, "valuation": make_cheap_valuation()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert cs.balance_sheet_score == 0.0
        assert any("negative equity" in n for n in cs.negatives)

    def test_all_metrics_none_scores_zero(self):
        """When every metric in a category is None, that category scores 0."""
        financial = FinancialResult(
            operating_margin=None,
            net_margin=None,
            fcf_margin=None,
            revenue_growth=None,
            ebit_growth=None,
            net_income_growth=None,
            roe=None,
            roa=None,
            debt_to_equity=None,
        )
        company = make_company(1, "TST", "Test")
        results = {1: {"financial": financial, "valuation": make_cheap_valuation()}}
        engine = RankingEngine()
        ranking = engine.rank([company], results)
        cs = ranking.scores[0]

        assert cs.quality_score == 0.0
        assert cs.growth_score == 0.0
        assert cs.balance_sheet_score == 0.0
        assert len(cs.missing_data) > 0


# ---------------------------------------------------------------------------
# Demo: print the ranking table (matches "Definition of done" output format)
# ---------------------------------------------------------------------------

class TestDemoOutput:
    """Demonstrate the ranking output format with hand-built companies."""

    def test_print_ranking_table(self, capsys):
        companies = [
            make_company(1, "AQ", "AQ Group"),
            make_company(2, "EXMPL", "Example Co"),
            make_company(3, "WEAK", "Weak Co"),
        ]
        results = {
            1: {"financial": make_strong_financial(), "valuation": make_cheap_valuation()},
            2: {
                "financial": FinancialResult(
                    operating_margin=0.10,
                    net_margin=0.08,
                    fcf_margin=0.06,
                    revenue_growth=0.08,
                    ebit_growth=0.06,
                    net_income_growth=0.07,
                    roe=0.12,
                    roa=0.06,
                    debt_to_equity=0.90,
                ),
                "valuation": make_expensive_valuation(),
            },
            3: {"financial": make_weak_financial(), "valuation": make_expensive_valuation()},
        }

        engine = RankingEngine()
        ranking = engine.rank(companies, results)

        for i, cs in enumerate(ranking.scores, 1):
            print(
                f"{i}. {cs.name:<14} "
                f"total={cs.total_score}  "
                f"quality={cs.quality_score} "
                f"growth={cs.growth_score} "
                f"valuation={cs.valuation_score} "
                f"balance_sheet={cs.balance_sheet_score}"
            )

        captured = capsys.readouterr().out
        assert "AQ Group" in captured
        assert "Example Co" in captured
        assert "Weak Co" in captured
        # AQ Group should be first (strongest)
        assert captured.index("AQ Group") < captured.index("Example Co")
        assert captured.index("Example Co") < captured.index("Weak Co")
