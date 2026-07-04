from datetime import datetime, timezone
from scraper.mfn_scraper import MfnScraper, ScrapedArticle
from scraper.logger import get_logger
from scraper import db, notifier, config

logger = get_logger(__name__)


class ScraperService:
    def __init__(self):
        self.scraper = MfnScraper(
            companies_to_track=config.COMPANIES_TO_TRACK,
            headless=config.HEADLESS,
        )

    def run_scrape_cycle(self):
        run_id = db.start_scrape_run()
        errors = []

        try:
            articles = self.scraper.get_matched_articles()
            logger.info("Scraped %d articles", len(articles))

            for article in articles:
                try:
                    self._process_article(article)
                except Exception as e:
                    logger.error("Failed processing %s: %s", article.url, e)
                    errors.append({"url": article.url, "error": str(e)})

            status = "success" if not errors else "partial"

        except Exception as e:
            logger.error("Scrape cycle failed entirely: %s", e)
            errors.append({"error": str(e)})
            status = "failed"

        db.finish_scrape_run(run_id, status=status, errors=errors)
        logger.info("Scrape cycle finished with status=%s, %d errors", status, len(errors))

    def _process_article(self, article: ScrapedArticle):
        if db.article_already_seen(article.url):
            logger.info("Skipping already-seen article: %s", article.url)
            return

        company_id = db.get_or_create_company(slug=article.slug, name=article.company)
        db.save_article(article, company_id=company_id)
        notifier.notify_new_release(article)
        logger.info("Processed new article: %s - %s", article.company, article.title, "processed new article: %s - %s", article.company, article.title)