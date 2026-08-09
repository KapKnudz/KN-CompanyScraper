from datetime import date, timedelta

from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.database import get_connection


class FinancialRepository:

    def save_reports(self, company_id: int, period_type: str, reports: list[Report]) -> None:
        query = """
            INSERT INTO financials (
                company_id, period_type, period_end, revenue, operating_profit,
                ebit, ebitda, net_income, debt, equity, free_cash_flow,
                shares_outstanding, total_assets, report_year, report_period,
                currency, raw_payload, gross_income, operating_cash_flow,
                fetched_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (company_id, period_type, period_end)
            DO UPDATE SET
                revenue = EXCLUDED.revenue,
                operating_profit = EXCLUDED.operating_profit,
                ebit = EXCLUDED.ebit,
                ebitda = EXCLUDED.ebitda,
                net_income = EXCLUDED.net_income,
                debt = EXCLUDED.debt,
                equity = EXCLUDED.equity,
                free_cash_flow = EXCLUDED.free_cash_flow,
                shares_outstanding = EXCLUDED.shares_outstanding,
                total_assets = EXCLUDED.total_assets,
                report_year = EXCLUDED.report_year,
                report_period = EXCLUDED.report_period,
                currency = EXCLUDED.currency,
                raw_payload = EXCLUDED.raw_payload,
                gross_income = EXCLUDED.gross_income,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                fetched_at = NOW()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                for report in reports:
                    period_end = report.period_end or date(report.year, 12, 31)
                    cur.execute(
                        query,
                        (
                            company_id, period_type, period_end, report.revenue,
                            report.operating_profit, report.ebit, report.ebitda,
                            report.net_income, report.total_debt, report.equity,
                            report.free_cash_flow, report.shares_outstanding,
                            report.total_assets, report.year, report.period,
                            report.currency, Json(report.raw_payload),
                            report.gross_income, report.operating_cash_flow,
                        ),
                    )

    def get_latest_report(self, company_id: int, period_type: str = "year") -> Report | None:
        reports = self._get_reports(company_id, period_type, limit=1)
        return reports[0] if reports else None

    def get_latest_report_as_of(
        self,
        company_id: int,
        period_type: str = "year",
        as_of: date | None = None,
        availability_lag_days: int = 0,
    ) -> Report | None:
        """Return the latest report estimated to be public by *as_of*."""
        if as_of is None:
            return self.get_latest_report(company_id, period_type)
        reports = self.get_reports_as_of(
            company_id,
            period_type,
            as_of,
            availability_lag_days=availability_lag_days,
        )
        return reports[0] if reports else None

    def get_reports_as_of(
        self,
        company_id: int,
        period_type: str,
        as_of: date,
        availability_lag_days: int = 0,
    ) -> list[Report]:
        """Return reports whose period end plus the configured lag is available."""
        reports = self._get_reports(company_id, period_type)
        return [
            report
            for report in reports
            if report.period_end
            and report.period_end + timedelta(days=availability_lag_days) <= as_of
        ]

    def get_historical_reports(self, company_id: int, period_type: str = "year") -> list[Report]:
        reports = self._get_reports(company_id, period_type)
        return list(reversed(reports[1:]))

    def _get_reports(
        self,
        company_id: int,
        period_type: str,
        limit: int | None = None,
    ) -> list[Report]:
        query = """
            SELECT revenue, operating_profit, ebit, ebitda, net_income,
                   free_cash_flow, equity, total_assets, debt,
                   shares_outstanding, report_year, report_period, period_end,
                   currency, raw_payload, gross_income, operating_cash_flow
            FROM financials
            WHERE company_id = %s AND period_type = %s
            ORDER BY period_end DESC
        """
        params: list = [company_id, period_type]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        return [
            Report(
                revenue=self._to_float(row["revenue"]),
                operating_profit=self._to_float(row["operating_profit"]),
                ebit=self._to_float(row["ebit"]),
                ebitda=self._to_float(row["ebitda"]),
                net_income=self._to_float(row["net_income"]),
                free_cash_flow=self._to_float(row["free_cash_flow"]),
                equity=self._to_float(row["equity"]),
                total_assets=self._to_float(row["total_assets"]),
                total_debt=self._to_float(row["debt"]),
                shares_outstanding=self._to_float(row["shares_outstanding"]),
                gross_income=self._to_float(row["gross_income"]),
                operating_cash_flow=self._to_float(row["operating_cash_flow"]),
                year=row["report_year"],
                period=row["report_period"],
                period_end=row["period_end"],
                currency=row["currency"],
                raw_payload=row["raw_payload"],
            )
            for row in rows
        ]

    @staticmethod
    def _to_float(value) -> float | None:
        return float(value) if value is not None else None
