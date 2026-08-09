from datetime import date

from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.database import get_connection
from kncompanyscraper.models.research_document import ResearchDocument


class ResearchDocumentRepository:
    def exists(self, url: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM research_documents WHERE url = %s", (url,))
                return cur.fetchone() is not None

    def save(self, document: ResearchDocument) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_documents (
                        company_id, document_type, title, url, published_at,
                        document_text, source_release_url, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        document.company_id,
                        document.document_type,
                        document.title,
                        document.url,
                        document.published_at,
                        document.text,
                        document.source_release_url,
                        Json(document.metadata),
                    ),
                )
                return cur.rowcount == 1

    def list_for_company(
        self,
        company_id: int,
        as_of: date | None = None,
        limit: int | None = None,
    ) -> list[ResearchDocument]:
        query = """
            SELECT id, company_id, document_type, title, url, published_at,
                   document_text, source_release_url, metadata
            FROM research_documents
            WHERE company_id = %s
        """
        params: list = [company_id]
        if as_of is not None:
            query += " AND (published_at IS NULL OR published_at::date <= %s)"
            params.append(as_of)
        query += " ORDER BY published_at DESC NULLS LAST, id DESC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        return [
            ResearchDocument(
                id=row["id"],
                company_id=row["company_id"],
                document_type=row["document_type"],
                title=row["title"],
                url=row["url"],
                published_at=row["published_at"],
                text=row["document_text"],
                source_release_url=row["source_release_url"],
                metadata=row["metadata"] or {},
            )
            for row in rows
        ]
