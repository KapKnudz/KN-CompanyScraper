import requests
from kncompanyscraper import config
from kncompanyscraper.logger import get_logger
from kncompanyscraper.http_transport import request_with_retry

logger = get_logger(__name__)

class Notifier:

    def notify_new_release(self, article):
        if not config.DISCORD_WEBHOOK_URL:
            logger.warning("No Discord webhook configured, skipping notification")
            return

        payload = {
            "content": f"**{article.company}** just released: **{article.title}**\n{article.url}"
        }

        try:
            response = request_with_retry(
                requests.post,
                source="Discord webhook",
                method="POST",
                url=config.DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Notified Discord for %s", article.company)
        except requests.RequestException as e:
            logger.error("Failed to send Discord notification: %s", e)
