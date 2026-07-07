import schedule
import time

from scraper.logger import get_logger
from scraper import config
from scraper.jobs.news_job import NewsJob
from scraper.repositories.company_repository import CompanyRepository
from scraper.repositories.news_repository import NewsRepository
from scraper.notifier import Notifier

logger = get_logger(__name__)
print("Scheduler module loaded")

def run_once():
    # Create the repository without passing a connection
    # The repository methods will handle their own connections
    repository = CompanyRepository()
    companies = repository.get_active_companies()

    news_repository = NewsRepository()
    notifier = Notifier()

    jobs = [
        NewsJob(news_repository, notifier),
    ]

    for company in companies:
        logger.info("Running jobs for %s", company.name)

        for job in jobs:
            try:
                job.run(company)
            except Exception as e:
                logger.exception(
                    "Job %s failed for %s: %s",
                    job.__class__.__name__,
                    company.name,
                    e,
                )


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