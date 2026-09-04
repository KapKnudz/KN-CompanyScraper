from psycopg2.extras import Json
from psycopg2.extras import RealDictCursor

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

    def get(self, job_id: int) -> dict | None:
        """Read one durable job and its latest checkpoint."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, job_type, status, company_id, started_at,
                           completed_at, result, error
                    FROM jobs
                    WHERE id = %s
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def update_result(self, job_id: int, result: dict) -> None:
        """Persist the latest partial result for a running job."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET result = %s
                    WHERE id = %s AND status = 'running'
                    """,
                    (Json(result), job_id),
                )

    def checkpoint_stage_input(
        self, job_id: int, stage: str, checkpoint: dict
    ) -> None:
        """Checkpoint a stage's frozen prompt artifact before model invocation."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET result = jsonb_set(
                        COALESCE(result, '{}'::jsonb),
                        ARRAY['stages', %s],
                        COALESCE(result #> ARRAY['stages', %s], '{}'::jsonb)
                            || %s::jsonb,
                        true
                    )
                    WHERE id = %s AND status = 'running'
                    """,
                    (stage, stage, Json(checkpoint), job_id),
                )

    def update_partial_result(self, job_id: int, patch: dict) -> None:
        """Merge a checkpoint into the existing JSON result."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET result = COALESCE(result, '{}'::jsonb) || %s
                    WHERE id = %s
                    """,
                    (Json(patch), job_id),
                )

    def mark_running(self, job_id: int) -> None:
        """Make a resumable job active again without changing its checkpoint."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'running', completed_at = NULL, error = NULL
                    WHERE id = %s
                    """,
                    (job_id,),
                )

    def fail(self, job_id: int, error: str, result: dict | None = None) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', completed_at = NOW(), error = %s, result = %s
                    WHERE id = %s
                    """,
                    (error, Json(result or {}), job_id),
                )
