import json

from psycopg2.extras import Json

from kncompanyscraper.database import get_connection


class AnalysisRepository:
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
