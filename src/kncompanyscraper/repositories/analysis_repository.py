import json
from dataclasses import fields

from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.database import get_connection


class AnalysisRepository:
    def save_stock_analysis_raw(
        self,
        company_id: int,
        raw_response: str,
        created_by: str,
        metadata: dict | None = None,
    ) -> int:
        query = """
            INSERT INTO analysis (
                company_id, analysis_type, content, created_by, metadata
            )
            VALUES (%s, 'stock_analysis_raw', %s, %s, %s)
            RETURNING id
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        company_id,
                        raw_response,
                        created_by,
                        Json({"validation_status": "pending", **(metadata or {})}),
                    ),
                )
                return cur.fetchone()[0]

    def update_raw_validation(
        self,
        analysis_id: int,
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in {"accepted", "rejected"}:
            raise ValueError("raw validation status must be accepted or rejected")
        query = """
            UPDATE analysis
            SET metadata = (metadata - 'validation_error') || %s
            WHERE id = %s AND analysis_type = 'stock_analysis_raw'
        """
        update = {"validation_status": status}
        if error is not None:
            update["validation_error"] = error
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (Json(update), analysis_id))

    def get_stock_analysis_raw(self, analysis_id: int) -> dict | None:
        query = """
            SELECT id, company_id, content, created_by, metadata
            FROM analysis
            WHERE id = %s AND analysis_type = 'stock_analysis_raw'
        """
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (analysis_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def save_stock_analysis(
        self,
        result,
        created_by: str,
        metadata: dict | None = None,
    ) -> int:
        analysis_query = """
            INSERT INTO analysis (
                company_id, analysis_type, content, created_by, metadata
            )
            VALUES (%s, 'stock_analysis', %s, %s, %s)
            RETURNING id
        """
        content = json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM companies WHERE id = %s FOR UPDATE",
                    (result.company_id,),
                )
                cur.execute(
                    analysis_query,
                    (result.company_id, content, created_by, Json(metadata or {})),
                )
                analysis_id = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT id, revision
                    FROM company_thesis_revisions
                    WHERE company_id = %s
                    ORDER BY revision DESC
                    LIMIT 1
                    """,
                    (result.company_id,),
                )
                previous = cur.fetchone()
                previous_id, previous_revision = previous if previous else (None, 0)
                revision = previous_revision + 1
                requested_change_type = (metadata or {}).get(
                    "thesis_revision_type", "full_reassessment"
                )
                if requested_change_type not in {
                    "full_reassessment",
                    "incremental_update",
                }:
                    raise ValueError("unknown thesis revision type")
                cur.execute(
                    """
                    INSERT INTO company_thesis_revisions (
                        company_id, revision, previous_revision_id,
                        source_analysis_id, change_type, evidence_as_of,
                        confidence, confidence_limitations, content,
                        created_by, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        result.company_id,
                        revision,
                        previous_id,
                        analysis_id,
                        "initial" if previous is None else requested_change_type,
                        (metadata or {}).get("evidence_as_of"),
                        result.confidence,
                        result.confidence_limitations,
                        Json(result.to_dict()),
                        created_by,
                        Json(metadata or {}),
                    ),
                )
                thesis_revision_id = cur.fetchone()[0]
                facts = [
                    (
                        result.company_id,
                        thesis_revision_id,
                        heading_field.name,
                        fact.statement,
                        fact.evidence_kind,
                        fact.source_ids,
                        fact.source_date,
                        fact.reporting_period,
                    )
                    for heading_field in fields(result.company_fact_ledger)
                    for fact in getattr(result.company_fact_ledger, heading_field.name)
                ]
                if facts:
                    cur.executemany(
                        """
                        INSERT INTO company_facts (
                            company_id, thesis_revision_id, heading, statement,
                            evidence_kind, source_ids, source_date, reporting_period
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        facts,
                    )
                return analysis_id

    def get_latest_validated_stock_analyses(self) -> dict[int, dict]:
        query = """
            SELECT DISTINCT ON (company_id)
                id, company_id, content, created_by, created_at, metadata
            FROM analysis
            WHERE analysis_type = 'stock_analysis'
              AND metadata->>'validation_status' = 'accepted'
            ORDER BY company_id, created_at DESC, id DESC
        """
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                rows = cur.fetchall()

        return {
            row["company_id"]: {
                "analysis_id": row["id"],
                "company_id": row["company_id"],
                "content": json.loads(row["content"]),
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat(),
                "metadata": row["metadata"] or {},
            }
            for row in rows
        }

    def get_validated_stock_analyses_by_ids(
        self, analysis_ids_by_company: dict[int, int]
    ) -> dict[int, dict]:
        if not analysis_ids_by_company:
            return {}
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, content, created_by, created_at, metadata
                    FROM analysis
                    WHERE id = ANY(%s)
                      AND analysis_type = 'stock_analysis'
                      AND metadata->>'validation_status' = 'accepted'
                    """,
                    (list(analysis_ids_by_company.values()),),
                )
                rows = cur.fetchall()
        result = {}
        for row in rows:
            expected_id = analysis_ids_by_company.get(row["company_id"])
            if expected_id != row["id"]:
                continue
            result[row["company_id"]] = {
                "analysis_id": row["id"],
                "company_id": row["company_id"],
                "content": json.loads(row["content"]),
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat(),
                "metadata": row["metadata"] or {},
            }
        return result

    def get_latest_rejected_incremental_updates(
        self, company_ids: list[int]
    ) -> dict[int, dict]:
        if not company_ids:
            return {}
        query = """
            SELECT id, company_id, content, created_by, metadata
            FROM (
                SELECT DISTINCT ON (company_id)
                    id, company_id, content, created_by, metadata, created_at
                FROM analysis
                WHERE analysis_type = 'stock_analysis_raw'
                  AND metadata->>'analysis_mode' = 'incremental_update'
                  AND company_id = ANY(%s)
                ORDER BY company_id, created_at DESC, id DESC
            ) latest
            WHERE metadata->>'validation_status' = 'rejected'
        """
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (company_ids,))
                rows = cur.fetchall()
        return {row["company_id"]: dict(row) for row in rows}

    def get_latest_rejected_initial_analyses(
        self, company_ids: list[int]
    ) -> dict[int, dict]:
        if not company_ids:
            return {}
        query = """
            SELECT id, company_id, content, created_by, metadata
            FROM (
                SELECT DISTINCT ON (company_id)
                    id, company_id, content, created_by, metadata, created_at
                FROM analysis
                WHERE analysis_type = 'stock_analysis_raw'
                  AND COALESCE(metadata->>'analysis_mode', 'initial') = 'initial'
                  AND company_id = ANY(%s)
                ORDER BY company_id, created_at DESC, id DESC
            ) latest
            WHERE metadata->>'validation_status' = 'rejected'
        """
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (company_ids,))
                rows = cur.fetchall()
        return {row["company_id"]: dict(row) for row in rows}
