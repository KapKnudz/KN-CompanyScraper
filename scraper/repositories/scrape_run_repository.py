from datetime import datetime
from scraper.database import get_connection


class ScrapeRunRepository:

    def start(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scrape_runs
                    (status)
                    VALUES ('running')
                    RETURNING id
                    """
                )
                return cur.fetchone()[0]


    def complete(self, run_id):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE scrape_runs
                    SET
                        finished_at = NOW(),
                        status = 'success'
                    WHERE id = %s
                    """,
                    (run_id,)
                )


    def fail(self, run_id, error):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE scrape_runs
                    SET
                        finished_at = NOW(),
                        status = 'failed',
                        errors = %s
                    WHERE id = %s
                    """,
                    (error, run_id)
                )