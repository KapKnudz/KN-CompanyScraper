import schedule
import time
from scraper.service import ScraperService
from scraper.logger import get_logger
from scraper import config

logger = get_logger(__name__)


def run_once():
    """Run a single scrape cycle immediately, with error isolation."""
    try:
        ScraperService().run_scrape_cycle()
    except Exception as e:
        # Catch-all safety net: even if run_scrape_cycle's own error
        # handling fails, the scheduler loop must not crash.
        logger.error("Unhandled exception in scrape cycle: %s", e)


def start():
    logger.info(
        "Scheduler starting. Running every %d minutes.",
        config.SCRAPE_INTERVAL_MINUTES,
    )

    # Run once immediately on startup, then on the interval
    run_once()
    schedule.every(config.SCRAPE_INTERVAL_MINUTES).minutes.do(run_once)

    while True:
        schedule.run_pending()
        time.sleep(1)