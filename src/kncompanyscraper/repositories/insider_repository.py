from datetime import date
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from kncompanyscraper.database import get_connection
from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.insider_transaction import InsiderTransaction

logger = get_logger(__name__)


def _row_to_transaction(row: dict) -> InsiderTransaction:
    """Convert a RealDictCursor row to an InsiderTransaction."""
    return InsiderTransaction(
        person_name=row["person_name"],
        person_role=row["person_role"],
        transaction_type=row["transaction_type"],
        shares=row["shares"],
        price_per_share=float(row["price_per_share"]) if row["price_per_share"] is not None else None,
        total_value=float(row["total_value"]) if row["total_value"] is not None else None,
        transaction_date=row["transaction_date"],
        source=row["source"],
        reported_at=row.get("reported_at"),
        currency=row.get("currency"),
    )


class InsiderRepository:

    def save(self, transaction: InsiderTransaction, company_id: int) -> bool:
        """Insert an insider transaction unless it has already been stored."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                self._insert(cur, transaction, company_id)
                inserted = cur.rowcount == 1

        if inserted:
            logger.info(
                "Saved insider transaction: %s %s %s shares of company_id=%s",
                transaction.person_name,
                transaction.transaction_type,
                transaction.shares,
                company_id,
            )
        return inserted

    def save_all(
        self,
        transactions: list[InsiderTransaction],
        company_id: int,
    ) -> int:
        inserted = 0
        with get_connection() as conn:
            with conn.cursor() as cur:
                for transaction in transactions:
                    self._insert(cur, transaction, company_id)
                    inserted += cur.rowcount
        return inserted

    @staticmethod
    def _insert(cur, transaction: InsiderTransaction, company_id: int) -> None:
        cur.execute(
            """
            INSERT INTO insider_transactions
                (company_id, person_name, person_role, transaction_type,
                 shares, price_per_share, total_value, transaction_date,
                 source, reported_at, currency)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), %s)
            ON CONFLICT DO NOTHING
            """,
            (
                company_id,
                transaction.person_name,
                transaction.person_role,
                transaction.transaction_type,
                transaction.shares,
                transaction.price_per_share,
                transaction.total_value,
                transaction.transaction_date,
                transaction.source,
                transaction.reported_at,
                transaction.currency,
            ),
        )

    def list_for_company(
        self,
        company_id: int,
        since: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> List[InsiderTransaction]:
        """Return transactions for a company, ordered by date descending.

        Optionally filter to transactions on or after `since` and/or cap the
        result count with `limit`.
        """
        query = """
            SELECT person_name, person_role, transaction_type,
                   shares, price_per_share, total_value, transaction_date,
                   source, reported_at, currency
            FROM insider_transactions
            WHERE company_id = %s
        """
        params: list = [company_id]

        if since is not None:
            query += " AND transaction_date >= %s"
            params.append(since)

        query += " ORDER BY transaction_date DESC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        return [_row_to_transaction(row) for row in rows]

    def get_recent_for_company(
        self,
        company_id: int,
        limit: int = 20,
    ) -> List[InsiderTransaction]:
        """Return the most recent transactions for a company."""
        return self.list_for_company(company_id, limit=limit)
