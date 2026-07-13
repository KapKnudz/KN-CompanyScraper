from contextlib import contextmanager
import psycopg2
from scraper import config
from scraper.logger import get_logger
from scraper.mfn_scraper import ScrapedArticle

logger = get_logger(__name__)

@contextmanager
def get_connection():
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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
                    (company_id, slug, url, title, body, scraped_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        company_id,
                        article.slug,
                        article.url,
                        article.title,
                        article.body,
                    ),
                )
                logger.info("Saved article: %s", article.title)