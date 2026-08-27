from unittest.mock import patch

import requests

from kncompanyscraper.scraper.notifier import Notifier


def test_notifier_skips_when_webhook_is_not_configured():
    with patch("kncompanyscraper.scraper.notifier.config.DISCORD_WEBHOOK_URL", None), patch(
        "kncompanyscraper.scraper.notifier.request_with_retry"
    ) as request:
        Notifier().notify_new_release(type("Article", (), {"company": "Acme", "title": "News", "url": "url"})())

    request.assert_not_called()


def test_notifier_swallow_request_failures():
    article = type("Article", (), {"company": "Acme", "title": "News", "url": "url"})()
    with patch("kncompanyscraper.scraper.notifier.config.DISCORD_WEBHOOK_URL", "https://discord"), patch(
        "kncompanyscraper.scraper.notifier.request_with_retry",
        side_effect=requests.RequestException("offline"),
    ):
        Notifier().notify_new_release(article)
