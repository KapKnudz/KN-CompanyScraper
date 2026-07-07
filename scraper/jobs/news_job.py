from scraper.mfn_scraper import MfnScraper, ScrapedArticle
from scraper.logger import get_logger

logger = get_logger(__name__)

class NewsJob:
    def __init__(self, news_repository, notifier):
        self.news_repository = news_repository
        self.notifier = notifier

    def run(self, company):
        logger.info("NewsJob started for %s", company.name)

        scraper = MfnScraper(company)
        articles = scraper.get_matched_articles()

        logger.info("Found %d articles", len(articles))

        for article in articles:
            logger.info("Processing article %s", article.title)

            if self.news_repository.exists(article.url):
                continue

            self.news_repository.save(article, company.id)
            self.notifier.notify_new_release(article)

        logger.info("NewsJob finished for %s", company.name)