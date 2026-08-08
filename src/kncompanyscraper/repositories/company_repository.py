from kncompanyscraper.models.company import Company
from kncompanyscraper.database import get_connection
from kncompanyscraper.models.company_profile import CompanyProfile
from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.watchlist_import import WatchlistCompany


class CompanyRepository:

    def __init__(self, connection=None):
        self.connection = connection

    def get_by_id(self, company_id: int) -> Company | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO companies (
                        name, ticker, mfn_slug, borsdata_id, isin, currency,
                        sector_id, branch_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, name, ticker, mfn_slug, borsdata_id, last_updated,
                              isin, currency, sector_id, branch_id
                    """,
                    (
                        company.name,
                        company.ticker,
                        company.mfn_slug,
                        company.borsdata_id,
                        company.isin,
                        company.currency,
                        company.sector_id,
                        company.branch_id,
                    ),
                )

                return Company(**cur.fetchone())

    def update(self, company: Company) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE companies
                    SET name         = %s,
                        ticker       = %s,
                        borsdata_id  = %s,
                        mfn_slug     = %s,
                        isin         = %s,
                        currency     = %s,
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
                        company.sector_id,
                        company.branch_id,
                        company.id,
                    ),
                )

    def get_profile(self, company_id: int) -> CompanyProfile | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM company_profiles
                    WHERE company_id = %s
                    """,
                    (company_id,),
                )

                row = cur.fetchone()
                return CompanyProfile(**row) if row else None

    def save_profile(self, profile: CompanyProfile) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO company_profiles (
                        company_id,
                        description,
                        business_model,
                        competitive_advantages,
                        management
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (company_id)
                    DO UPDATE SET
                        description = EXCLUDED.description,
                        business_model = EXCLUDED.business_model,
                        competitive_advantages = EXCLUDED.competitive_advantages,
                        management = EXCLUDED.management,
                        updated_at = NOW()
                    """,
                    (
                        profile.company_id,
                        profile.description,
                        profile.business_model,
                        profile.competitive_advantages,
                        Json(profile.management),
                    ),
                )

    def get_active_companies(self) -> list[Company]:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT c.id,
                           c.name,
                           c.ticker,
                           c.borsdata_id,
                           c.mfn_slug,
                           c.isin,
                           c.currency,
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

    def set_borsdata_identity(
        self,
        company_id: int,
        borsdata_id: int,
        currency: str | None,
        sector_id: int | None,
        branch_id: int | None,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE companies
                    SET borsdata_id = %s,
                        currency = COALESCE(%s, currency),
                        sector_id = %s,
                        branch_id = %s,
                        last_updated = NOW()
                    WHERE id = %s
                    """,
                    (borsdata_id, currency, sector_id, branch_id, company_id),
                )

    def upsert_watchlist_companies(
        self,
        companies: list[WatchlistCompany],
    ) -> tuple[int, int]:
        created = 0
        updated = 0

        with get_connection() as conn:
            with conn.cursor() as cur:
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
