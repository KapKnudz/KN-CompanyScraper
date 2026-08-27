from kncompanyscraper.models.company import Company
from kncompanyscraper.repositories.base_repository import BaseRepository

from kncompanyscraper.watchlist_import import WatchlistCompany


class CompanyRepository(BaseRepository):

    def get_by_id(self, company_id: int) -> Company | None:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT
                id,
                name,
                ticker,
                mfn_slug,
                borsdata_id,
                isin,
                currency,
                stock_price_currency,
                report_currency,
                sector_id,
                branch_id,
                last_updated
                FROM companies
                WHERE id = %s
                """,
                (company_id,),
            )

            row = cur.fetchone()
            return Company(**row) if row else None

    def get_by_ticker(self, ticker: str) -> Company | None:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT
                id,
                name,
                ticker,
                mfn_slug,
                borsdata_id,
                isin,
                currency,
                stock_price_currency,
                report_currency,
                sector_id,
                branch_id,
                last_updated
                FROM companies
                WHERE ticker = %s
                """,
                (ticker,),
            )

            row = cur.fetchone()
            return Company(**row) if row else None

    def create(self, company: Company) -> Company:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (
                    name, ticker, mfn_slug, borsdata_id, isin, currency,
                    stock_price_currency, report_currency, sector_id, branch_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, ticker, mfn_slug, borsdata_id, last_updated,
                          isin, currency, stock_price_currency, report_currency,
                          sector_id, branch_id
                """,
                (
                    company.name,
                    company.ticker,
                    company.mfn_slug,
                    company.borsdata_id,
                    company.isin,
                    company.currency,
                    company.listing_currency,
                    company.report_currency,
                    company.sector_id,
                    company.branch_id,
                ),
            )

            return Company(**cur.fetchone())

    def update(self, company: Company) -> None:
        with self._get_cursor() as cur:
            cur.execute(
                """
                UPDATE companies
                SET name         = %s,
                    ticker       = %s,
                    borsdata_id  = %s,
                    mfn_slug     = %s,
                    isin         = %s,
                    currency     = %s,
                    stock_price_currency = %s,
                    report_currency = %s,
                    sector_id    = %s,
                    branch_id    = %s,
                    last_updated = NOW()
                WHERE id = %s
                """,
                (
                    company.name,
                    company.ticker,
                    company.borsdata_id,
                    company.mfn_slug,
                    company.isin,
                    company.currency,
                    company.listing_currency,
                    company.report_currency,
                    company.sector_id,
                    company.branch_id,
                    company.id,
                ),
            )


    def get_active_companies(self) -> list[Company]:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT c.id,
                       c.name,
                       c.ticker,
                       c.borsdata_id,
                       c.mfn_slug,
                       c.isin,
                       c.currency,
                       c.stock_price_currency,
                       c.report_currency,
                       c.sector_id,
                       c.branch_id,
                       c.last_updated
                FROM companies c
                         JOIN watchlist w
                              ON c.id = w.company_id
                WHERE w.active = TRUE
                ORDER BY c.name
                """
            )

            return [Company(**row) for row in cur.fetchall()]

    def get_backtest_companies(self) -> list[Company]:
        """Return every stored company with price history, including inactive names."""
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT c.id,
                       c.name,
                       c.ticker,
                       c.borsdata_id,
                       c.mfn_slug,
                       c.isin,
                       c.currency,
                       c.stock_price_currency,
                       c.report_currency,
                       c.sector_id,
                       c.branch_id,
                       c.last_updated
                FROM companies c
                WHERE EXISTS (
                    SELECT 1
                    FROM stock_prices sp
                    WHERE sp.company_id = c.id
                )
                ORDER BY c.name
                """
            )
            return [Company(**row) for row in cur.fetchall()]

    def set_borsdata_identity(
        self,
        company_id: int,
        borsdata_id: int,
        stock_price_currency: str | None,
        sector_id: int | None,
        branch_id: int | None,
        report_currency: str | None = None,
    ) -> None:
        with self._get_cursor() as cur:
            cur.execute(
                """
                UPDATE companies
                SET borsdata_id = %s,
                    currency = COALESCE(%s, currency),
                    stock_price_currency = COALESCE(%s, stock_price_currency, currency),
                    report_currency = COALESCE(%s, report_currency),
                    sector_id = %s,
                    branch_id = %s,
                    last_updated = NOW()
                WHERE id = %s
                """,
                (
                    borsdata_id,
                    stock_price_currency,
                    stock_price_currency,
                    report_currency,
                    sector_id,
                    branch_id,
                    company_id,
                ),
            )

    def upsert_watchlist_companies(
        self,
        companies: list[WatchlistCompany],
    ) -> tuple[int, int]:
        created = 0
        updated = 0

        with self._get_cursor() as cur:
            for company in companies:
                cur.execute(
                    "SELECT id FROM companies WHERE borsdata_id = %s",
                    (company.borsdata_id,),
                )
                row = cur.fetchone()

                if row is None:
                    cur.execute(
                        "SELECT id FROM companies WHERE ticker = %s",
                        (company.ticker,),
                    )
                    row = cur.fetchone()

                if row is None:
                    cur.execute(
                        """
                        INSERT INTO companies (name, ticker, borsdata_id, currency)
                        VALUES (%s, %s, %s, NULL)
                        RETURNING id
                        """,
                        (company.name, company.ticker, company.borsdata_id),
                    )
                    company_id = cur.fetchone()[0]
                    created += 1
                else:
                    company_id = row[0]
                    cur.execute(
                        """
                        UPDATE companies
                        SET name = %s,
                            ticker = %s,
                            borsdata_id = %s,
                            last_updated = NOW()
                        WHERE id = %s
                        """,
                        (
                            company.name,
                            company.ticker,
                            company.borsdata_id,
                            company_id,
                        ),
                    )
                    updated += 1

                cur.execute(
                    """
                    INSERT INTO watchlist (company_id, active)
                    VALUES (%s, TRUE)
                    ON CONFLICT (company_id)
                    DO UPDATE SET active = TRUE
                    """,
                    (company_id,),
                )

        return created, updated
