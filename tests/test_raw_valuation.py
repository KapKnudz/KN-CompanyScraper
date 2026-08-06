"""Tests for raw valuation computation from stock price + report data."""

import pytest
from datetime import date

from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.analysis.valuation.raw_valuation import (
    RawValuation,
    compute_raw_valuation,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def make_stock_price(close: float) -> StockPrice:
    return StockPrice(date=date(2026, 8, 1), close=close)


def make_report(**overrides) -> Report:
    defaults = {
        "revenue": 500_000_000,
        "operating_profit": 70_000_000,
        "ebit": 70_000_000,
        "ebitda": 100_000_000,
        "net_income": 50_000_000,
        "free_cash_flow": 35_000_000,
        "equity": 180_000_000,
        "total_assets": 680_000_000,
        "total_debt": 160_000_000,
        "shares_outstanding": 20_000_000,
    }
    defaults.update(overrides)
    return Report(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputeRawValuation:
    def test_full_computation(self):
        """With complete data, all fields should be computed."""
        price = make_stock_price(close=250.0)
        report = make_report()
        rv = compute_raw_valuation(price, report)

        # market_cap = 250 * 20M = 5B
        assert rv.market_cap == pytest.approx(5_000_000_000)
        # enterprise_value = 5B + 160M = 5.16B
        assert rv.enterprise_value == pytest.approx(5_160_000_000)

        # earnings_yield = 50M / 5B = 0.01 = 1%
        assert rv.earnings_yield == pytest.approx(0.01)
        # fcf_yield = 35M / 5B = 0.007 = 0.7%
        assert rv.fcf_yield == pytest.approx(0.007)
        # sales_yield = 500M / 5B = 0.10 = 10%
        assert rv.sales_yield == pytest.approx(0.10)
        # book_yield = 180M / 5B = 0.036 = 3.6%
        assert rv.book_yield == pytest.approx(0.036)

        # pe = 5B / 50M = 100
        assert rv.pe == pytest.approx(100.0)
        # pfcf = 5B / 35M ≈ 142.86
        assert rv.pfcf == pytest.approx(142.857, rel=1e-3)
        # ps = 5B / 500M = 10
        assert rv.ps == pytest.approx(10.0)
        # pb = 5B / 180M ≈ 27.78
        assert rv.pb == pytest.approx(27.778, rel=1e-3)

        # ev_ebit = 5.16B / 70M ≈ 73.71
        assert rv.ev_ebit == pytest.approx(73.714, rel=1e-3)
        # ev_ebitda = 5.16B / 100M = 51.60
        assert rv.ev_ebitda == pytest.approx(51.60, rel=1e-3)

    def test_none_stock_price_returns_empty(self):
        rv = compute_raw_valuation(None, make_report())
        assert rv.market_cap is None
        assert rv.pe is None

    def test_currency_mismatch_returns_empty(self):
        price = make_stock_price(100.0)
        price.currency = "SEK"
        report = make_report(currency="EUR")

        rv = compute_raw_valuation(price, report)
        assert rv.market_cap is None
        assert rv.pe is None

    def test_none_report_returns_empty(self):
        rv = compute_raw_valuation(make_stock_price(100.0), None)
        assert rv.market_cap is None
        assert rv.pe is None

    def test_zero_shares_returns_empty(self):
        price = make_stock_price(100.0)
        report = make_report(shares_outstanding=0)
        rv = compute_raw_valuation(price, report)
        assert rv.market_cap is None

    def test_zero_close_returns_empty(self):
        price = make_stock_price(0.0)
        report = make_report()
        rv = compute_raw_valuation(price, report)
        assert rv.market_cap is None

    def test_negative_net_income_gives_negative_yields(self):
        """Net income can be negative — yields and P/E should reflect that."""
        price = make_stock_price(50.0)
        report = make_report(net_income=-10_000_000)
        rv = compute_raw_valuation(price, report)

        assert rv.market_cap == pytest.approx(1_000_000_000)
        assert rv.earnings_yield == pytest.approx(-0.01)
        assert rv.pe == pytest.approx(-100.0)

    def test_no_debt_gives_ev_equals_market_cap(self):
        price = make_stock_price(100.0)
        report = make_report(total_debt=0)
        rv = compute_raw_valuation(price, report)

        assert rv.market_cap == pytest.approx(2_000_000_000)
        assert rv.enterprise_value == pytest.approx(2_000_000_000)

    def test_zero_operating_income_gives_none_ev_ebit(self):
        price = make_stock_price(100.0)
        report = make_report(ebit=0)
        rv = compute_raw_valuation(price, report)

        assert rv.market_cap is not None
        assert rv.ev_ebit is None  # division by zero
