from psycopg2.extras import Json

from kncompanyscraper.repositories.base_repository import BaseRepository


class PortfolioRepository(BaseRepository):
    def save_run(self, portfolio_run: dict) -> int:
        query = """
            INSERT INTO portfolio_runs (as_of, target_size, status, content)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        with self._get_conn() as conn:
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
