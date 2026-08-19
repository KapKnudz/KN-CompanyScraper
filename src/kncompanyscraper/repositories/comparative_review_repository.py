from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.database import get_connection


class ComparativeReviewRepository:
    def get_by_ranking_run(self, ranking_run_id: int) -> dict | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, ranking_run_id, status, raw_response, content,
                           final_scores, created_by, metadata, validation_error,
                           created_at, validated_at
                    FROM comparative_agent_reviews
                    WHERE ranking_run_id = %s
                    """,
                    (ranking_run_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def save_attempt(
        self,
        *,
        ranking_run_id: int,
        raw_response: str,
        created_by: str,
        metadata: dict,
    ) -> int:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO comparative_agent_reviews (
                        ranking_run_id, status, raw_response, created_by, metadata
                    )
                    VALUES (%s, 'pending', %s, %s, %s)
                    ON CONFLICT (ranking_run_id) DO NOTHING
                    RETURNING id
                    """,
                    (ranking_run_id, raw_response, created_by, Json(metadata)),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError("monthly ranking already has a comparative response")
                return row[0]

    def accept(self, review_id: int, result, final_ranking) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE comparative_agent_reviews
                    SET status = 'accepted', content = %s, final_scores = %s,
                        validation_error = NULL, validated_at = NOW()
                    WHERE id = %s AND status IN ('pending', 'rejected')
                    """,
                    (
                        Json(result.to_dict()),
                        Json(final_ranking.to_dict()["ranks"]),
                        review_id,
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError("comparative review cannot be accepted")

    def reject(self, review_id: int, error: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE comparative_agent_reviews
                    SET status = 'rejected', validation_error = %s,
                        validated_at = NOW()
                    WHERE id = %s AND status IN ('pending', 'rejected')
                    """,
                    (error, review_id),
                )

    def attach_to_ranking_run(
        self,
        ranking_run_id: int,
        *,
        review_id: int,
        final_actionable_company_ids: list[int],
        final_ranked_company_ids: list[int],
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ranking_runs
                    SET inputs_summary = COALESCE(inputs_summary, '{}'::JSONB) || %s
                    WHERE id = %s
                      AND snapshot_month IS NOT NULL
                      AND NOT (
                          COALESCE(inputs_summary, '{}'::JSONB) ?
                          'comparative_agent_review_id'
                      )
                    """,
                    (
                        Json(
                            {
                                "comparative_agent_review_id": review_id,
                                "comparative_final_actionable_company_ids": (
                                    final_actionable_company_ids
                                ),
                                "comparative_final_ranked_company_ids": (
                                    final_ranked_company_ids
                                ),
                            }
                        ),
                        ranking_run_id,
                    ),
                )
