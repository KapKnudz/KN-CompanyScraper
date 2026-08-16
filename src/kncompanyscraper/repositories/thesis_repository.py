from psycopg2.extras import RealDictCursor

from kncompanyscraper.database import get_connection


class ThesisRepository:
    def get_latest(self, company_id: int) -> dict | None:
        query = """
            SELECT id, company_id, revision, previous_revision_id,
                   source_analysis_id, change_type, evidence_as_of,
                   confidence, confidence_limitations, content,
                   created_by, metadata, created_at
            FROM company_thesis_revisions
            WHERE company_id = %s
            ORDER BY revision DESC
            LIMIT 1
        """
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (company_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def list_latest_facts(self, company_id: int) -> list[dict]:
        query = """
            SELECT f.id, f.company_id, f.thesis_revision_id, f.heading,
                   f.statement, f.evidence_kind, f.source_ids,
                   f.source_date, f.reporting_period, f.created_at
            FROM company_facts f
            JOIN company_thesis_revisions t ON t.id = f.thesis_revision_id
            WHERE f.company_id = %s
              AND t.revision = (
                  SELECT MAX(revision)
                  FROM company_thesis_revisions
                  WHERE company_id = %s
              )
            ORDER BY f.heading, f.id
        """
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (company_id, company_id))
                rows = cur.fetchall()
        return [dict(row) for row in rows]
