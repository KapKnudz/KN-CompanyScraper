from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.database import get_connection


class RankingChallengerRepository:
    def save(self, snapshot) -> tuple[int, bool]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ranking_challenger_snapshots (
                        snapshot_month, source_ranking_run_id, source_as_of,
                        policy_version, status, company_count, eligible_count,
                        affected_company_count, scores,
                        production_top_company_ids, challenger_top_company_ids
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (snapshot_month, policy_version) DO NOTHING
                    RETURNING id
                    """,
                    (
                        snapshot.snapshot_month,
                        snapshot.source_ranking_run_id,
                        snapshot.source_as_of,
                        snapshot.policy_version,
                        snapshot.status,
                        snapshot.company_count,
                        snapshot.eligible_count,
                        snapshot.affected_company_count,
                        Json(snapshot.scores),
                        Json(snapshot.production_top_company_ids),
                        Json(snapshot.challenger_top_company_ids),
                    ),
                )
                row = cur.fetchone()
                if row:
                    return row[0], True
                cur.execute(
                    """
                    SELECT id FROM ranking_challenger_snapshots
                    WHERE snapshot_month = %s AND policy_version = %s
                    """,
                    (snapshot.snapshot_month, snapshot.policy_version),
                )
                return cur.fetchone()[0], False

    def list_snapshots(self) -> list[dict]:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, snapshot_month, source_ranking_run_id, source_as_of,
                           policy_version, status, company_count, eligible_count,
                           affected_company_count, scores,
                           production_top_company_ids, challenger_top_company_ids,
                           created_at
                    FROM ranking_challenger_snapshots
                    ORDER BY snapshot_month, id
                    """
                )
                rows = cur.fetchall()
        return [self._snapshot_dict(row) for row in rows]

    def get_for_month(self, snapshot_month, policy_version: str) -> dict | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, snapshot_month, source_ranking_run_id, source_as_of,
                           policy_version, status, company_count, eligible_count,
                           affected_company_count, scores,
                           production_top_company_ids, challenger_top_company_ids,
                           created_at
                    FROM ranking_challenger_snapshots
                    WHERE snapshot_month = %s AND policy_version = %s
                    """,
                    (snapshot_month, policy_version),
                )
                row = cur.fetchone()
        return self._snapshot_dict(row) if row else None

    def save_performance_evaluation(
        self, evaluation, policy_version: str
    ) -> tuple[int, bool]:
        payload = evaluation.to_dict()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ranking_challenger_performance_evaluations (
                        challenger_snapshot_id, horizon_months, target_date,
                        status, policy_version, result
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        challenger_snapshot_id, horizon_months, policy_version
                    )
                    DO UPDATE SET
                        target_date = EXCLUDED.target_date,
                        status = EXCLUDED.status,
                        policy_version = EXCLUDED.policy_version,
                        result = EXCLUDED.result,
                        evaluated_at = NOW()
                    WHERE ranking_challenger_performance_evaluations.status <> 'complete'
                    RETURNING id
                    """,
                    (
                        evaluation.challenger_snapshot_id,
                        evaluation.horizon_months,
                        evaluation.target_date,
                        evaluation.status,
                        policy_version,
                        Json(payload),
                    ),
                )
                row = cur.fetchone()
                if row:
                    return row[0], True
                cur.execute(
                    """
                    SELECT id FROM ranking_challenger_performance_evaluations
                    WHERE challenger_snapshot_id = %s
                      AND horizon_months = %s
                      AND policy_version = %s
                    """,
                    (
                        evaluation.challenger_snapshot_id,
                        evaluation.horizon_months,
                        policy_version,
                    ),
                )
                return cur.fetchone()[0], False

    def list_performance_evaluations(
        self,
        *,
        challenger_snapshot_id: int | None = None,
        limit: int = 24,
    ) -> list[dict]:
        query = """
            SELECT evaluation.id, evaluation.challenger_snapshot_id,
                   evaluation.horizon_months, evaluation.target_date,
                   evaluation.status, evaluation.policy_version,
                   evaluation.result, evaluation.evaluated_at,
                   snapshot.snapshot_month
            FROM ranking_challenger_performance_evaluations AS evaluation
            JOIN ranking_challenger_snapshots AS snapshot
              ON snapshot.id = evaluation.challenger_snapshot_id
        """
        params = []
        if challenger_snapshot_id is not None:
            query += " WHERE evaluation.challenger_snapshot_id = %s"
            params.append(challenger_snapshot_id)
        query += """
            ORDER BY snapshot.snapshot_month DESC,
                     evaluation.horizon_months DESC,
                     evaluation.id DESC
            LIMIT %s
        """
        params.append(limit)
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "challenger_snapshot_id": row["challenger_snapshot_id"],
                "snapshot_month": row["snapshot_month"].isoformat(),
                "horizon_months": row["horizon_months"],
                "target_date": row["target_date"].isoformat(),
                "status": row["status"],
                "policy_version": row["policy_version"],
                "result": row["result"],
                "evaluated_at": row["evaluated_at"].isoformat(),
            }
            for row in rows
        ]

    @staticmethod
    def _snapshot_dict(row) -> dict:
        return {
            "id": row["id"],
            "snapshot_month": row["snapshot_month"].isoformat(),
            "source_ranking_run_id": row["source_ranking_run_id"],
            "source_as_of": row["source_as_of"].isoformat(),
            "policy_version": row["policy_version"],
            "status": row["status"],
            "company_count": row["company_count"],
            "eligible_count": row["eligible_count"],
            "affected_company_count": row["affected_company_count"],
            "scores": row["scores"],
            "production_top_company_ids": row["production_top_company_ids"],
            "challenger_top_company_ids": row["challenger_top_company_ids"],
            "created_at": row["created_at"].isoformat(),
        }
