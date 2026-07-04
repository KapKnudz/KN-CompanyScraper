from scraper import scheduler
from scraper.logger import get_logger

logger = get_logger("main")

if __name__ == "__main__":
    logger.info("Starting KN-CompanyScraper")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully (Ctrl+C received)")