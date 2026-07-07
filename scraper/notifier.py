import requests
from scraper import config
from scraper.logger import get_logger
from scraper.mfn_scraper import ScrapedArticle

logger = get_logger(__name__)

class Notifier:

    def notify_new_release(article: ScrapedArticle):
        if not config.DISCORD_WEBHOOK_URL:
            logger.warning("No Discord webhook configured, skipping notification")
            return

        payload = {
            "content": f"**{article.company}** just released: **{article.title}**\n{article.url}"
        }

        try:
            response = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Notified Discord for %s", article.company)
        except requests.RequestException as e:
            logger.error("Failed to send Discord notification: %s", e)