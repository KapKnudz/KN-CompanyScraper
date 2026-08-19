import random
import time
import requests
from datetime import date, datetime

from kncompanyscraper import config
from kncompanyscraper.logger import get_logger
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory, KpiHistoryPoint
from kncompanyscraper.borsdata.instrument import Instrument
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.borsdata.dividend import CashDividend
from kncompanyscraper.models.insider_transaction import InsiderTransaction

logger = get_logger(__name__)


class BorsdataClient:

    BASE_URL = "https://apiservice.borsdata.se"
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 1.0  # seconds — doubles each retry

    def __init__(self, api_key=None):
        self.api_key = api_key or config.BORSDATA_API_KEY
        if not self.api_key:
            raise ValueError(
                "BORSDATA_API_KEY is required. "
                "Set the BORSDATA_API_KEY environment variable or pass api_key= to BorsdataClient()."
            )

    def get_kpis(self, instrument_id, kpi_id, calc_group="last", calc="latest"):
        data = self._get(f"/v1/instruments/{instrument_id}/kpis/{kpi_id}/{calc_group}/{calc}")

        value = data.get("value") or {}
        n = value.get("n")
        if n is None:
            return None

        return Kpi(id=kpi_id, name=str(kpi_id), value=n)

    def get_instruments(self) -> list[Instrument]:
        data = self._get("/v1/instruments")
        return [
            Instrument(
                id=item["insId"],
                name=item.get("name"),
                isin=item.get("isin"),
                ticker=item.get("ticker"),
                stock_price_currency=item.get("stockPriceCurrency"),
                report_currency=item.get("reportCurrency"),
                sector_id=item.get("sectorId"),
                branch_id=item.get("branchId"),
            )
            for item in data.get("instruments") or []
        ]

    def get_kpi_history(self, instrument_id, kpi_id, report_type="year", price_type="mean", max_count=20):
        data = self._get(
            f"/v1/instruments/{instrument_id}/kpis/{kpi_id}/{report_type}/{price_type}/history",
            {"maxCount": max_count},
        )

        points = [
            KpiHistoryPoint(
                year=point["y"],
                value=point["v"],
                period=point.get("p"),
            )
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

    def get_stock_price(self, instrument_id, max_count=None):
        params = {"maxCount": max_count} if max_count is not None else None
        data = self._get(f"/v1/instruments/{instrument_id}/stockprices", params)

        return [
            StockPrice(date=date.fromisoformat(p["d"][:10]), close=p["c"])
            for p in data.get("stockPricesList") or []
        ]

    def get_dividends(
        self,
        instrument_ids: list[int],
    ) -> dict[int, list[CashDividend]]:
        if not instrument_ids:
            return {}
        if len(instrument_ids) > 50:
            raise ValueError("Börsdata dividend endpoint accepts at most 50 instruments")

        data = self._get(
            "/v1/instruments/dividend/calendar",
            {"instList": ",".join(str(value) for value in instrument_ids)},
        )
        result = {}
        for instrument in data.get("list") or []:
            instrument_id = instrument.get("insId")
            if instrument_id not in instrument_ids:
                continue
            result[instrument_id] = []
            for row in instrument.get("values") or []:
                ex_date = row.get("excludingDate")
                amount = row.get("amountPaid")
                currency = row.get("currencyShortName")
                dividend_type = row.get("dividendType")
                if not ex_date:
                    raise ValueError(
                        f"Börsdata dividend row has no ex-date for instrument {instrument_id}"
                    )
                parsed_date = date.fromisoformat(ex_date[:10])
                if amount == 0 and currency:
                    # Börsdata emits dated zero rows for explicit no-distribution
                    # decisions. They certify the calendar but are not cash flows.
                    continue
                if amount is None or amount < 0 or not currency:
                    if parsed_date <= date.today():
                        raise ValueError(
                            "Börsdata historical dividend row is incomplete for "
                            f"instrument {instrument_id} on {parsed_date}"
                        )
                    continue
                result[instrument_id].append(
                    CashDividend(
                        ex_date=parsed_date,
                        amount=float(amount),
                        currency=currency.upper(),
                        dividend_type=int(dividend_type or 0),
                        distribution_frequency=row.get("distributionFrequency"),
                    )
                )
        return result

    def get_insider_transactions(
        self,
        instrument_ids: list[int],
    ) -> dict[int, list[InsiderTransaction]]:
        if not instrument_ids:
            return {}
        if len(instrument_ids) > 50:
            raise ValueError("Börsdata insider endpoint accepts at most 50 instruments")

        data = self._get(
            "/v1/holdings/insider",
            {"instList": ",".join(str(instrument_id) for instrument_id in instrument_ids)},
        )
        transactions_by_instrument = {instrument_id: [] for instrument_id in instrument_ids}

        for instrument in data.get("list") or []:
            instrument_id = instrument.get("insId")
            if instrument_id not in transactions_by_instrument:
                continue

            for row in instrument.get("values") or []:
                transaction_type = {19: "buy", 25: "sell"}.get(row.get("transactionType"))
                transaction_date = row.get("transactionDate")
                if (
                    transaction_type is None
                    or row.get("misc")
                    or row.get("equityProgram")
                    or not transaction_date
                    or not row.get("ownerName")
                ):
                    continue

                transactions_by_instrument[instrument_id].append(
                    InsiderTransaction(
                        person_name=row["ownerName"],
                        person_role=row.get("ownerPosition"),
                        transaction_type=transaction_type,
                        shares=abs(row.get("shares") or 0),
                        price_per_share=abs(row["price"]) if row.get("price") is not None else None,
                        total_value=abs(row["amount"]) if row.get("amount") is not None else None,
                        transaction_date=date.fromisoformat(transaction_date[:10]),
                        source=f"borsdata:{row['transactionType']}",
                        reported_at=(
                            datetime.fromisoformat(row["verificationDate"])
                            if row.get("verificationDate")
                            else None
                        ),
                        currency=row.get("currency"),
                    )
                )

        return transactions_by_instrument

    def _report_from_json(self, r):
        return Report(
            revenue=r.get("revenues"),
            operating_profit=r.get("operating_Income"),
            ebit=r.get("operating_Income"),
            ebitda=None,
            net_income=r.get("profit_To_Equity_Holders"),
            free_cash_flow=r.get("free_Cash_Flow"),
            equity=r.get("total_Equity"),
            total_assets=r.get("total_Assets"),
            total_debt=r.get("net_Debt"),
            shares_outstanding=r.get("number_Of_Shares"),
            gross_income=r.get("gross_Income"),
            operating_cash_flow=r.get("cash_Flow_From_Operating_Activities"),
            investing_cash_flow=r.get("cash_Flow_From_Investing_Activities"),
            year=r.get("year"),
            period=r.get("period"),
            period_end=(
                date.fromisoformat(r["report_End_Date"][:10])
                if r.get("report_End_Date")
                else None
            ),
            currency=r.get("currency"),
            raw_payload=r,
        )

    def _get(self, path, params=None):
        params = dict(params or {})
        params["authKey"] = self.api_key

        url = f"{self.BASE_URL}{path}"

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(url, params=params, timeout=20)
            except requests.exceptions.Timeout:
                if attempt < self.MAX_RETRIES - 1:
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Börsdata timeout on %s, retrying in %.1fs (attempt %d/%d)",
                        path, wait, attempt + 1, self.MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Börsdata timeout on %s after %d attempts", path, self.MAX_RETRIES)
                raise requests.exceptions.Timeout(
                    f"Börsdata request timed out: {path}"
                ) from None
            except requests.exceptions.ConnectionError:
                if attempt < self.MAX_RETRIES - 1:
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Börsdata connection error on %s, retrying in %.1fs (attempt %d/%d)",
                        path, wait, attempt + 1, self.MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Börsdata connection error on %s after %d attempts", path, self.MAX_RETRIES)
                raise requests.exceptions.ConnectionError(
                    f"Börsdata connection error: {path}"
                ) from None

            # Rate limiting — honour Retry-After if present, else exponential backoff
            if response.status_code == 429:
                if attempt < self.MAX_RETRIES - 1:
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else self._backoff(attempt)
                    logger.warning(
                        "Börsdata rate limited (429) on %s, waiting %.1fs (attempt %d/%d)",
                        path, wait, attempt + 1, self.MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Börsdata rate limited (429) on %s after %d attempts", path, self.MAX_RETRIES)

            # Transient server errors
            if response.status_code >= 500:
                if attempt < self.MAX_RETRIES - 1:
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Börsdata server error (%d) on %s, retrying in %.1fs (attempt %d/%d)",
                        response.status_code, path, wait, attempt + 1, self.MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    "Börsdata server error (%d) on %s after %d attempts",
                    response.status_code, path, self.MAX_RETRIES,
                )

            if response.status_code >= 400:
                # requests includes the full query string in HTTPError messages.
                # Börsdata authenticates via query parameter, so strip it before
                # raising to keep the API key out of logs and tracebacks.
                response.url = url
                response.raise_for_status()
            logger.debug("Börsdata %s → 200", path)
            return response.json()

        raise RuntimeError(f"Börsdata request exhausted retries: {path}")

    def _backoff(self, attempt):
        """Exponential backoff with jitter: ~1s, ~2s, ~4s."""
        return self.RETRY_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.5)
