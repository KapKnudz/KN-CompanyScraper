from scraper.mfn_scraper import MfnScraper, ScrapedArticle

class NewsJob:
    def __init__(self, news_repository, notifier):
        self.news_repository = news_repository
        self.notifier = notifier

    def run(self, company):
        # Use MfnScraper to fetch articles for the company
        scraper = MfnScraper(company)
        articles = scraper.get_matched_articles()

        for article in articles:
            if self.news_repository.exists(article.url):
                continue

            self.news_repository.save(article, company.id)
            self.notifier.notify(article)