from kncompanyscraper.borsdata.client import BorsdataClient
from kncompanyscraper.borsdata.report import Report


class FinancialRepository:

    def __init__(self, client: BorsdataClient):
        self.client = client

    def get_latest_report(self, instrument_id: int) -> Report | None:
        reports = self.client.get_reports(instrument_id)
        if not reports:
            return None
        # Assuming reports are sorted by date descending, or we take the first one
        return reports[0]

    def get_historical_reports(self, instrument_id: int) -> list[Report]:
        reports = self.client.get_reports(instrument_id)
        if not reports or len(reports) < 2:
            return []
        # Return all except the latest one for history
        return reports[1:]
