import json
from pathlib import Path

import pytest

from kncompanyscraper.borsdata.client import BorsdataClient
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.borsdata.report import Report

MOCKS_DIR = Path(__file__).resolve().parent / "mocks"


def load_mock(filename):
    with open(MOCKS_DIR / filename) as f:
        return json.load(f)


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class TestBorsdataClient:

    def test_init_raises_when_no_api_key(self, monkeypatch):
        """BorsdataClient raises ValueError when no API key is provided."""
        monkeypatch.setattr("kncompanyscraper.borsdata.client.config.BORSDATA_API_KEY", None)
        with pytest.raises(ValueError, match="BORSDATA_API_KEY is required"):
            BorsdataClient(api_key=None)

    def test_get_kpis_maps_value(self, monkeypatch):
        payload = load_mock("kpi_screener_mock.json")
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: FakeResponse(payload),
        )

        client = BorsdataClient(api_key="test")
        result = client.get_kpis(3, 2)

        assert isinstance(result, Kpi)
        assert result.value == pytest.approx(18.50)

    def test_get_kpi_history_maps_points(self, monkeypatch):
        payload = load_mock("kpi_history_mock.json")["pe_history"]
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: FakeResponse(payload),
        )

        client = BorsdataClient(api_key="test")
        result = client.get_kpi_history(3, 2)

        assert isinstance(result, KpiHistory)
        assert [p.value for p in result.values] == [12.50, 14.20, 16.80, 15.90, 18.50]

    def test_get_reports_maps_reports(self, monkeypatch):
        payload = load_mock("reports_mock.json")
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: FakeResponse(payload),
        )

        client = BorsdataClient(api_key="test")
        result = client.get_reports(3)

        assert len(result) == 5
        assert all(isinstance(r, Report) for r in result)
        assert result[-1].revenue == 550_000_000

    def test_get_stock_price_maps_prices(self, monkeypatch):
        payload = load_mock("stock_prices_mock.json")
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: FakeResponse(payload),
        )

        client = BorsdataClient(api_key="test")
        result = client.get_stock_price(3)

        assert len(result) == 5
        assert all(isinstance(p, StockPrice) for p in result)
        assert result[0].close == pytest.approx(278.0)