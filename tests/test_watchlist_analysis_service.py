"""
Integration tests for WatchlistAnalysisService.

Run with: uv run pytest tests/test_watchlist_analysis_service.py -v
"""

import pytest

from kncompanyscraper.analysis.watchlist.watchlist_analysis_service import WatchlistAnalysisService
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
from kncompanyscraper.analysis.ranking.company_score import CompanyScore, WatchlistRanking
from kncompanyscraper.models.company import Company


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_company(id_: int, ticker: str, name: str) -> Company:
    return Company(
        id=id_, name=name, ticker=ticker, mfn_slug=None, borsdata_id=None, last_updated=None,
    )


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

class MockFinancialResult:
    """Minimal stub that score_rules can consume without a real FinancialResult."""
    def __init__(self, roe=0.15, roa=0.08, net_margin=0.10, fcf_margin=0.08,
                 revenue_growth=0.10, ebit_growth=0.10, net_income_growth=0.10,
                 debt_to_equity=0.5):
        self.roe = roe
        self.roa = roa
        self.net_margin = net_margin
        self.fcf_margin = fcf_margin
        self.revenue_growth = revenue_growth
        self.ebit_growth = ebit_growth
        self.net_income_growth = net_income_growth
        self.debt_to_equity = debt_to_equity


class MockValuationResult:
    """Minimal stub that score_rules can consume without a real ValuationResult."""
    def __init__(self, earnings_yield=0.06, free_cash_flow_yield=0.05,
                 pe_percentile=50.0, ev_ebit_percentile=50.0):
        self.earnings_yield = earnings_yield
        self.free_cash_flow_yield = free_cash_flow_yield
        self.pe_percentile = pe_percentile
        self.ev_ebit_percentile = ev_ebit_percentile


class StubCompanyRepository:
    """Returns a fixed list of companies, simulating active watchlist query."""

    def __init__(self, companies: list[Company] | None = None):
        self.companies = companies or []

    def get_active_companies(self) -> list[Company]:
        return list(self.companies)


class StubAnalysisEngine:
    """Runs stub skills that return pre-configured results per company."""

    def __init__(self, results_by_company: dict[int, dict] | None = None):
        self.results_by_company = results_by_company or {}

    def analyze(self, company) -> dict:
        return self.results_by_company.get(company.id, {})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWatchlistAnalysisService:
    """Integration tests: mocked repos + skills → real RankingEngine."""

    def test_rank_watchlist_analyzes_active_companies(self):
        companies = [make_company(1, "AQ", "AQ Group"), make_company(2, "EX", "Example")]
        repo = StubCompanyRepository(companies)

        results = {
            1: {
                "financial": MockFinancialResult(roe=0.28, roa=0.12, net_margin=0.18, fcf_margin=0.16,
                                                 revenue_growth=0.18, ebit_growth=0.20,
                                                 net_income_growth=0.22, debt_to_equity=0.25),
                "valuation": MockValuationResult(earnings_yield=0.10, free_cash_flow_yield=0.08,
                                                 pe_percentile=10.0, ev_ebit_percentile=15.0),
            },
            2: {
                "financial": MockFinancialResult(roe=0.05, roa=0.02, net_margin=0.03, fcf_margin=0.01,
                                                 revenue_growth=0.02, ebit_growth=0.01,
                                                 net_income_growth=0.0, debt_to_equity=1.5),
                "valuation": MockValuationResult(earnings_yield=0.02, free_cash_flow_yield=0.01,
                                                 pe_percentile=90.0, ev_ebit_percentile=85.0),
            },
        }
        engine = StubAnalysisEngine(results)
        ranking_engine = RankingEngine()

        service = WatchlistAnalysisService(repo, engine, ranking_engine)
        ranking = service.rank_watchlist()

        assert isinstance(ranking, WatchlistRanking)
        assert len(ranking.scores) == 2
        # Sorted by total_score descending — AQ should be first
        assert ranking.scores[0].company_id == 1
        assert ranking.scores[0].ticker == "AQ"
        assert ranking.scores[1].company_id == 2

    def test_rank_watchlist_results_keyed_by_company_id(self):
        """Each company in the ranking matches a company that was analyzed."""
        companies = [make_company(10, "T1", "Test1"), make_company(20, "T2", "Test2")]
        repo = StubCompanyRepository(companies)

        results = {
            10: {"financial": MockFinancialResult(), "valuation": MockValuationResult()},
            20: {"financial": MockFinancialResult(), "valuation": MockValuationResult()},
        }
        engine = StubAnalysisEngine(results)

        service = WatchlistAnalysisService(repo, engine, RankingEngine())
        ranking = service.rank_watchlist()

        company_ids = {cs.company_id for cs in ranking.scores}
        assert company_ids == {10, 20}

    def test_rank_watchlist_handles_missing_skill_results(self):
        """Companies with no skill results still appear in the ranking (score 0)."""
        companies = [make_company(1, "EMPTY", "Empty Co")]
        repo = StubCompanyRepository(companies)
        engine = StubAnalysisEngine({})  # no results at all

        service = WatchlistAnalysisService(repo, engine, RankingEngine())
        ranking = service.rank_watchlist()

        assert len(ranking.scores) == 1
        cs = ranking.scores[0]
        assert cs.company_id == 1
        assert cs.total_score == 0.0
        assert cs.data_quality == "low"

    def test_rank_watchlist_empty_watchlist(self):
        repo = StubCompanyRepository([])
        engine = StubAnalysisEngine({})

        service = WatchlistAnalysisService(repo, engine, RankingEngine())
        ranking = service.rank_watchlist()

        assert isinstance(ranking, WatchlistRanking)
        assert ranking.scores == []

    def test_shortlist_for_agent_returns_top_n(self):
        """shortlist_for_agent returns at most max_total, starting from top_n."""
        companies = [make_company(i, f"T{i}", f"Test {i}") for i in range(1, 51)]
        repo = StubCompanyRepository(companies)

        results = {}
        for c in companies:
            # Vary scores so there's a clear ordering
            results[c.id] = {
                "financial": MockFinancialResult(
                    roe=0.05 + c.id * 0.004,  # higher ID = higher ROE
                ),
                "valuation": MockValuationResult(),
            }

        engine = StubAnalysisEngine(results)
        service = WatchlistAnalysisService(repo, engine, RankingEngine())

        shortlist = service.shortlist_for_agent(top_n=10, max_total=30)
        assert len(shortlist) == 10  # no flags to pull extras in
        assert all(isinstance(cs, CompanyScore) for cs in shortlist)
        # First is highest total_score
        for i in range(len(shortlist) - 1):
            assert shortlist[i].total_score >= shortlist[i + 1].total_score

    def test_shortlist_for_agent_includes_flagged_companies(self):
        """Companies beyond top_n with important flags are included."""
        companies = [make_company(i, f"T{i}", f"Test {i}") for i in range(1, 51)]
        repo = StubCompanyRepository(companies)

        results = {}
        for c in companies:
            results[c.id] = {
                "financial": MockFinancialResult(),
                "valuation": MockValuationResult(),
            }

        # Make company 35 (position 35 in the ranking) have cheap_quality flag.
        # Since same scores → sorted by total_score, all equal.
        # We'll give company at id=35 strong financial + cheap valuation to get the flag.
        results[35] = {
            "financial": MockFinancialResult(roe=0.28, roa=0.12, net_margin=0.18, fcf_margin=0.16),
            "valuation": MockValuationResult(earnings_yield=0.10, free_cash_flow_yield=0.08,
                                             pe_percentile=10.0, ev_ebit_percentile=15.0),
        }

        engine = StubAnalysisEngine(results)
        service = WatchlistAnalysisService(repo, engine, RankingEngine())

        shortlist = service.shortlist_for_agent(top_n=10, max_total=30)
        # Company 35 should be in the shortlist (it got cheap_quality + fcf_quality)
        shortlist_ids = {cs.company_id for cs in shortlist}
        assert 35 in shortlist_ids
        assert len(shortlist) <= 30

    def test_shortlist_for_agent_respects_max_total(self):
        """shortlist_for_agent never exceeds max_total even with many flagged companies."""
        companies = [make_company(i, f"T{i}", f"Test {i}") for i in range(1, 101)]
        repo = StubCompanyRepository(companies)

        results = {}
        for c in companies:
            results[c.id] = {
                "financial": MockFinancialResult(
                    roe=0.28, roa=0.12, net_margin=0.18, fcf_margin=0.16,
                ),
                "valuation": MockValuationResult(
                    earnings_yield=0.10, free_cash_flow_yield=0.08,
                    pe_percentile=10.0, ev_ebit_percentile=15.0,
                ),
            }

        engine = StubAnalysisEngine(results)
        service = WatchlistAnalysisService(repo, engine, RankingEngine())

        shortlist = service.shortlist_for_agent(top_n=5, max_total=15)
        assert len(shortlist) <= 15

    def test_shortlist_for_agent_cheap_but_weak_growth_flag_included(self):
        """cheap_but_weak_growth is now an important flag that pulls companies in."""
        companies = [make_company(i, f"T{i}", f"Test {i}") for i in range(1, 51)]
        repo = StubCompanyRepository(companies)

        results = {}
        for c in companies:
            results[c.id] = {
                "financial": MockFinancialResult(),
                "valuation": MockValuationResult(),
            }

        # Company 40 gets cheap_but_weak_growth: weak growth + strong valuation
        results[40] = {
            "financial": MockFinancialResult(
                revenue_growth=-0.03, ebit_growth=-0.05, net_income_growth=-0.10,
            ),
            "valuation": MockValuationResult(
                earnings_yield=0.10, free_cash_flow_yield=0.08,
                pe_percentile=10.0, ev_ebit_percentile=15.0,
            ),
        }

        engine = StubAnalysisEngine(results)
        service = WatchlistAnalysisService(repo, engine, RankingEngine())

        shortlist = service.shortlist_for_agent(top_n=10, max_total=30)
        shortlist_ids = {cs.company_id for cs in shortlist}
        assert 40 in shortlist_ids, "cheap_but_weak_growth should pull company into shortlist"

    def test_shortlist_for_agent_fcf_quality_flag_included(self):
        """fcf_quality is now an important flag that pulls companies in."""
        companies = [make_company(i, f"T{i}", f"Test {i}") for i in range(1, 51)]
        repo = StubCompanyRepository(companies)

        results = {}
        for c in companies:
            results[c.id] = {
                "financial": MockFinancialResult(),
                "valuation": MockValuationResult(),
            }

        # Company 40 gets fcf_quality: high FCF margin + strong valuation
        # Strong FCF margin (>= 0.15) + valuation score >= 70 = fcf_quality + cheap_quality
        results[40] = {
            "financial": MockFinancialResult(
                roe=0.28, roa=0.12, net_margin=0.18, fcf_margin=0.20,  # strong FCF
            ),
            "valuation": MockValuationResult(
                earnings_yield=0.10, free_cash_flow_yield=0.08,
                pe_percentile=10.0, ev_ebit_percentile=15.0,
            ),
        }

        engine = StubAnalysisEngine(results)
        service = WatchlistAnalysisService(repo, engine, RankingEngine())

        shortlist = service.shortlist_for_agent(top_n=10, max_total=30)
        shortlist_ids = {cs.company_id for cs in shortlist}
        assert 40 in shortlist_ids, "fcf_quality should pull company into shortlist"

    def test_full_pipeline_produces_expected_structure(self):
        """End-to-end: the ranking has all fields populated."""
        companies = [make_company(1, "AQ", "AQ Group")]
        repo = StubCompanyRepository(companies)

        results = {
            1: {
                "financial": MockFinancialResult(roe=0.28, roa=0.12, net_margin=0.18, fcf_margin=0.16,
                                                 revenue_growth=0.18, ebit_growth=0.20,
                                                 net_income_growth=0.22, debt_to_equity=0.25),
                "valuation": MockValuationResult(earnings_yield=0.10, free_cash_flow_yield=0.08,
                                                 pe_percentile=10.0, ev_ebit_percentile=15.0),
            },
        }
        engine = StubAnalysisEngine(results)

        service = WatchlistAnalysisService(repo, engine, RankingEngine())
        ranking = service.rank_watchlist()

        cs = ranking.scores[0]
        assert cs.company_id == 1
        assert cs.ticker == "AQ"
        assert cs.name == "AQ Group"
        assert cs.total_score > 0
        assert cs.quality_score > 0
        assert cs.growth_score > 0
        assert cs.valuation_score > 0
        assert cs.balance_sheet_score > 0
        assert cs.data_quality in ("high", "medium", "low")
        assert isinstance(cs.flags, list)
        assert isinstance(cs.candidate_reason, str)
        assert len(cs.positives) > 0
