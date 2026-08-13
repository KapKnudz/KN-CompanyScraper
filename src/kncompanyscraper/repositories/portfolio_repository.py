from psycopg2.extras import Json

from kncompanyscraper.database import get_connection


class PortfolioRepository:
    def save_run(self, portfolio_run: dict) -> int:
        query = """
            INSERT INTO portfolio_runs (as_of, target_size, status, content)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        portfolio_run["as_of"],
                        portfolio_run["target_size"],
                        portfolio_run["status"],
                        Json(portfolio_run),
                    ),
                )
                return cur.fetchone()[0]
