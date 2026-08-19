"""
Tests for financial, valuation, and insider analysis modules using mock JSON data
that mirrors the Borsdata API swagger response schemas.

Run with: python -m pytest tests/test_analysis.py -v
"""

import json
import math
from pathlib import Path
from dataclasses import dataclass

import pytest

from kncompanyscraper.analysis.financial.financial_mapper import FinancialMapper
from kncompanyscraper.analysis.financial.financial_calculator import FinancialCalculator
from kncompanyscraper.analysis.financial.financial_result import FinancialResult, CurrentFinancials, HistoricalFinancials
from kncompanyscraper.analysis.valuation.valuation_mapper import ValuationMapper
from kncompanyscraper.analysis.valuation.valuation_calculator import ValuationCalculator
from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.analysis.valuation.current_valuation import CurrentValuation
from kncompanyscraper.analysis.valuation.historical_valuation import HistoricalValuation
from kncompanyscraper.borsdata.report import Report

MOCKS_DIR = Path(__file__).resolve().parent / "mocks"


# ---------------------------------------------------------------------------
# Helpers: load mock JSON and convert to domain objects
# ---------------------------------------------------------------------------

def load_mock(filename: str) -> dict:
    path = MOCKS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Mock file not found: {path}")
    with open(path) as f:
        return json.load(f)


def report_from_swagger(swagger_report: dict) -> Report:
    """
    Convert a Borsdata API ReportV1 (from swagger) into the project's
    borsdata.report.Report domain object.
    """
    return Report(
        revenue=swagger_report.get("revenues", 0) or 0,
        operating_profit=swagger_report.get("operating_Income", 0) or 0,
        ebit=swagger_report.get("operating_Income", 0) or 0,
        ebitda=(swagger_report.get("operating_Income", 0) or 0)
        + (swagger_report.get("intangible_Assets", 0) or 0),  # rough EBITDA estimate
        net_income=swagger_report.get("profit_To_Equity_Holders", 0) or 0,
        free_cash_flow=swagger_report.get("free_Cash_Flow", 0) or 0,
        equity=swagger_report.get("total_Equity", 0) or 0,
        total_assets=swagger_report.get("total_Assets", 0) or 0,
        total_debt=swagger_report.get("net_Debt", 0) or 0,
        shares_outstanding=swagger_report.get("number_Of_Shares", 0) or 0,
    )


def reports_from_mock() -> list[Report]:
    """Load reports_mock.json and convert to Report objects."""
    data = load_mock("reports_mock.json")
    return [report_from_swagger(r) for r in data["reports"]]


# ---------------------------------------------------------------------------
# Financial tests
# ---------------------------------------------------------------------------

class TestFinancialMapper:
    """Test that FinancialMapper correctly transforms Report → analysis domain objects."""

    def test_to_current_maps_all_fields(self):
        reports = reports_from_mock()
        latest = reports[-1]  # 2026 report

        mapper = FinancialMapper()
        current = mapper.to_current(latest)

        assert current.revenue == 550_000_000
        assert current.ebit == 70_000_000
        assert current.net_income == 55_000_000
        assert current.free_cash_flow == 35_000_000
        assert current.equity == 180_000_000
        assert current.total_assets == 680_000_000
        assert current.total_debt == 160_000_000

    def test_to_historical_extracts_lists_correctly(self):
        reports = reports_from_mock()
        # Exclude the latest (index -1) to simulate historical
        historical_reports = reports[:-1]

        mapper = FinancialMapper()
        historical = mapper.to_historical(historical_reports)

        assert historical.revenue_history == [420_000_000, 450_000_000, 480_000_000, 520_000_000]
        assert historical.ebit_history == [52_000_000, 58_000_000, 62_000_000, 65_000_000]
        assert historical.net_income_history == [38_000_000, 43_000_000, 47_000_000, 50_000_000]
        assert historical.fcf_history == [25_000_000, 28_000_000, 30_000_000, 32_000_000]

    def test_to_historical_empty_list_returns_empty_histories(self):
        mapper = FinancialMapper()
        historical = mapper.to_historical([])

        assert historical.revenue_history == []
        assert historical.ebit_history == []
        assert historical.net_income_history == []
        assert historical.fcf_history == []


class TestFinancialCalculator:
    """Test that FinancialCalculator computes correct ratios and growth rates."""

    def test_full_calculation_with_mock_data(self):
        reports = reports_from_mock()
        mapper = FinancialMapper()
        calculator = FinancialCalculator()

        current = mapper.to_current(reports[-1])
        historical = mapper.to_historical(reports[:-1])

        result = calculator.calculate(current, historical)

        # --- Margins ---
        assert result.operating_margin == pytest.approx(70_000_000 / 550_000_000, rel=1e-6)
        assert result.net_margin == pytest.approx(55_000_000 / 550_000_000, rel=1e-6)
        assert result.fcf_margin == pytest.approx(35_000_000 / 550_000_000, rel=1e-6)

        # --- Growth (three-year CAGR) ---
        assert result.revenue_growth == pytest.approx((550_000_000 / 450_000_000) ** (1 / 3) - 1)
        assert result.ebit_growth == pytest.approx((70_000_000 / 58_000_000) ** (1 / 3) - 1)
        assert result.net_income_growth == pytest.approx((55_000_000 / 43_000_000) ** (1 / 3) - 1)
        assert result.revenue_growth_years == 3

        # --- Returns ---
        assert result.roe == pytest.approx(55_000_000 / 180_000_000, rel=1e-6)
        assert result.roa == pytest.approx(55_000_000 / 680_000_000, rel=1e-6)

        # --- Health ---
        assert result.debt_to_equity == pytest.approx(160_000_000 / 180_000_000, rel=1e-6)

    def test_calculate_ratio_returns_none_for_zero_denominator(self):
        calc = FinancialCalculator()
        assert calc.calculate_ratio(100.0, 0) is None
        assert calc.calculate_ratio(100.0, None) is None
        assert calc.calculate_ratio(None, 50.0) is None

    def test_calculate_growth_returns_none_for_empty_history(self):
        calc = FinancialCalculator()
        assert calc.calculate_growth(100.0, []) is None

    def test_calculate_growth_returns_none_for_zero_previous(self):
        calc = FinancialCalculator()
        assert calc.calculate_growth(100.0, [0.0]) is None

    def test_calculate_growth_returns_none_for_missing_previous(self):
        calc = FinancialCalculator()
        assert calc.calculate_growth(100.0, [None]) is None

    def test_calculate_growth_with_negative_previous(self):
        calc = FinancialCalculator()
        assert calc.calculate_growth(100.0, [-50.0]) is None
        assert calc.is_turnaround(100.0, [-50.0]) is True

    def test_all_none_when_current_is_empty(self):
        calc = FinancialCalculator()
        current = CurrentFinancials(
            revenue=None, ebit=None, ebitda=None, net_income=None,
            free_cash_flow=None, equity=None, total_assets=None, total_debt=None,
            operating_profit=None
        )
        historical = HistoricalFinancials(
            revenue_history=[], ebit_history=[], fcf_history=[], net_income_history=[],
        )
        result = calc.calculate(current, historical)

        assert result.operating_margin is None
        assert result.net_margin is None
        assert result.fcf_margin is None
        assert result.revenue_growth is None
        assert result.ebit_growth is None
        assert result.net_income_growth is None
        assert result.roe is None
        assert result.roa is None
        assert result.debt_to_equity is None


# ---------------------------------------------------------------------------
# Valuation tests
# ---------------------------------------------------------------------------

# Build domain objects directly from mock data (since ValuationRepository is a stub,
# this simulates what the repository would return after parsing KPI endpoints).

def current_valuation_from_mock() -> CurrentValuation:
    """
    Construct a CurrentValuation from the kpi_screener mock.
    In production, ValuationRepository would parse KPI screener responses
    and return this domain object.
    """
    data = load_mock("kpi_screener_mock.json")
    kpis = {entry["_label"]: entry for entry in data["_all_valuation_kpis"]}

    def kpi_value(label: str) -> float | None:
        entry = kpis.get(label)
        if entry and entry["values"]:
            return entry["values"][0]["n"]
        return None

    return CurrentValuation(
        market_cap=kpi_value("Market Cap"),
        enterprise_value=kpi_value("Enterprise Value"),
        pe=kpi_value("P/E (current)"),
        ev_ebit=kpi_value("EV/EBIT (current)"),
        ev_ebitda=kpi_value("EV/EBITDA (current)"),
        pb=kpi_value("P/B (current)"),
        ps=kpi_value("P/S (current)"),
        pfcf=kpi_value("P/FCF (current)"),
        peg=kpi_value("PEG Ratio"),
        dividend_yield=kpi_value("Dividend Yield %"),
    )


def historical_valuation_from_mock() -> HistoricalValuation:
    """Construct HistoricalValuation from kpi_history mock."""
    data = load_mock("kpi_history_mock.json")

    def values_for(key: str) -> list[float]:
        return [point["v"] for point in data[key]["values"]]

    pe_history = values_for("pe_history")
    ev_ebit_history = values_for("ev_ebit_history")
    pb_history = values_for("pb_history")

    mapper = ValuationMapper()
    return mapper.to_historical(pe_history, ev_ebit_history, pb_history)


class TestValuationMapper:
    """Test that ValuationMapper correctly builds domain objects."""

    def test_to_current_passes_through_all_fields(self):
        current = current_valuation_from_mock()

        assert current.pe == pytest.approx(18.50)
        assert current.ev_ebit == pytest.approx(13.20)
        assert current.ev_ebitda == pytest.approx(10.80)
        assert current.pb == pytest.approx(3.40)
        assert current.ps == pytest.approx(2.10)
        assert current.pfcf == pytest.approx(25.40)
        assert current.peg == pytest.approx(0.85)
        assert current.market_cap == pytest.approx(550_000_000_000)
        assert current.enterprise_value == pytest.approx(710_000_000_000)
        assert current.dividend_yield == pytest.approx(4.10)

    def test_to_historical_computes_averages_correctly(self):
        pe_hist = [12.5, 14.2, 16.8, 15.9, 18.5]
        ev_ebit_hist = [9.2, 10.5, 12.1, 11.8, 13.2]
        pb_hist = [2.1, 2.45, 2.9, 3.15, 3.4]

        mapper = ValuationMapper()
        hist = mapper.to_historical(pe_hist, ev_ebit_hist, pb_hist)

        assert hist.pe_history == pe_hist
        assert hist.ev_ebit_history == ev_ebit_hist
        assert hist.pb_history == pb_hist
        assert hist.avg_pe == pytest.approx(sum(pe_hist) / len(pe_hist), rel=1e-6)
        assert hist.avg_ev_ebit == pytest.approx(sum(ev_ebit_hist) / len(ev_ebit_hist), rel=1e-6)
        assert hist.avg_pb == pytest.approx(sum(pb_hist) / len(pb_hist), rel=1e-6)
        assert hist.median_pe == 15.9
        assert hist.median_ev_ebit == 11.8
        assert hist.median_pb == 2.9

    def test_to_historical_with_single_value(self):
        mapper = ValuationMapper()
        hist = mapper.to_historical([10.0], [5.0], [2.0])

        assert hist.avg_pe == 10.0
        assert hist.median_pe == 10.0
        assert hist.avg_ev_ebit == 5.0
        assert hist.median_ev_ebit == 5.0


class TestValuationCalculator:
    """Test that ValuationCalculator computes correct derived metrics."""

    def test_full_calculation_with_mock_data(self):
        current = current_valuation_from_mock()
        historical = historical_valuation_from_mock()
        calculator = ValuationCalculator()

        result = calculator.calculate(current, historical)

        # Direct passthrough
        assert result.pe == pytest.approx(18.50)
        assert result.ev_ebit == pytest.approx(13.20)
        assert result.ev_ebitda == pytest.approx(10.80)
        assert result.pb == pytest.approx(3.40)
        assert result.ps == pytest.approx(2.10)
        assert result.pfcf == pytest.approx(25.40)
        assert result.peg == pytest.approx(0.85)

        # Yields
        assert result.earnings_yield == pytest.approx(1 / 18.50, rel=1e-6)
        assert result.free_cash_flow_yield == pytest.approx(1 / 25.40, rel=1e-6)

        # vs 5y avg
        avg_pe = (12.5 + 14.2 + 16.8 + 15.9 + 18.5) / 5  # = 15.58
        avg_ev_ebit = (9.2 + 10.5 + 12.1 + 11.8 + 13.2) / 5  # = 11.36
        avg_pb = (2.1 + 2.45 + 2.9 + 3.15 + 3.4) / 5  # = 2.80
        assert result.pe_vs_5y_avg == pytest.approx(18.50 / avg_pe, rel=1e-6)
        assert result.ev_ebit_vs_5y_avg == pytest.approx(13.20 / avg_ev_ebit, rel=1e-6)
        assert result.pb_vs_5y_avg == pytest.approx(3.40 / avg_pb, rel=1e-6)

        # Percentiles: current PE 18.50 vs [12.5, 14.2, 15.9, 16.8, 18.5]
        # All 5 values <= 18.50, so 5/5 * 100 = 100%
        assert result.pe_percentile == pytest.approx(100.0)

        # Percentile: current EV/EBIT 13.20 vs [9.2, 10.5, 11.8, 12.1, 13.2]
        # All 5 <= 13.20 → 100%
        assert result.ev_ebit_percentile == pytest.approx(100.0)
        assert result.ev_ebit_guardrail_low == pytest.approx(9.72)
        assert result.ev_ebit_guardrail_high == pytest.approx(12.76)
        assert result.ev_ebit_history_count == 5

    def test_percentile_with_middle_value(self):
        calc = ValuationCalculator()
        percentile = calc.calculate_percentile(3.0, [1.0, 2.0, 3.0, 4.0, 5.0])
        # 3 values <= 3.0 out of 5 = 60%
        assert percentile == pytest.approx(60.0)

    def test_percentile_all_below(self):
        calc = ValuationCalculator()
        percentile = calc.calculate_percentile(10.0, [1.0, 2.0, 3.0])
        assert percentile == pytest.approx(100.0)

    def test_percentile_all_above(self):
        calc = ValuationCalculator()
        percentile = calc.calculate_percentile(0.0, [1.0, 2.0, 3.0])
        assert percentile == pytest.approx(0.0)

    def test_percentile_empty_history_returns_none(self):
        calc = ValuationCalculator()
        assert calc.calculate_percentile(10.0, []) is None

    def test_percentile_none_value_returns_none(self):
        calc = ValuationCalculator()
        assert calc.calculate_percentile(None, [1.0, 2.0]) is None

    def test_history_bound_requires_five_positive_observations(self):
        calc = ValuationCalculator()

        assert calc.calculate_history_bound([1.0, 2.0, 3.0, 4.0], 0.10) is None
        assert calc.calculate_history_bound([-1.0, 1.0, 2.0, 3.0, 4.0], 0.90) is None

    def test_ratio_returns_none_for_zero_denominator(self):
        calc = ValuationCalculator()
        assert calc.calculate_ratio(100.0, 0) is None
        assert calc.calculate_ratio(100.0, None) is None
        assert calc.calculate_ratio(None, 50.0) is None

    def test_all_none_when_current_is_empty(self):
        calc = ValuationCalculator()
        current = CurrentValuation(
            market_cap=None, enterprise_value=None, pe=None, ev_ebit=None,
            ev_ebitda=None, pb=None, ps=None, pfcf=None, peg=None, dividend_yield=None,
        )
        historical = HistoricalValuation(
            pe_history=[], ev_ebit_history=[], pb_history=[],
            avg_pe=None, avg_ev_ebit=None, avg_pb=None,
            median_pe=None, median_ev_ebit=None, median_pb=None,
        )
        result = calc.calculate(current, historical)

        assert result.earnings_yield is None
        assert result.free_cash_flow_yield is None
        assert result.pe_vs_5y_avg is None
        assert result.ev_ebit_vs_5y_avg is None
        assert result.pb_vs_5y_avg is None
        assert result.pe_percentile is None
        assert result.ev_ebit_percentile is None


# ---------------------------------------------------------------------------
# Insider data verification tests
# ---------------------------------------------------------------------------
# InsiderCalculator and InsiderMapper are not yet implemented (empty files).
# These tests verify the mock data shapes are correct and exercise
# CurrentInsiderActivity / HistoricalInsiderActivity construction.

from kncompanyscraper.analysis.insider.current_insider_activity import CurrentInsiderActivity
from kncompanyscraper.analysis.insider.historical_insider_activity import HistoricalInsiderActivity
from kncompanyscraper.analysis.insider.insider_result import InsiderResult


class TestInsiderMockData:
    """Verify insider mock data can be parsed into domain shapes."""

    def test_insider_mock_has_expected_structure(self):
        data = load_mock("insider_holdings_mock.json")

        assert "list" in data
        assert len(data["list"]) == 1
        insider_entry = data["list"][0]
        assert insider_entry["insId"] == 3
        assert len(insider_entry["values"]) == 8

        # Verify transaction types: 1=buy, 2=sell
        buys = [t for t in insider_entry["values"] if t["transactionType"] == 1]
        sells = [t for t in insider_entry["values"] if t["transactionType"] == 2]
        assert len(buys) == 6
        assert len(sells) == 2

    def test_build_current_insider_activity_from_mock(self):
        data = load_mock("insider_holdings_mock.json")
        transactions = data["list"][0]["values"]

        buys = [t for t in transactions if t["transactionType"] == 1]
        sells = [t for t in transactions if t["transactionType"] == 2]

        activity = CurrentInsiderActivity(
            buy_value=sum(t["amount"] for t in buys),
            sell_value=sum(t["amount"] for t in sells),
            buy_count=len(buys),
            sell_count=len(sells),
            unique_buyers=len({t["ownerName"] for t in buys}),
            unique_sellers=len({t["ownerName"] for t in sells}),
            largest_buy=max((t["amount"] for t in buys), default=None),
            largest_sell=max((t["amount"] for t in sells), default=None),
        )

        # 6 buys: 3682500 + 2080000 + 1350000 + 765000 + 2750000 + 516000 = 11,143,500
        assert activity.buy_value == pytest.approx(11_143_500.0)
        # 2 sells: 3360000 + 1060000 = 4,420,000
        assert activity.sell_value == pytest.approx(4_420_000.0)
        assert activity.buy_count == 6
        assert activity.sell_count == 2
        assert activity.unique_buyers == 5  # Erik x2, Maria, Per, Lars, Helena
        assert activity.unique_sellers == 2  # Karin, Anna
        assert activity.largest_buy == pytest.approx(3_682_500.0)  # Erik's first buy
        assert activity.largest_sell == pytest.approx(3_360_000.0)  # Karin's sell

    def test_net_buying_is_positive(self):
        """Net insider buying should be positive for our mock data."""
        data = load_mock("insider_holdings_mock.json")
        transactions = data["list"][0]["values"]

        buys = [t for t in transactions if t["transactionType"] == 1]
        sells = [t for t in transactions if t["transactionType"] == 2]

        net_buying = sum(t["amount"] for t in buys) - sum(t["amount"] for t in sells)
        assert net_buying > 0  # More buying than selling = bullish signal


# ---------------------------------------------------------------------------
# Stock price mock data tests
# ---------------------------------------------------------------------------

class TestStockPriceMockData:
    """Verify stock price mock data matches the swagger StockPricesRespV1 schema."""

    def test_stock_prices_have_expected_shape(self):
        data = load_mock("stock_prices_mock.json")

        assert data["instrument"] == 3
        assert len(data["stockPricesList"]) == 5

        # Each price point has the abbreviated OHLCV fields from StockPriceV1
        latest = data["stockPricesList"][0]
        assert "d" in latest
        assert "c" in latest
        assert "h" in latest
        assert "l" in latest
        assert "o" in latest
        assert "v" in latest

    def test_last_close_price_is_278(self):
        data = load_mock("stock_prices_mock.json")
        assert data["stockPricesList"][0]["c"] == pytest.approx(278.0)


# ---------------------------------------------------------------------------
# Report ↔ swagger consistency check
# ---------------------------------------------------------------------------

class TestReportRoundTrip:
    """Verify the mock report JSON maps correctly to the Report domain object."""

    def test_all_reports_parse_without_error(self):
        reports = reports_from_mock()
        assert len(reports) == 5

    def test_reports_are_sorted_chronologically(self):
        """Mock data has oldest first, newest last — verify."""
        reports = reports_from_mock()
        revenues = [r.revenue for r in reports]
        assert revenues == sorted(revenues), "Reports should be in chronological order"

    def test_shares_outstanding_is_preserved(self):
        reports = reports_from_mock()
        for r in reports:
            assert r.shares_outstanding == 2_033_000_000


# ---------------------------------------------------------------------------
# Integration-style test: full pipeline with mock data
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Wire mocks through mapper → calculator and verify non-None results."""

    def test_financial_pipeline_returns_valid_result(self):
        reports = reports_from_mock()
        mapper = FinancialMapper()
        calculator = FinancialCalculator()

        current = mapper.to_current(reports[-1])
        historical = mapper.to_historical(reports[:-1])
        result = calculator.calculate(current, historical)

        # All computed fields should be non-None with our mock data
        assert result.operating_margin is not None
        assert result.net_margin is not None
        assert result.fcf_margin is not None
        assert result.revenue_growth is not None
        assert result.ebit_growth is not None
        assert result.net_income_growth is not None
        assert result.revenue_per_share_growth == pytest.approx(result.revenue_growth)
        assert result.share_count_growth == pytest.approx(0.0)
        assert result.roe is not None
        assert result.roa is not None
        assert result.debt_to_equity is not None

        # Sanity: growth should be positive (mock shows growing company)
        assert result.revenue_growth > 0
        assert result.ebit_growth > 0
        assert result.net_income_growth > 0

    def test_per_share_growth_removes_growth_created_only_by_dilution(self):
        current = CurrentFinancials(
            revenue=200,
            operating_profit=20,
            ebit=20,
            ebitda=None,
            net_income=10,
            free_cash_flow=10,
            equity=100,
            total_assets=200,
            total_debt=20,
            shares_outstanding=200,
        )
        historical = HistoricalFinancials(
            revenue_history=[100, 100, 100],
            ebit_history=[10, 10, 10],
            fcf_history=[5, 5, 5],
            net_income_history=[5, 5, 5],
            equity_history=[50, 50, 50],
            shares_history=[100, 100, 100],
            operating_profit_history=[10, 10, 10],
        )

        result = FinancialCalculator().calculate(current, historical)

        assert result.revenue_growth > 0
        assert result.revenue_per_share_growth == pytest.approx(0.0)
        assert result.share_count_growth > 0.05
        assert result.share_dilution is True

    def test_cash_quality_margin_stability_and_recent_quarter_are_calculated(self):
        current = CurrentFinancials(
            revenue=120,
            operating_profit=24,
            ebit=24,
            ebitda=None,
            net_income=12,
            free_cash_flow=10,
            equity=60,
            total_assets=120,
            total_debt=10,
            shares_outstanding=100,
            gross_income=60,
            operating_cash_flow=15,
        )
        historical = HistoricalFinancials(
            revenue_history=[90, 100, 110],
            ebit_history=[18, 20, 22],
            fcf_history=[8, 9, 10],
            net_income_history=[9, 10, 11],
            equity_history=[45, 50, 55],
            shares_history=[100, 100, 100],
            operating_profit_history=[18, 20, 22],
        )
        latest_quarter = CurrentFinancials(35, 7, 7, None, 4, 3, 60, 120, 10)
        prior_quarter = CurrentFinancials(25, 5, 5, None, 3, 2, 55, 110, 10)

        result = FinancialCalculator().calculate(
            current,
            historical,
            latest_quarter=latest_quarter,
            prior_year_quarter=prior_quarter,
        )

        assert result.gross_margin == pytest.approx(0.5)
        assert result.cash_conversion == pytest.approx(1.25)
        assert result.fcf_conversion == pytest.approx(10 / 12)
        assert result.operating_margin_volatility == pytest.approx(0.0)
        assert result.positive_fcf_ratio == pytest.approx(1.0)
        assert result.recent_revenue_growth == pytest.approx(0.4)
        assert result.recent_growth_acceleration is True

    def test_valuation_pipeline_returns_valid_result(self):
        current = current_valuation_from_mock()
        historical = historical_valuation_from_mock()
        calculator = ValuationCalculator()

        result = calculator.calculate(current, historical)

        assert result.pe is not None
        assert result.ev_ebit is not None
        assert result.ev_ebitda is not None
        assert result.pb is not None
        assert result.earnings_yield is not None
        assert result.pe_vs_5y_avg is not None
        assert result.pe_percentile is not None
        assert result.ev_ebit_percentile is not None
