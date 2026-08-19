from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from kncompanyscraper.analysis.backtesting.backtest_engine import BacktestEngine
from kncompanyscraper.analysis.backtesting.backtest_result import (
    CategoryCorrelation,
    CompanyAttribution,
    DecilePerformance,
    MetricAttribution,
    PeriodResult,
)
from kncompanyscraper.analysis.realized_total_return import RealizedReturnObservation
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.models.company import Company
from kncompanyscraper.main import _cmd_backtest
from kncompanyscraper.repositories.dividend_repository import (
    DividendCoverage,
    DividendRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(year: int, **overrides) -> Report:
    defaults = {
        "revenue": 1000.0,
        "operating_profit": 200.0,
        "ebit": 180.0,
        "ebitda": 250.0,
        "net_income": 120.0,
        "free_cash_flow": 100.0,
        "equity": 800.0,
        "total_assets": 2000.0,
        "total_debt": 400.0,
        "shares_outstanding": 100.0,
        "gross_income": 400.0,
        "operating_cash_flow": 150.0,
        "year": year,
        "period": 4,
        "period_end": date(year, 12, 31),
        "currency": "SEK",
        "raw_payload": None,
    }
    defaults.update(overrides)
    return Report(**defaults)


def _make_company(id_: int = 1, ticker: str = "TST") -> Company:
    return Company(id_, "Test Co", ticker, None, None, None)


def _make_price(d: date, close: float = 50.0) -> StockPrice:
    return StockPrice(date=d, close=close, currency="SEK")


def _dividend_repository():
    repository = MagicMock()
    repository.get_coverage.return_value = DividendCoverage(
        date(2020, 1, 1), date.today() + timedelta(days=730), "borsdata"
    )
    repository.get_dividends.return_value = []
    repository.get_reviews.return_value = {}
    repository.review_key.side_effect = DividendRepository.review_key
    return repository


# ---------------------------------------------------------------------------
# Decile / result dataclass tests
# ---------------------------------------------------------------------------

class TestDecilePerformance:
    def test_defaults(self):
        dp = DecilePerformance(decile=1)
        assert dp.decile == 1
        assert dp.avg_6m_return is None
        assert dp.count == 0


class TestPeriodResult:
    def test_defaults(self):
        pr = PeriodResult(observation_date="2025-01-01")
        assert pr.observation_date == "2025-01-01"
        assert pr.deciles == []
        assert pr.company_count == 0


# ---------------------------------------------------------------------------
# BacktestEngine unit tests (mocked DB)
# ---------------------------------------------------------------------------

class TestBacktestEngine:
    def test_run_no_companies_returns_empty(self):
        company_repo = MagicMock()
        company_repo.get_backtest_companies.return_value = []

        engine = BacktestEngine(company_repo, MagicMock(), MagicMock())
        results = engine.run(num_periods=4)
        assert results == []

    def test_find_period_dates_uses_one_market_date_per_month(self):
        company_repo = MagicMock()
        valuation_repo = MagicMock()
        today = date.today()
        dates = [today - timedelta(days=i * 30) for i in range(15, 0, -1)]
        valuation_repo.get_backtest_month_end_dates.return_value = dates
        engine = BacktestEngine(company_repo, MagicMock(), valuation_repo)
        result = engine._find_period_dates(num_periods=5)
        assert result == dates[-5:]
        valuation_repo.get_backtest_month_end_dates.assert_called_once()
        cutoff = valuation_repo.get_backtest_month_end_dates.call_args.kwargs["max_date"]
        assert cutoff.day >= 28
        assert cutoff.month != (today - timedelta(days=365)).month

    def test_run_single_period_no_reports_returns_none(self):
        company_repo = MagicMock()
        financial_repo = MagicMock()
        financial_repo.get_latest_report_as_of.return_value = None
        valuation_repo = MagicMock()

        company = _make_company()
        engine = BacktestEngine(company_repo, financial_repo, valuation_repo)
        result = engine._run_single_period([company], date.today())
        assert result is None

    def test_run_single_period_excludes_company_without_fresh_observation_price(self):
        financial_repo = MagicMock()
        valuation_repo = MagicMock()
        valuation_repo.get_stock_price_on_date.return_value = None

        engine = BacktestEngine(MagicMock(), financial_repo, valuation_repo)
        result = engine._run_single_period([_make_company()], date.today())

        assert result is None
        financial_repo.get_latest_report_as_of.assert_not_called()

    def test_run_single_period_with_reports_ranks_and_computes_returns(self):
        company_repo = MagicMock()
        financial_repo = MagicMock()
        valuation_repo = MagicMock()

        period_date = date(2025, 12, 31)

        # Financial data
        report = _make_report(2025, period_end=date(2025, 12, 31))
        financial_repo.get_latest_report_as_of.return_value = report
        financial_repo.get_reports_as_of.return_value = [
            _make_report(2025, period_end=date(2025, 12, 31)),
            _make_report(2024, period_end=date(2024, 12, 31)),
            _make_report(2023, period_end=date(2023, 12, 31)),
        ]

        # Stock prices for valuation and forward returns
        valuation_repo.get_stock_price_on_date.return_value = _make_price(period_date, 50.0)
        valuation_repo.get_snapshot_history_as_of.return_value = {}
        valuation_repo.get_snapshot_history.return_value = {}
        valuation_repo.get_historical_as_of.return_value = ([], [], [])

        company = _make_company()
        engine = BacktestEngine(company_repo, financial_repo, valuation_repo)
        result = engine._run_single_period([company], period_date)

        assert result is not None
        assert result.company_count == 1
        assert result.eligible_count == 1
        assert result.deciles == []
        assert result.top_decile_spread_6m is None
        assert result.top_decile_spread_12m is None
        assert result.return_basis == "unavailable"
        assert result.return_coverage_6m_count == 0
        assert result.missing_return_company_ids_6m == (1,)
        assert len(result.correlations) == 5
        financial_repo.get_latest_report_as_of.assert_has_calls(
            [
                call(1, "year", period_date, availability_lag_days=90),
                call(1, "r12", period_date, availability_lag_days=45),
            ]
        )
        valuation_repo.get_current.assert_not_called()

    def test_reconstruct_uses_public_quarters_and_annual_fundamental_history(self):
        period_date = date(2025, 7, 31)
        annual = _make_report(2024, period_end=date(2024, 12, 31))
        prior_annual = _make_report(2023, period_end=date(2023, 12, 31))
        latest_quarter = _make_report(
            2025,
            period=2,
            period_end=date(2025, 6, 30),
            revenue=120.0,
        )
        prior_quarter = _make_report(
            2024,
            period=2,
            period_end=date(2024, 6, 30),
            revenue=100.0,
        )
        financial_repo = MagicMock()
        financial_repo.get_latest_report_as_of.side_effect = (
            lambda _company_id, period_type, *_args, **_kwargs: (
                annual if period_type == "year" else None
            )
        )
        financial_repo.get_reports_as_of.side_effect = (
            lambda _company_id, period_type, *_args, **_kwargs: (
                [annual, prior_annual]
                if period_type == "year"
                else [latest_quarter, prior_quarter]
            )
        )
        valuation_repo = MagicMock()
        valuation_repo.get_snapshot_history_as_of.return_value = {}
        valuation_repo.get_kpi_values_for_year.return_value = {
            KpiIds.ROIC: 15.0,
            KpiIds.NET_DEBT_EBITDA: 1.5,
        }
        valuation_repo.get_stock_price_on_date.return_value = _make_price(
            period_date
        )
        valuation_repo.get_historical_as_of.return_value = ([], [], [])
        engine = BacktestEngine(MagicMock(), financial_repo, valuation_repo)
        engine.reverse_dcf_skill.analyze_reports = MagicMock(return_value=None)

        financial, _, _, _, fundamentals = engine._reconstruct(
            _make_company(),
            period_date,
            _make_price(period_date),
        )

        assert financial.recent_revenue_growth == pytest.approx(0.20)
        assert fundamentals[KpiIds.ROIC] == 15.0
        assert fundamentals[KpiIds.NET_DEBT_EBITDA] == 1.5
        assert fundamentals["_sources"] == {
            KpiIds.ROIC: "annual_kpi_history",
            KpiIds.NET_DEBT_EBITDA: "annual_kpi_history",
        }
        valuation_repo.get_kpi_values_for_year.assert_called_once_with(
            1,
            KpiIds.GENERAL_FUNDAMENTAL_KPIS,
            2024,
        )

    def test_forward_returns_calculates_correctly(self):
        valuation_repo = MagicMock()
        today = date.today()

        def _get_price(cid, target_date, max_age_days=None):
            if target_date <= today:
                return _make_price(target_date, 50.0)
            days_ahead = (target_date - today).days
            if days_ahead >= 365:
                return _make_price(target_date, 55.0)  # +10% over year
            elif days_ahead >= 180:
                return _make_price(target_date, 52.50)  # +5% over 6 months
            return None

        valuation_repo.get_stock_price_on_date.side_effect = _get_price
        engine = BacktestEngine(
            MagicMock(), MagicMock(), valuation_repo, _dividend_repository()
        )

        ret_6m, ret_12m = engine._forward_returns(1, today)

        assert ret_6m == pytest.approx(0.05, rel=0.01)
        assert ret_12m == pytest.approx(0.10, rel=0.01)

    def test_forward_returns_include_reinvested_dividend(self):
        from kncompanyscraper.borsdata.dividend import CashDividend

        valuation_repo = MagicMock()
        start = date(2025, 1, 1)

        def _get_price(_company_id, target_date, max_age_days=None):
            if target_date == start:
                return _make_price(start, 100.0)
            return _make_price(target_date, 110.0)

        valuation_repo.get_stock_price_on_date.side_effect = _get_price
        valuation_repo.get_stock_price_on_or_after.return_value = _make_price(
            date(2025, 6, 2), 100.0
        )
        dividends = _dividend_repository()
        dividends.get_dividends.return_value = [
            CashDividend(date(2025, 6, 2), 5.0, "SEK", 0)
        ]
        engine = BacktestEngine(
            MagicMock(), MagicMock(), valuation_repo, dividends
        )

        ret_6m, ret_12m = engine._forward_returns(1, start)

        assert ret_6m == pytest.approx(0.155)
        assert ret_12m == pytest.approx(0.155)

    def test_long_horizon_observations_use_calendar_month_endpoints(self):
        valuation_repo = MagicMock()
        valuation_repo.get_stock_price_on_date.return_value = _make_price(
            date(2024, 2, 29), 100.0
        )
        engine = BacktestEngine(
            MagicMock(), MagicMock(), valuation_repo, _dividend_repository()
        )
        engine._forward_return_observations = MagicMock(
            return_value=(
                RealizedReturnObservation(0.05, 0.05, None, date(2024, 8, 29)),
                RealizedReturnObservation(0.10, 0.10, None, date(2025, 2, 28)),
            )
        )
        engine.total_return_calculator.calculate = MagicMock(
            side_effect=[
                RealizedReturnObservation(0.20, 0.20, None, date(2026, 2, 28)),
                RealizedReturnObservation(0.30, 0.30, None, date(2027, 2, 28)),
                RealizedReturnObservation(0.40, 0.40, None, date(2028, 2, 29)),
            ]
        )

        observations = engine._forward_return_observations_by_horizon(
            1, date(2024, 2, 29)
        )

        assert observations[24].total_return == pytest.approx(0.20)
        assert observations[48].total_return == pytest.approx(0.40)
        target_dates = [
            call.args[2]
            for call in engine.total_return_calculator.calculate.call_args_list
        ]
        assert target_dates == [
            date(2026, 2, 28),
            date(2027, 2, 28),
            date(2028, 2, 29),
        ]

    def test_benchmark_return_requires_gross_total_return_series(self):
        benchmark = MagicMock()
        benchmark.get_return_basis.return_value = "gross_total_return"
        benchmark.get_value_on_or_before.side_effect = [
            (date(2025, 1, 31), 1000.0),
            (date(2025, 7, 30), 1080.0),
        ]
        engine = BacktestEngine(
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), benchmark
        )

        result = engine._benchmark_return(date(2025, 1, 31), 180)

        assert result == pytest.approx(0.08)

        benchmark.get_return_basis.return_value = "price_return"
        assert engine._benchmark_return(date(2025, 1, 31), 180) is None

    def test_period_records_top_decile_benchmark_excess_and_coverage(self):
        companies = [_make_company(index, f"C{index}") for index in range(1, 11)]
        valuation_repo = MagicMock()
        valuation_repo.get_stock_price_on_date.return_value = _make_price(
            date(2025, 1, 31), 100.0
        )
        engine = BacktestEngine(
            MagicMock(), MagicMock(), valuation_repo, _dividend_repository(), MagicMock()
        )
        engine._reconstruct = MagicMock(
            return_value=(MagicMock(), None, None, {}, {})
        )
        engine.ranking_engine.rank = MagicMock(
            return_value=SimpleNamespace(
                scores=[
                    SimpleNamespace(
                        company_id=index,
                        total_score=100 - index,
                        rank_eligible=True,
                    )
                    for index in range(1, 11)
                ]
            )
        )
        engine._forward_return_observations = MagicMock(
            side_effect=lambda company_id, _from_date: (
                RealizedReturnObservation(
                    0.20 if company_id == 1 else -0.01 * company_id,
                    None,
                    None,
                    date(2025, 7, 30),
                ),
                RealizedReturnObservation(
                    0.30 if company_id == 1 else -0.01 * company_id,
                    None,
                    None,
                    date(2026, 1, 31),
                ),
            )
        )
        engine._benchmark_return = MagicMock(
            side_effect=[0.05, 0.10, None, None, None]
        )

        result = engine._run_single_period(companies, date(2025, 1, 31))

        assert result.top_decile_excess_6m == pytest.approx(0.15)
        assert result.top_decile_excess_12m == pytest.approx(0.20)
        assert result.return_coverage_6m_count == 10
        assert result.return_coverage_12m_count == 10
        assert result.missing_return_company_ids_6m == ()
        assert len(result.attributions) == 10
        assert result.attributions[0].rank == 1
        assert result.attributions[0].decile == 1
        assert result.attributions[0].contribution_6m == pytest.approx(0.20)
        assert result.attributions[-1].decile == 10

    def test_attribution_contributions_sum_to_decile_average(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        companies = {
            index: _make_company(index, f"C{index}") for index in range(1, 21)
        }
        scores = [
            SimpleNamespace(
                company_id=index,
                total_score=101 - index,
                quality_score=20.0,
                growth_score=15.0,
                valuation_score=30.0,
                balance_sheet_score=10.0,
            )
            for index in range(1, 21)
        ]
        observations = {
            index: (
                RealizedReturnObservation(
                    index / 100, index / 100, None, date(2025, 7, 30)
                ),
                RealizedReturnObservation(
                    index / 50, index / 50, None, date(2026, 1, 30)
                ),
            )
            for index in range(1, 21)
        }

        attributions = engine._build_attributions(
            date(2025, 1, 31), scores, companies, observations
        )

        assert sum(
            item.contribution_12m
            for item in attributions
            if item.decile == 1
        ) == pytest.approx(0.03)
        assert attributions[0].company_name == "Test Co"
        assert attributions[0].quality_score == 20.0
        assert attributions[0].sector_id is None
        assert attributions[0].benchmark_12m_return is None

    def test_forward_returns_none_when_no_start_price(self):
        valuation_repo = MagicMock()
        valuation_repo.get_stock_price_on_date.return_value = None
        engine = BacktestEngine(MagicMock(), MagicMock(), valuation_repo)

        ret_6m, ret_12m = engine._forward_returns(1, date.today())
        assert ret_6m is None
        assert ret_12m is None

    def test_balanced_deciles_and_return_counts(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        scores = [
            SimpleNamespace(company_id=i, total_score=100 - i)
            for i in range(15)
        ]
        returns = {
            i: (0.10 if i % 2 == 0 else -0.05, 0.20)
            for i in range(15)
        }

        deciles = engine._build_deciles(scores, returns)

        assert len(deciles) == 10
        assert sum(decile.count for decile in deciles) == 15
        assert max(decile.count for decile in deciles) - min(
            decile.count for decile in deciles
        ) <= 1
        assert sum(decile.count_6m for decile in deciles) == 15
        assert sum(decile.count_12m for decile in deciles) == 15

    def test_fewer_than_ten_companies_does_not_claim_deciles(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        scores = [SimpleNamespace(company_id=i) for i in range(9)]
        assert engine._build_deciles(scores, {}) == []


class TestPearson:
    def test_perfect_positive_correlation(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        pairs = [(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]
        assert engine._pearson(pairs) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        pairs = [(1.0, 6.0), (2.0, 4.0), (3.0, 2.0)]
        assert engine._pearson(pairs) == pytest.approx(-1.0)

    def test_no_correlation(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        pairs = [(1.0, 5.0), (2.0, 5.0), (3.0, 5.0)]
        # Zero variance in y → zero denominator → 0.0
        assert engine._pearson(pairs) == 0.0

    def test_too_few_pairs_returns_zero(self):
        engine = BacktestEngine(MagicMock(), MagicMock(), MagicMock())
        assert engine._pearson([(1.0, 2.0)]) == 0.0
        assert engine._pearson([]) == 0.0


def test_backtest_cli_handles_missing_decile_returns_and_prints_complete_row(capsys):
    deciles = [DecilePerformance(decile=i) for i in range(1, 11)]
    deciles[0] = DecilePerformance(
        decile=1,
        avg_6m_return=0.10,
        avg_12m_return=0.20,
        hit_rate_6m=0.60,
        hit_rate_12m=0.70,
        count=2,
        count_6m=2,
        count_12m=2,
    )
    result = PeriodResult(
        observation_date="2025-01-31",
        deciles=deciles,
        eligible_count=20,
        top_decile_spread_6m=0.05,
        top_decile_spread_12m=-0.02,
        top_decile_excess_6m=0.03,
        top_decile_excess_12m=-0.01,
    )

    with patch(
        "kncompanyscraper.analysis.backtesting.backtest_engine.BacktestEngine.run",
        return_value=[result],
    ):
        _cmd_backtest(1)

    output = capsys.readouterr().out
    assert "1           10.0%    20.0%      60%      70%      2      2" in output
    assert "10" in output
    assert "—" in output
    assert "Top-bottom 6m      1/1 positive (100%); median=5.0%" in output
    assert "Top-bottom 12m     0/1 positive (0%); median=-2.0%" in output
    assert "not independent statistical trials" in output


def test_backtest_cli_writes_company_attribution_csv(tmp_path, capsys):
    attribution = CompanyAttribution(
        observation_date="2025-01-31",
        company_id=42,
        company_name="Test, AB",
        ticker="TEST",
        rank=1,
        decile=1,
        quality_score=20.0,
        growth_score=15.0,
        valuation_score=30.0,
        balance_sheet_score=10.0,
        total_score=75.0,
        return_6m=0.10,
        return_12m=0.20,
        price_return_6m=0.08,
        price_return_12m=0.15,
        contribution_6m=0.05,
        contribution_12m=0.10,
        return_issue_6m=None,
        return_issue_12m=None,
        return_end_date_6m="2025-07-30",
        return_end_date_12m="2026-01-30",
    )
    result = PeriodResult(
        observation_date="2025-01-31",
        attributions=[attribution],
        eligible_count=1,
    )
    output_path = tmp_path / "attribution.csv"

    with patch(
        "kncompanyscraper.analysis.backtesting.backtest_engine.BacktestEngine.run",
        return_value=[result],
    ):
        _cmd_backtest(1, output_path)

    content = output_path.read_text()
    assert "observation_date,company_id,company_name" in content
    assert "return_24m" in content
    assert "return_48m" in content
    assert '42,"Test, AB",TEST,1,1' in content
    assert "Company attribution CSV" in capsys.readouterr().out


def test_backtest_cli_writes_long_form_scoring_audit(tmp_path, capsys):
    metric = MetricAttribution(
        observation_date="2025-01-31",
        company_id=42,
        company_name="Test AB",
        ticker="TEST",
        ranking_model="general",
        category="valuation",
        metric="margin_of_safety",
        raw_value=0.02,
        normalized_score=70.0,
        configured_weight=0.12,
        effective_weight=0.15,
        category_contribution=10.5,
        category_score=60.0,
        reconstruction_error=0.0,
        total_category_weight=0.30,
        total_contribution=3.15,
        available=True,
        transformation="linear[-0.05,0.05]",
        dependencies="fcf_yield|debt_to_equity",
        cross_category_dependencies="quality_score|growth_score",
        provenance="report_reconstructed",
    )
    result = PeriodResult(
        observation_date="2025-01-31",
        metric_attributions=[metric],
        eligible_count=1,
    )
    output_path = tmp_path / "scoring-audit.csv"

    with patch(
        "kncompanyscraper.analysis.backtesting.backtest_engine.BacktestEngine.run",
        return_value=[result],
    ):
        _cmd_backtest(1, scoring_audit_csv=output_path)

    content = output_path.read_text()
    assert "category,metric,raw_value,normalized_score" in content
    assert "benchmark_48m_return" in content
    assert "quality_score|growth_score" in content
    assert "Scoring audit CSV" in capsys.readouterr().out
