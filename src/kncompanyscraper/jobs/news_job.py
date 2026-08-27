from kncompanyscraper.scraper.mfn_scraper import MfnScraper
from kncompanyscraper.logger import get_logger
from kncompanyscraper.jobs.job import run_isolated

logger = get_logger(__name__)


class NewsJob:
    def __init__(self, news_repository, notifier, job_repository=None):
        self.news_repository = news_repository
        self.notifier = notifier
        self.job_repository = job_repository

    def run(self, company):
        return run_isolated(
            lambda: self._run(company),
            logger=logger,
            job_repository=self.job_repository,
            job_type="news",
            company_id=company.id,
        )

    def _run(self, company):
        logger.info("NewsJob started for %s", company.name)

        try:
            articles = MfnScraper(company).get_matched_articles()
        except Exception:
            logger.exception("News scrape failed for %s; continuing", company.name)
            return 0
        inserted = 0

        logger.info("Found %d articles", len(articles))

        for article in articles:
            logger.info("Processing article %s", article.title)

            try:
                if self.news_repository.exists(article.url):
                    continue

                self.news_repository.save(article, company.id)
                self.notifier.notify_new_release(article)
            except Exception:
                logger.exception(
                    "Failed to process article %s for %s",
                    article.url,
                    company.name,
                )
                continue

            inserted += 1

        logger.info(
            "NewsJob finished for %s. Added %d new articles",
            company.name,
            inserted
        )

        return inserted
