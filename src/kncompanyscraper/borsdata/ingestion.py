from datetime import date

from kncompanyscraper.borsdata.report import InstrumentReportBundle
from kncompanyscraper.repositories.valuation_repository import ValuationRepository
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.constants import BORSDATA_DIVIDEND_SOURCE


class BorsdataIngestionService:

    DIVIDEND_SOURCE = BORSDATA_DIVIDEND_SOURCE

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

    def sync_company(self, company, report_bundle: InstrumentReportBundle | None = None) -> None:
        if company.id is None or company.borsdata_id is None:
            raise ValueError("Company must have both id and borsdata_id before Börsdata sync")

        if report_bundle is None:
            report_bundle = self.get_report_bundles([company.borsdata_id])[company.borsdata_id]
        self.sync_reports(company, report_bundle)

        stock_prices = self.client.get_stock_price(company.borsdata_id)
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
            kpi = self.client.get_kpis(company.borsdata_id, kpi_id)
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
