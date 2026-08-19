from psycopg2.extras import Json
from kncompanyscraper.repositories.base_repository import BaseRepository


class RankingRepository(BaseRepository):
    def save_monthly_ranking_run(
        self,
        *,
        snapshot_month,
        model_version: str,
        company_count: int,
        eligible_count: int,
        scores: list[dict],
        inputs_summary: dict,
    ) -> tuple[int, bool]:
        with self._get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO ranking_runs (
                    snapshot_month, model_version, company_count,
                    eligible_count, scores, inputs_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_month)
                    WHERE snapshot_month IS NOT NULL
                DO NOTHING
                RETURNING id
                """,
                (
                    snapshot_month,
                    model_version,
                    company_count,
                    eligible_count,
                    Json(scores),
                    Json(inputs_summary),
                ),
            )
            row = cur.fetchone()
            if row:
                return row[0], True
            cur.execute(
                """
                SELECT id FROM ranking_runs
                WHERE snapshot_month = %s
                """,
                (snapshot_month,),
            )
            return cur.fetchone()[0], False

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
        with self._get_cursor() as cur:
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
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT id, run_at, model_version, company_count, eligible_count,
                       scores, inputs_summary, snapshot_month
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

    def get_latest_deterministic_run(self, as_of) -> dict | None:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT id, run_at, model_version, company_count, eligible_count,
                       scores, inputs_summary
                FROM ranking_runs
                WHERE snapshot_month IS NULL
                  AND run_at::date <= %s
                  AND COALESCE(inputs_summary->>'ranking_type', '') <>
                      'combined_forward_scenario'
                ORDER BY run_at DESC, id DESC
                LIMIT 1
                """,
                (as_of,),
            )
            row = cur.fetchone()
        return self._run_dict(row) if row else None

    def list_monthly_runs(self) -> list[dict]:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT id, run_at, model_version, company_count, eligible_count,
                       scores, inputs_summary, snapshot_month
                FROM ranking_runs
                WHERE snapshot_month IS NOT NULL
                ORDER BY snapshot_month, id
                """
            )
            rows = cur.fetchall()
        return [self._run_dict(row) for row in rows]

    def get_latest_monthly_run_before(self, snapshot_month) -> dict | None:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT id, run_at, model_version, company_count, eligible_count,
                       scores, inputs_summary, snapshot_month
                FROM ranking_runs
                WHERE snapshot_month < %s
                ORDER BY snapshot_month DESC, id DESC
                LIMIT 1
                """,
                (snapshot_month,),
            )
            row = cur.fetchone()
        return self._run_dict(row) if row else None

    def save_performance_evaluation(self, evaluation, policy_version: str) -> tuple[int, bool]:
        payload = evaluation.to_dict()
        with self._get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO ranking_performance_evaluations (
                    ranking_run_id, horizon_months, target_date,
                    status, policy_version, result
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ranking_run_id, horizon_months) DO UPDATE SET
                    target_date = EXCLUDED.target_date,
                    status = EXCLUDED.status,
                    policy_version = EXCLUDED.policy_version,
                    result = EXCLUDED.result,
                    evaluated_at = NOW()
                WHERE ranking_performance_evaluations.status <> 'complete'
                RETURNING id
                """,
                (
                    evaluation.ranking_run_id,
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
                SELECT id FROM ranking_performance_evaluations
                WHERE ranking_run_id = %s AND horizon_months = %s
                """,
                (evaluation.ranking_run_id, evaluation.horizon_months),
            )
            return cur.fetchone()[0], False

    def list_performance_evaluations(
        self,
        *,
        ranking_run_id: int | None = None,
        limit: int = 24,
    ) -> list[dict]:
        query = """
            SELECT evaluation.id, evaluation.ranking_run_id,
                   evaluation.horizon_months, evaluation.target_date,
                   evaluation.status, evaluation.policy_version,
                   evaluation.result, evaluation.evaluated_at,
                   ranking.snapshot_month
            FROM ranking_performance_evaluations AS evaluation
            JOIN ranking_runs AS ranking ON ranking.id = evaluation.ranking_run_id
        """
        params = []
        if ranking_run_id is not None:
            query += " WHERE evaluation.ranking_run_id = %s"
            params.append(ranking_run_id)
        query += """
            ORDER BY ranking.snapshot_month DESC,
                     evaluation.horizon_months DESC,
                     evaluation.id DESC
            LIMIT %s
        """
        params.append(limit)

        with self._get_dict_cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "ranking_run_id": row["ranking_run_id"],
                "snapshot_month": (
                    row["snapshot_month"].isoformat()
                    if row["snapshot_month"] is not None
                    else None
                ),
                "horizon_months": row["horizon_months"],
                "target_date": row["target_date"].isoformat(),
                "status": row["status"],
                "policy_version": row["policy_version"],
                "result": row["result"],
                "evaluated_at": row["evaluated_at"].isoformat(),
            }
            for row in rows
        ]

    def attach_cohort_provenance(
        self,
        ranking_run_id: int,
        *,
        cohort_snapshot_id: int,
        cohort_company_ids: list[int],
        recall_universe_company_ids: list[int],
    ) -> None:
        with self._get_cursor() as cur:
            cur.execute(
                """
                UPDATE ranking_runs
                SET inputs_summary = COALESCE(inputs_summary, '{}'::JSONB) || %s
                WHERE id = %s
                  AND snapshot_month IS NOT NULL
                  AND NOT (
                      COALESCE(inputs_summary, '{}'::JSONB) ?
                      'agent_cohort_snapshot_id'
                  )
                """,
                (
                    Json(
                        {
                            "agent_cohort_snapshot_id": cohort_snapshot_id,
                            "agent_cohort_company_ids": cohort_company_ids,
                            "recall_universe_company_ids": (
                                recall_universe_company_ids
                            ),
                        }
                    ),
                    ranking_run_id,
                ),
            )

    def attach_tier_hysteresis_provenance(
        self,
        ranking_run_id: int,
        *,
        proposed_economic_tiers: dict[str, str],
        effective_economic_tiers: dict[str, str],
        pending_transitions: dict[str, dict],
        policy_version: str,
    ) -> None:
        with self._get_cursor() as cur:
            cur.execute(
                """
                UPDATE ranking_runs
                SET inputs_summary = COALESCE(inputs_summary, '{}'::JSONB) || %s
                WHERE id = %s
                  AND snapshot_month IS NOT NULL
                  AND NOT (
                      COALESCE(inputs_summary, '{}'::JSONB) ?
                      'tier_hysteresis_policy_version'
                  )
                """,
                (
                    Json(
                        {
                            "tier_hysteresis_policy_version": policy_version,
                            "proposed_economic_tiers": proposed_economic_tiers,
                            "effective_economic_tiers": effective_economic_tiers,
                            "pending_tier_transitions": pending_transitions,
                        }
                    ),
                    ranking_run_id,
                ),
            )

    def get_run(self, run_id: int) -> dict | None:
        with self._get_dict_cursor() as cur:
            cur.execute(
                """
                SELECT id, run_at, model_version, company_count, eligible_count,
                       scores, inputs_summary, snapshot_month
                FROM ranking_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return self._run_dict(row)

    @staticmethod
    def _run_dict(row) -> dict:
        result = {
            "id": row["id"],
            "run_at": row["run_at"].isoformat(),
            "model_version": row["model_version"],
            "company_count": row["company_count"],
            "eligible_count": row["eligible_count"],
            "scores": row["scores"],
            "inputs_summary": row["inputs_summary"] or {},
        }
        if "snapshot_month" in row:
            result["snapshot_month"] = row["snapshot_month"].isoformat()
        return result
