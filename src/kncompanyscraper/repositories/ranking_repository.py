import json

from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.database import get_connection


class RankingRepository:
    def save_ranking_run(
        self,
        model_version: str,
        company_count: int,
        eligible_count: int,
        scores: list[dict],
        inputs_summary: dict | None = None,
    ) -> int:
        query = """
            INSERT INTO ranking_runs (
                model_version, company_count, eligible_count, scores, inputs_summary
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        model_version,
                        company_count,
                        eligible_count,
                        Json(scores),
                        Json(inputs_summary or {}),
                    ),
                )
                return cur.fetchone()[0]

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, run_at, model_version, company_count, eligible_count,
                           scores, inputs_summary
                    FROM ranking_runs
                    ORDER BY run_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [
                    {
                        "id": row["id"],
                        "run_at": row["run_at"].isoformat(),
                        "model_version": row["model_version"],
                        "company_count": row["company_count"],
                        "eligible_count": row["eligible_count"],
                        "scores": row["scores"],
                        "inputs_summary": row["inputs_summary"],
                    }
                    for row in cur.fetchall()
                ]

    def get_run(self, run_id: int) -> dict | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, run_at, model_version, company_count, eligible_count,
                           scores, inputs_summary
                    FROM ranking_runs
                    WHERE id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "id": row["id"],
                    "run_at": row["run_at"].isoformat(),
                    "model_version": row["model_version"],
                    "company_count": row["company_count"],
                    "eligible_count": row["eligible_count"],
                    "scores": row["scores"],
                    "inputs_summary": row["inputs_summary"],
                }
