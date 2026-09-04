from dataclasses import dataclass
from datetime import date, datetime

from psycopg2.extras import RealDictCursor

from kncompanyscraper.repositories.base_repository import BaseRepository
from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.scraped_article import ScrapedArticle

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

class NewsRepository(BaseRepository):
    def exists(self, url: str) -> bool:
        """Check if an article with the given URL already exists."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM news_releases WHERE url = %s",
                    (url,),
                )
                return cur.fetchone() is not None

    def list_urls_for_company(self, company_id: int) -> set[str]:
        """Return stored release URLs for one company."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT url FROM news_releases WHERE company_id = %s",
                    (company_id,),
                )
                return {row[0] for row in cur.fetchall()}

    def record_feed_check(
        self,
        company_id: int,
        checked_at: datetime,
        *,
        discovered_count: int,
        unseen_count: int,
    ) -> None:
        """Persist the latest successful MFN feed check, including zero deltas."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mfn_feed_checks (
                        company_id, checked_at, discovered_count, unseen_count
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (company_id) DO UPDATE SET
                        checked_at = EXCLUDED.checked_at,
                        discovered_count = EXCLUDED.discovered_count,
                        unseen_count = EXCLUDED.unseen_count
                    """,
                    (company_id, checked_at, discovered_count, unseen_count),
                )

    def save(self, article: ScrapedArticle, company_id: int) -> None:
        """Save a new article to the database."""
        with self._get_conn() as conn:
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

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [NewsRelease(**row) for row in cur.fetchall()]
