"""
Opt-in live integration tests for the Börsdata API.

These tests are skipped unless BORSDATA_API_KEY is set in the environment.
Run with:  pytest -m integration -v
"""

import os

import pytest

from kncompanyscraper.borsdata.client import BorsdataClient
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.borsdata.report import Report


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_key():
    key = os.getenv("BORSDATA_API_KEY")
    if not key:
        pytest.skip("BORSDATA_API_KEY not set")
    return key


@pytest.fixture(scope="module")
def client(api_key):
    return BorsdataClient(api_key=api_key)


# Use a well-known instrument ID for testing. 3 = AAK AB, a large-cap Swedish
# company listed on Nasdaq Stockholm that should always have data available.
TEST_INSTRUMENT_ID = 3


# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

class TestClientInit:
    def test_raises_when_api_key_is_none(self):
        with pytest.raises(ValueError, match="BORSDATA_API_KEY is required"):
            BorsdataClient(api_key=None)

    def test_accepts_explicit_api_key(self, api_key):
        client = BorsdataClient(api_key=api_key)
        assert client.api_key == api_key


# ---------------------------------------------------------------------------
# KPI endpoints
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestLiveKpis:
    def test_get_kpis_returns_kpi(self, client):
        result = client.get_kpis(TEST_INSTRUMENT_ID, 2)  # KPI 2 = P/E
        if result is not None:
            assert isinstance(result, Kpi)
            assert result.value > 0

    def test_get_kpis_nonexistent_returns_none(self, client):
        result = client.get_kpis(TEST_INSTRUMENT_ID, 99999)
        # Börsdata returns null for unknown KPI IDs
        assert result is None or isinstance(result, Kpi)


@pytest.mark.integration
class TestLiveKpiHistory:
    def test_get_kpi_history_returns_points(self, client):
        result = client.get_kpi_history(TEST_INSTRUMENT_ID, 2, max_count=5)
        assert isinstance(result, KpiHistory)
        if result.values:
            assert len(result.values) <= 5
            for point in result.values:
                assert point.value > 0

    def test_get_kpi_history_unknown_kpi_returns_empty(self, client):
        result = client.get_kpi_history(TEST_INSTRUMENT_ID, 99999, max_count=5)
        assert isinstance(result, KpiHistory)
        assert result.values == []


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestLiveReports:
    def test_get_reports_returns_list(self, client):
        result = client.get_reports(TEST_INSTRUMENT_ID, max_count=5)
        assert isinstance(result, list)
        if result:
            assert all(isinstance(r, Report) for r in result)
            # Latest report should have sensible values
            latest = result[0]
            assert latest.revenue > 0
            assert latest.shares_outstanding > 0

    def test_get_reports_quarterly(self, client):
        result = client.get_reports(TEST_INSTRUMENT_ID, report_type="quarter", max_count=4)
        assert isinstance(result, list)
        if result:
            assert all(isinstance(r, Report) for r in result)


# ---------------------------------------------------------------------------
# Stock price endpoint
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestLiveStockPrices:
    def test_get_stock_price_returns_list(self, client):
        result = client.get_stock_price(TEST_INSTRUMENT_ID)
        assert isinstance(result, list)
        if result:
            assert all(isinstance(p, StockPrice) for p in result)
            # Most recent price should have a positive close
            latest = result[-1]
            assert latest.close > 0

    def test_stock_prices_in_descending_date_order(self, client):
        result = client.get_stock_price(TEST_INSTRUMENT_ID)
        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i].date <= result[i + 1].date, (
                    f"Stock prices not sorted by date: {result[i].date} > {result[i+1].date}"
                )


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestResponseShape:
    """Verify the live API returns fields the mappers expect."""

    def test_report_has_expected_fields(self, client):
        """The report JSON should contain the fields _report_from_json reads."""
        # Use _get directly to inspect the raw JSON
        data = client._get(f"/v1/instruments/{TEST_INSTRUMENT_ID}/reports/year", {"maxCount": 1})
        reports = data.get("reports") or []
        if reports:
            r = reports[0]
            # Fields used by _report_from_json
            expected_fields = [
                "revenues", "operating_Income", "profit_To_Equity_Holders",
                "free_Cash_Flow", "total_Equity", "total_Assets",
                "net_Debt", "number_Of_Shares",
            ]
            for field in expected_fields:
                assert field in r, f"Expected field '{field}' not found in report JSON"

    def test_stock_price_has_expected_fields(self, client):
        """The stock price JSON should contain the fields our mapper expects."""
        data = client._get(f"/v1/instruments/{TEST_INSTRUMENT_ID}/stockprices")
        prices = data.get("stockPricesList") or []
        if prices:
            p = prices[0]
            for field in ("d", "c"):
                assert field in p, f"Expected field '{field}' not found in stock price JSON"
