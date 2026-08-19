from dataclasses import dataclass
from datetime import date

from psycopg2.extras import RealDictCursor

from kncompanyscraper.borsdata.dividend import CashDividend
from kncompanyscraper.database import get_connection


@dataclass(frozen=True)
class DividendCoverage:
    covered_from: date
    covered_through: date
    source: str


@dataclass(frozen=True)
class DividendEventReview:
    status: str
    reason: str
    evidence_url: str | None


class DividendRepository:
    REVIEW_STATUSES = {"pending", "approved", "excluded"}

    def replace_calendar(
        self,
        company_id: int,
        dividends: list[CashDividend],
        *,
        covered_from: date,
        covered_through: date,
        source: str,
    ) -> None:
        if covered_from > covered_through:
            raise ValueError("covered_from must not be after covered_through")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM company_dividends WHERE company_id = %s AND source = %s",
                    (company_id, source),
                )
                for dividend in dividends:
                    if dividend.amount <= 0:
                        raise ValueError("dividend amount must be positive")
                    cur.execute(
                        """
                        INSERT INTO company_dividends (
                            company_id, ex_date, amount, currency, dividend_type,
                            distribution_frequency, source, fetched_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            company_id,
                            dividend.ex_date,
                            dividend.amount,
                            dividend.currency,
                            dividend.dividend_type,
                            dividend.distribution_frequency,
                            source,
                        ),
                    )
                cur.execute(
                    """
                    INSERT INTO dividend_data_coverage (
                        company_id, covered_from, covered_through, source, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (company_id) DO UPDATE SET
                        covered_from = EXCLUDED.covered_from,
                        covered_through = EXCLUDED.covered_through,
                        source = EXCLUDED.source,
                        fetched_at = NOW()
                    """,
                    (company_id, covered_from, covered_through, source),
                )

    def get_coverage(self, company_id: int) -> DividendCoverage | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT covered_from, covered_through, source
                    FROM dividend_data_coverage
                    WHERE company_id = %s
                    """,
                    (company_id,),
                )
                row = cur.fetchone()
        return DividendCoverage(**row) if row else None

    def get_dividends(
        self,
        company_id: int,
        *,
        after_date: date,
        through_date: date,
    ) -> list[CashDividend]:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ex_date, amount, currency, dividend_type,
                           distribution_frequency
                    FROM company_dividends
                    WHERE company_id = %s
                      AND ex_date > %s
                      AND ex_date <= %s
                    ORDER BY ex_date, id
                    """,
                    (company_id, after_date, through_date),
                )
                rows = cur.fetchall()
        return [
            CashDividend(
                ex_date=row["ex_date"],
                amount=float(row["amount"]),
                currency=row["currency"],
                dividend_type=row["dividend_type"],
                distribution_frequency=row["distribution_frequency"],
            )
            for row in rows
        ]

    def get_reviews(
        self,
        company_id: int,
        *,
        after_date: date,
        through_date: date,
        source: str,
    ) -> dict[tuple, DividendEventReview]:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ex_date, amount, currency, dividend_type,
                           status, reason, evidence_url
                    FROM dividend_event_reviews
                    WHERE company_id = %s
                      AND ex_date > %s
                      AND ex_date <= %s
                      AND source = %s
                    """,
                    (company_id, after_date, through_date, source),
                )
                rows = cur.fetchall()
        return {
            self.review_key(
                row["ex_date"],
                float(row["amount"]),
                row["currency"],
                row["dividend_type"],
            ): DividendEventReview(
                row["status"], row["reason"], row["evidence_url"]
            )
            for row in rows
        }

    def review_events(
        self,
        company_id: int,
        *,
        after_date: date,
        through_date: date,
        status: str,
        reason: str,
        evidence_url: str | None,
        source: str,
    ) -> int:
        if status not in self.REVIEW_STATUSES:
            raise ValueError("unsupported dividend review status")
        if not reason.strip():
            raise ValueError("dividend review reason is required")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dividend_event_reviews (
                        company_id, ex_date, amount, currency, dividend_type,
                        source, status, reason, evidence_url, reviewed_at
                    )
                    SELECT company_id, ex_date, amount, currency, dividend_type,
                           source, %s, %s, %s, NOW()
                    FROM company_dividends
                    WHERE company_id = %s
                      AND ex_date > %s
                      AND ex_date <= %s
                      AND source = %s
                    ON CONFLICT (
                        company_id, ex_date, amount, currency, dividend_type, source
                    ) DO UPDATE SET
                        status = EXCLUDED.status,
                        reason = EXCLUDED.reason,
                        evidence_url = EXCLUDED.evidence_url,
                        reviewed_at = NOW()
                    """,
                    (
                        status,
                        reason.strip(),
                        evidence_url,
                        company_id,
                        after_date,
                        through_date,
                        source,
                    ),
                )
                return cur.rowcount

    @staticmethod
    def review_key(
        ex_date: date,
        amount: float,
        currency: str,
        dividend_type: int,
    ) -> tuple:
        return ex_date, round(amount, 6), currency.upper(), dividend_type
