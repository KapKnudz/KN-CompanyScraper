from scraper.models.company import Company
from scraper.database import get_connection
from psycopg2.extras import RealDictCursor


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
                    INSERT INTO companies (name, ticker, mfn_slug, borsdata_id)
                    VALUES (%s, %s, %s) RETURNING id, name, ticker, mfn_slug, borsdata_id, last_updated
                    """,
                    (
                        company.name,
                        company.ticker,
                        company.mfn_slug,
                        company.borsdata_id,
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
                        last_updated = NOW()
                    WHERE id = %s
                    """,
                    (
                        company.name,
                        company.ticker,
                        company.mfn_slug,
                        company.borsdata_id,
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
                           c.last_updated
                    FROM companies c
                             JOIN watchlist w
                                  ON c.id = w.company_id
                    WHERE w.active = TRUE
                    ORDER BY c.name
                    """
                )


                return [Company(**row) for row in cur.fetchall()]