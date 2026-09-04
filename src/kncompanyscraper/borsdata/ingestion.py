from datetime import date

import requests

from kncompanyscraper.borsdata.report import InstrumentReportBundle
from kncompanyscraper.repositories.valuation_repository import ValuationRepository
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.constants import BORSDATA_DIVIDEND_SOURCE
from kncompanyscraper.logger import get_logger


logger = get_logger(__name__)


class BorsdataIngestionService:

    DIVIDEND_SOURCE = BORSDATA_DIVIDEND_SOURCE
    TARGETED_PRICE_MAX_COUNT = 130

    def __init__(
        self,
        client,
        financial_repository,
        valuation_repository,
        dividend_repository,
    ):
        self.client = client
        self.financial_repository = financial_repository
        self.valuation_repository = valuation_repository
        self.dividend_repository = dividend_repository

    def get_report_bundles(self, instrument_ids):
        return self.client.get_report_bundles(instrument_ids)

    def refresh_reports(self, companies: list) -> dict:
        """Refresh reports for exactly the supplied companies."""
        companies = list(companies)
        self._validate_companies(companies)
        refreshed = {}
        for offset in range(0, len(companies), 50):
            batch = companies[offset : offset + 50]
            bundles = self.get_report_bundles([company.borsdata_id for company in batch])
            for company in batch:
                bundle = bundles.get(company.borsdata_id)
                if bundle is None:
                    raise ValueError(
                        "Börsdata report response omitted instrument "
                        f"{company.borsdata_id}"
                    )
                self.sync_reports(company, bundle)
                refreshed[company.id] = bundle
        return refreshed

    def refresh_prices(
        self,
        companies: list,
        *,
        max_count: int = TARGETED_PRICE_MAX_COUNT,
    ) -> dict[int, int]:
        """Refresh only the bounded mutable price window for each company."""
        self._validate_companies(companies)
        return {
            company.id: self.sync_prices(company, max_count=max_count)
            for company in companies
        }

    def refresh_dividends(self, companies: list, *, as_of: date | None = None) -> dict[int, int]:
        """Refresh dividend coverage for exactly the supplied companies."""
        self._validate_companies(companies)
        return {
            company.id: self.sync_dividends(company, as_of=as_of)
            for company in companies
        }

    def refresh_kpis(self, companies: list) -> dict[int, int]:
        """Refresh current and historical KPI inputs for supplied companies."""
        self._validate_companies(companies)
        return {company.id: self.sync_kpis(company) for company in companies}

    def sync_reports(self, company, bundle: InstrumentReportBundle) -> None:
        if company.id is None or company.borsdata_id is None:
            raise ValueError("Company must have both id and borsdata_id before Börsdata sync")
        if bundle.instrument_id != company.borsdata_id:
            raise ValueError(
                "Börsdata report bundle does not match company instrument "
                f"{company.borsdata_id}"
            )
        if bundle.error:
            raise ValueError(
                f"Börsdata report sync failed for instrument {bundle.instrument_id}: "
                f"{bundle.error}"
            )
        self.financial_repository.save_report_bundle(company.id, bundle)

    def sync_company(
        self,
        company,
        report_bundle: InstrumentReportBundle | None = None,
        *,
        price_max_count: int | None = None,
    ) -> None:
        if company.id is None or company.borsdata_id is None:
            raise ValueError("Company must have both id and borsdata_id before Börsdata sync")
        if report_bundle is None:
            raise ValueError("Börsdata report bundle is required before company sync")

        self.sync_reports(company, report_bundle)

        if price_max_count is None:
            stock_prices = self.client.get_stock_price(company.borsdata_id)
        else:
            stock_prices = self.client.get_stock_price(
                company.borsdata_id, max_count=price_max_count
            )
        self.valuation_repository.save_stock_prices(
            company.id, stock_prices, company.listing_currency
        )
        dividends_by_instrument = self.client.get_dividends([company.borsdata_id])
        if company.borsdata_id not in dividends_by_instrument:
            raise ValueError(
                "Börsdata dividend calendar omitted requested instrument "
                f"{company.borsdata_id}"
            )
        dividends = dividends_by_instrument[company.borsdata_id]
        price_bounds = self.valuation_repository.get_stock_price_bounds(company.id)
        if price_bounds:
            covered_from, _ = price_bounds
            covered_through = date.today()
            if covered_from <= covered_through:
                self.dividend_repository.replace_calendar(
                    company.id,
                    dividends,
                    covered_from=covered_from,
                    covered_through=covered_through,
                    source=self.DIVIDEND_SOURCE,
                )

        for kpi_id in ValuationRepository.CURRENT_KPIS:
            kpi = self.client.get_kpis(company.borsdata_id, kpi_id)
            if kpi is not None:
                self.valuation_repository.save_snapshot(company.id, kpi_id, kpi.value)

        sector_kpis = ()
        if company.branch_id == 75:
            sector_kpis = KpiIds.PROPERTY_KPIS
        elif company.branch_id in (68, 69, 70):
            sector_kpis = KpiIds.BANK_KPIS

        for kpi_id in sector_kpis:
            kpi = self._get_sector_kpi(company, kpi_id)
            if kpi is not None:
                self.valuation_repository.save_snapshot(company.id, kpi_id, kpi.value)

        for kpi_id in ValuationRepository.HISTORICAL_KPIS:
            history = self.client.get_kpi_history(
                company.borsdata_id,
                kpi_id,
                report_type="year",
                price_type="mean",
            )
            self.valuation_repository.save_history(company.id, history)
        self.sync_general_fundamental_history(company)

    def sync_prices(self, company, *, max_count: int = TARGETED_PRICE_MAX_COUNT) -> int:
        """Fetch and persist the targeted mutable price window."""
        self._validate_companies([company])
        prices = self.client.get_stock_price(company.borsdata_id, max_count=max_count)
        self.valuation_repository.save_stock_prices(
            company.id, prices, company.listing_currency
        )
        return len(prices)

    def sync_dividends(self, company, *, as_of: date | None = None) -> int:
        """Fetch and persist the current dividend calendar for one company."""
        self._validate_companies([company])
        calendars = self.client.get_dividends([company.borsdata_id])
        if company.borsdata_id not in calendars:
            raise ValueError(
                "Börsdata dividend calendar omitted requested instrument "
                f"{company.borsdata_id}"
            )
        bounds = self.valuation_repository.get_stock_price_bounds(company.id)
        if bounds is None:
            raise ValueError("no stored stock-price history")
        covered_from, _ = bounds
        dividends = calendars[company.borsdata_id]
        self.dividend_repository.replace_calendar(
            company.id,
            dividends,
            covered_from=covered_from,
            covered_through=as_of or date.today(),
            source=self.DIVIDEND_SOURCE,
        )
        return len(dividends)

    def sync_kpis(self, company) -> int:
        """Fetch and persist all current and historical KPI inputs."""
        self._validate_companies([company])
        saved = 0
        sector_kpis = ()
        if company.branch_id == 75:
            sector_kpis = KpiIds.PROPERTY_KPIS
        elif company.branch_id in (68, 69, 70):
            sector_kpis = KpiIds.BANK_KPIS

        for kpi_id in ValuationRepository.CURRENT_KPIS:
            kpi = self.client.get_kpis(company.borsdata_id, kpi_id)
            if kpi is not None:
                self.valuation_repository.save_snapshot(company.id, kpi_id, kpi.value)
                saved += 1

        for kpi_id in sector_kpis:
            kpi = self._get_sector_kpi(company, kpi_id)
            if kpi is not None:
                self.valuation_repository.save_snapshot(company.id, kpi_id, kpi.value)
                saved += 1

        for kpi_id in ValuationRepository.HISTORICAL_KPIS:
            history = self.client.get_kpi_history(
                company.borsdata_id,
                kpi_id,
                report_type="year",
                price_type="mean",
            )
            self.valuation_repository.save_history(company.id, history)

        for kpi_id in KpiIds.GENERAL_FUNDAMENTAL_KPIS:
            history = self.client.get_kpi_history(
                company.borsdata_id,
                kpi_id,
                report_type="year",
                price_type="mean",
            )
            self.valuation_repository.save_history(company.id, history)
        return saved

    def _get_sector_kpi(self, company, kpi_id):
        """Return None when a known sector KPI is unavailable for one instrument."""
        try:
            return self.client.get_kpis(company.borsdata_id, kpi_id)
        except requests.HTTPError as exc:
            response = exc.response
            if response is None or response.status_code != 400:
                raise
            logger.info(
                "Börsdata sector KPI unavailable: instrument=%s kpi=%s",
                company.borsdata_id,
                kpi_id,
            )
            return None

    def sync_general_fundamental_history(self, company) -> None:
        """Backfill annual point-in-time inputs used by the general ranking."""
        if company.id is None or company.borsdata_id is None:
            raise ValueError("Company must have both id and borsdata_id before Börsdata sync")
        for kpi_id in KpiIds.GENERAL_FUNDAMENTAL_KPIS:
            history = self.client.get_kpi_history(
                company.borsdata_id,
                kpi_id,
                report_type="year",
                price_type="mean",
            )
            self.valuation_repository.save_history(company.id, history)

    @staticmethod
    def _validate_companies(companies) -> None:
        seen = set()
        for company in companies:
            if company.id is None or company.borsdata_id is None:
                raise ValueError(
                    "Company must have both id and borsdata_id before Börsdata sync"
                )
            if company.id in seen:
                raise ValueError(f"Duplicate company ID: {company.id}")
            seen.add(company.id)

    def sync_companies(self, companies: list) -> int:
        synced = 0
        for company in companies:
            try:
                self.sync_company(company)
            except Exception:
                logger.exception(
                    "Börsdata sync failed for %s; continuing with next company",
                    company.name,
                )
                continue
            synced += 1
        return synced
