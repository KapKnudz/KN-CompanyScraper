from kncompanyscraper.borsdata.client import BorsdataClient
from kncompanyscraper.borsdata.report import Report
import psycopg2

class FinancialRepository:
    def __init__(self, client: BorsdataClient, db_connection_string: str):
        self.client = client
        self.db_connection_string = db_connection_string

    def _execute(self, query: str, params: tuple = None):
        """Helper method to execute SQL queries."""
        with psycopg2.connect(self.db_connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                conn.commit()

    def get_latest_report(self, instrument_id: int) -> Report | None:
        reports = self.client.get_reports(instrument_id)
        if not reports:
            return None
        return reports[0]

    def get_historical_reports(self, instrument_id: int) -> list[Report]:
        reports = self.client.get_reports(instrument_id)
        if not reports or len(reports) < 2:
            return []
        return reports[1:]

    def save_report(self, company_id: int, period_type: str, period_end: str, data: dict) -> None:
        """
        Save financial report to PostgreSQL. Uses ON CONFLICT to avoid duplicates.
        """
        query = """
            INSERT INTO financials (company_id, period_type, period_end, data)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (company_id, period_type, period_end)
            DO UPDATE SET data = EXCLUDED.data;
        """
        self._execute(query, (company_id, period_type, period_end, data))