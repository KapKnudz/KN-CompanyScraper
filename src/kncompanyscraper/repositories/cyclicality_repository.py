from psycopg2.extras import Json

from kncompanyscraper.repositories.base_repository import BaseRepository


class CyclicalityRepository(BaseRepository):
    def save_consensus(
        self,
        company_id: int,
        consensus: dict,
        *,
        classifier_policy_version: str,
        consensus_policy_version: str,
    ) -> None:
        query = """
            INSERT INTO company_cyclicality_consensus (
                company_id,
                classifier_policy_version,
                consensus_policy_version,
                consensus
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (company_id) DO UPDATE SET
                classifier_policy_version = EXCLUDED.classifier_policy_version,
                consensus_policy_version = EXCLUDED.consensus_policy_version,
                consensus = EXCLUDED.consensus,
                classified_at = now()
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        company_id,
                        classifier_policy_version,
                        consensus_policy_version,
                        Json(consensus),
                    ),
                )

    def get_consensus(self, company_id: int) -> dict | None:
        query = """
            SELECT consensus
            FROM company_cyclicality_consensus
            WHERE company_id = %s
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_id,))
                row = cur.fetchone()
        return row[0] if row else None
