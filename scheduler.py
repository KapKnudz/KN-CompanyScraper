import schedule
import time

from scraper.logger import get_logger
from scraper import config
from scraper.jobs.news_job import NewsJob
from scraper.repositories.company_repository import CompanyRepository
from scraper.repositories.news_repository import NewsRepository
from scraper.notifier import Notifier
from scraper.repositories.scrape_run_repository import ScrapeRunRepository

logger = get_logger(__name__)
repository = CompanyRepository()
news_repository = NewsRepository()
scrape_run_repository = ScrapeRunRepository()
notifier = Notifier()

def run_once():

    scrape_run_id = scrape_run_repository.start()

    companies_found = 0
    news_added = 0

    try:

        companies = repository.get_active_companies()
        companies_found = len(companies)

        jobs = [
            NewsJob(
                news_repository,
                notifier
            )
        ]

        for company in companies:
            for job in jobs:
                result = job.run(company)
                news_added += result

        scrape_run_repository.complete(
            scrape_run_id,
            "success",
            companies_found,
            news_added
        )

    except Exception as e:

        scrape_run_repository.fail(
            scrape_run_id,
            str(e),
            companies_found,
            news_added
        )

        raise

def start():
    logger.info(
        "Scheduler starting. Running every %d minutes.",
        config.SCRAPE_INTERVAL_MINUTES,
    )

    run_once()

    schedule.every(config.SCRAPE_INTERVAL_MINUTES).minutes.do(run_once)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    start()