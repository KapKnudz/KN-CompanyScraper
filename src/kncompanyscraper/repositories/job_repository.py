from psycopg2.extras import Json

from kncompanyscraper.repositories.base_repository import BaseRepository


class JobRepository(BaseRepository):

    def start(self, job_type: str, company_id: int | None) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (job_type, status, company_id, started_at)
                    VALUES (%s, 'running', %s, NOW())
                    RETURNING id
                    """,
                    (job_type, company_id),
                )
                return cur.fetchone()[0]

    def complete(self, job_id: int, result: dict | None = None) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'success', completed_at = NOW(), result = %s
                    WHERE id = %s
                    """,
                    (Json(result or {}), job_id),
                )

    def fail(self, job_id: int, error: str) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', completed_at = NOW(), error = %s
                    WHERE id = %s
                    """,
                    (error, job_id),
                )
