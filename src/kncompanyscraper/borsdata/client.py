import requests
from datetime import date

from kncompanyscraper import config
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory, KpiHistoryPoint
from kncompanyscraper.borsdata.stock_price import StockPrice


class BorsdataClient:

    BASE_URL = "https://apiservice.borsdata.se"

    def __init__(self, api_key=None):
        self.api_key = api_key or config.BORSDATA_API_KEY

    def get_kpis(self, instrument_id, kpi_id, calc_group="last", calc="latest"):
        data = self._get(f"/v1/instruments/{instrument_id}/kpis/{kpi_id}/{calc_group}/{calc}")

        value = data.get("value") or {}
        n = value.get("n")
        if n is None:
            return None

        return Kpi(id=kpi_id, name=str(kpi_id), value=n)

    def get_kpi_history(self, instrument_id, kpi_id, report_type="year", price_type="mean", max_count=20):
        data = self._get(
            f"/v1/instruments/{instrument_id}/kpis/{kpi_id}/{report_type}/{price_type}/history",
            {"maxCount": max_count},
        )

        points = [
            KpiHistoryPoint(year=point["y"], value=point["v"])
            for point in data.get("values") or []
            if point.get("v") is not None
        ]

        return KpiHistory(kpi_id=kpi_id, values=points)

    def get_reports(self, instrument_id, report_type="year", max_count=20):
        data = self._get(
            f"/v1/instruments/{instrument_id}/reports/{report_type}",
            {"maxCount": max_count},
        )

        return [self._report_from_json(r) for r in data.get("reports") or []]

    def get_stock_price(self, instrument_id):
        data = self._get(f"/v1/instruments/{instrument_id}/stockprices")

        return [
            StockPrice(date=date.fromisoformat(p["d"][:10]), close=p["c"])
            for p in data.get("stockPricesList") or []
        ]

    def _report_from_json(self, r):
        return Report(
            revenue=r.get("revenues") or 0,
            operating_profit=r.get("operating_Income") or 0,
            ebit=r.get("operating_Income") or 0,
            ebitda=(r.get("operating_Income") or 0) + (r.get("intangible_Assets") or 0),
            net_income=r.get("profit_To_Equity_Holders") or 0,
            free_cash_flow=r.get("free_Cash_Flow") or 0,
            equity=r.get("total_Equity") or 0,
            total_assets=r.get("total_Assets") or 0,
            total_debt=r.get("net_Debt") or 0,
            shares_outstanding=r.get("number_Of_Shares") or 0,
        )

    def _get(self, path, params=None):
        params = dict(params or {})
        params["authKey"] = self.api_key

        response = requests.get(f"{self.BASE_URL}{path}", params=params, timeout=20)
        response.raise_for_status()

        return response.json()