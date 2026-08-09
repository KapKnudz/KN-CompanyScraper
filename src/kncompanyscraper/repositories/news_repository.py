from dataclasses import dataclass
from datetime import date, datetime

from psycopg2.extras import RealDictCursor

from kncompanyscraper.database import get_connection
from kncompanyscraper.logger import get_logger
from kncompanyscraper.scraper.mfn_scraper import ScrapedArticle

logger = get_logger(__name__)


@dataclass(frozen=True)
class NewsRelease:
    id: int
    company_id: int
    slug: str
    url: str
    title: str
    body: str
    published_at: datetime | None

class NewsRepository:
    def exists(self, url: str) -> bool:
        """Check if an article with the given URL already exists."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM news_releases WHERE url = %s",
                    (url,),
                )
                return cur.fetchone() is not None

    def save(self, article: ScrapedArticle, company_id: int) -> None:
        """Save a new article to the database."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO news_releases
                    (company_id, slug, url, title, body, published_at, scraped_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        company_id,
                        article.slug,
                        article.url,
                        article.title,
                        article.body,
                        article.published_at,
                    ),
                )
                logger.info("Saved article: %s", article.title)

    def list_for_company(
        self,
        company_id: int,
        as_of: date | None = None,
        limit: int | None = None,
    ) -> list[NewsRelease]:
        query = """
            SELECT id, company_id, slug, url, title, body, published_at
            FROM news_releases
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
                return [NewsRelease(**row) for row in cur.fetchall()]
