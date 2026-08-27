from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.repositories.base_repository import BaseRepository


class AgentCohortRepository(BaseRepository):
    def save(self, snapshot) -> tuple[int, bool]:
        payload = snapshot.to_dict()
        return self._insert_or_get(
            """
                    INSERT INTO agent_cohort_snapshots (
                        snapshot_month, deterministic_run_id, policy_version,
                        target_size, grace_months, eligible_universe_company_ids,
                        top_company_ids, members
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (snapshot_month) DO NOTHING
                    RETURNING id
                    """,
                    (
                        snapshot.snapshot_month,
                        snapshot.deterministic_run_id,
                        snapshot.policy_version,
                        snapshot.target_size,
                        snapshot.grace_months,
                        Json(payload["eligible_universe_company_ids"]),
                        Json(payload["top_company_ids"]),
                        Json(payload["members"]),
                    ),
            "SELECT id FROM agent_cohort_snapshots WHERE snapshot_month = %s",
            (snapshot.snapshot_month,),
        )

    def get_for_month(self, snapshot_month) -> dict | None:
        return self._get(
            "WHERE snapshot_month = %s",
            (snapshot_month,),
        )

    def get_latest_before(self, snapshot_month) -> dict | None:
        return self._get(
            "WHERE snapshot_month < %s ORDER BY snapshot_month DESC LIMIT 1",
            (snapshot_month,),
        )

    @staticmethod
    def _get(where_clause: str, params: tuple) -> dict | None:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT id, snapshot_month, deterministic_run_id, policy_version,
                           target_size, grace_months,
                           eligible_universe_company_ids, top_company_ids, members,
                           created_at
                    FROM agent_cohort_snapshots
                    {where_clause}
                    """,
                    params,
                )
                row = cur.fetchone()
        return dict(row) if row else None
