import json

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

    def save_stock_analysis(
        self,
        result,
        created_by: str,
        metadata: dict | None = None,
    ) -> int:
        query = """
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
                    query,
                    (result.company_id, content, created_by, Json(metadata or {})),
                )
                return cur.fetchone()[0]

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
