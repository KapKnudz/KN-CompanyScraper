from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from kncompanyscraper.analysis.backtesting.backtest_engine import BacktestEngine
from kncompanyscraper.analysis.backtesting.backtest_result import (
    CategoryCorrelation,
    DecilePerformance,
    PeriodResult,
)
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.models.company import Company
from kncompanyscraper.main import _cmd_backtest


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
        assert len(result.correlations) == 6  # reverse DCF is a standalone signal too
        financial_repo.get_latest_report_as_of.assert_has_calls(
            [
                call(1, "year", period_date, availability_lag_days=90),
                call(1, "r12", period_date, availability_lag_days=45),
            ]
        )
        valuation_repo.get_current.assert_not_called()

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
        engine = BacktestEngine(MagicMock(), MagicMock(), valuation_repo)

        ret_6m, ret_12m = engine._forward_returns(1, today)

        assert ret_6m == pytest.approx(0.05, rel=0.01)
        assert ret_12m == pytest.approx(0.10, rel=0.01)

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
