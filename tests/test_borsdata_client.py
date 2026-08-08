import json
from pathlib import Path

import pytest
import requests

from kncompanyscraper.borsdata.client import BorsdataClient
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.instrument import Instrument

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

    def test_get_instruments_maps_identity_fields(self, monkeypatch):
        payload = {
            "instruments": [
                {
                    "insId": 42,
                    "name": "Testbolaget",
                    "isin": "SE0000000042",
                    "ticker": "TEST",
                    "stockPriceCurrency": "SEK",
                    "reportCurrency": "SEK",
                    "sectorId": 1,
                    "branchId": 75,
                }
            ]
        }
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: FakeResponse(payload),
        )

        result = BorsdataClient(api_key="test").get_instruments()

        assert result == [
            Instrument(42, "Testbolaget", "SE0000000042", "TEST", "SEK", "SEK", 1, 75)
        ]

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
        assert [p.period for p in result.values] == [1, 1, 1, 1, 1]

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

    def test_report_mapping_preserves_missing_values_without_fabricating_ebitda(self):
        report = BorsdataClient(api_key="test")._report_from_json(
            {
                "year": 2025,
                "period": 1,
                "operating_Income": 12.0,
                "intangible_Assets": 500.0,
            }
        )

        assert report.ebit == 12.0
        assert report.ebitda is None
        assert report.revenue is None
        assert report.net_income is None
        assert report.total_debt is None

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

    def test_get_insider_transactions_keeps_only_open_market_buys_and_sells(self, monkeypatch):
        payload = {
            "list": [
                {
                    "insId": 3,
                    "values": [
                        {
                            "misc": False,
                            "ownerName": "Buyer",
                            "ownerPosition": "board member",
                            "equityProgram": False,
                            "shares": 100,
                            "price": 25.0,
                            "amount": 2500.0,
                            "currency": "SEK",
                            "transactionType": 19,
                            "verificationDate": "2026-08-02T10:00:00",
                            "transactionDate": "2026-08-01T00:00:00",
                        },
                        {
                            "misc": False,
                            "ownerName": "Seller",
                            "ownerPosition": "ceo",
                            "equityProgram": False,
                            "shares": -50,
                            "price": 30.0,
                            "amount": -1500.0,
                            "currency": "SEK",
                            "transactionType": 25,
                            "verificationDate": "2026-08-03T10:00:00",
                            "transactionDate": "2026-08-02T00:00:00",
                        },
                        {
                            "misc": True,
                            "ownerName": "Transfer",
                            "equityProgram": False,
                            "transactionType": 19,
                            "transactionDate": "2026-08-01T00:00:00",
                        },
                        {
                            "misc": False,
                            "ownerName": "Grant",
                            "equityProgram": True,
                            "transactionType": 19,
                            "transactionDate": "2026-08-01T00:00:00",
                        },
                    ],
                }
            ]
        }
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: FakeResponse(payload),
        )

        result = BorsdataClient(api_key="test").get_insider_transactions([3])

        assert [transaction.transaction_type for transaction in result[3]] == ["buy", "sell"]
        assert result[3][1].shares == 50
        assert result[3][1].total_value == 1500.0
        assert result[3][0].currency == "SEK"
        assert result[3][0].source == "borsdata:19"

    def test_get_insider_transactions_rejects_more_than_fifty_instruments(self):
        with pytest.raises(ValueError, match="at most 50"):
            BorsdataClient(api_key="test").get_insider_transactions(list(range(51)))

    def test_http_error_does_not_expose_api_key(self, monkeypatch):
        response = requests.Response()
        response.status_code = 400
        response.reason = "Bad Request"
        response.url = "https://apiservice.borsdata.se/example?authKey=secret"
        monkeypatch.setattr(
            "kncompanyscraper.borsdata.client.requests.get",
            lambda url, params, timeout: response,
        )

        with pytest.raises(requests.HTTPError) as exc_info:
            BorsdataClient(api_key="secret")._get("/example")

        assert "secret" not in str(exc_info.value)
        assert "https://apiservice.borsdata.se/example" in str(exc_info.value)
