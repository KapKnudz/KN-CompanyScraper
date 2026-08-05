from kncompanyscraper.repositories.valuation_repository import ValuationRepository


class BorsdataIngestionService:

    def __init__(self, client, financial_repository, valuation_repository):
        self.client = client
        self.financial_repository = financial_repository
        self.valuation_repository = valuation_repository

    def sync_company(self, company) -> None:
        if company.id is None or company.borsdata_id is None:
            raise ValueError("Company must have both id and borsdata_id before Börsdata sync")

        reports = self.client.get_reports(company.borsdata_id, report_type="year")
        self.financial_repository.save_reports(company.id, "year", reports)

        for kpi_id in ValuationRepository.CURRENT_KPIS:
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

    def sync_companies(self, companies: list) -> int:
        synced = 0
        for company in companies:
            self.sync_company(company)
            synced += 1
        return synced
