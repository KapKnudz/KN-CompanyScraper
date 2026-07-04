import psycopg2
import psycopg2.extras
import json
from contextlib import contextmanager
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


def start_scrape_run() -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (status) VALUES ('running') RETURNING id"
            )
            run_id = cur.fetchone()[0]
            logger.info("Started scrape_run id=%s", run_id)
            return run_id


def finish_scrape_run(run_id: int, status: str, errors: list):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_runs
                SET status = %s, finished_at = now(), errors = %s
                WHERE id = %s
                """,
                (status, json.dumps(errors), run_id),
            )


def get_or_create_company(slug: str, name: str) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM companies WHERE ticker = %s", (slug,))
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                "INSERT INTO companies (name, ticker) VALUES (%s, %s) RETURNING id",
                (name, slug),
            )
            company_id = cur.fetchone()[0]
            logger.info("Created new company: %s (%s)", name, slug)
            return company_id


def article_already_seen(url: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM news_releases WHERE url = %s", (url,))
            return cur.fetchone() is not None


def save_article(article: ScrapedArticle, company_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_releases (company_id, slug, url, title, body)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (company_id, article.slug, article.url, article.title, article.body),
            )