"""
Integration-style tests for NewsJob using mocked scraper, repository, and notifier.

Run with: python -m pytest tests/test_news_job.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.jobs.news_job import NewsJob
from kncompanyscraper.scraper.mfn_scraper import ScrapedArticle
from kncompanyscraper.models.company import Company


def make_company() -> Company:
    return Company(
        id=1,
        name="TestCo",
        ticker="TEST",
        mfn_slug="testco",
        borsdata_id=100,
        last_updated=None,
    )


def make_article(title: str = "Test Article") -> ScrapedArticle:
    return ScrapedArticle(
        company="TestCo",
        slug="testco",
        url="https://example.com/news/1",
        title=title,
        body="Body text.",
    )


class TestNewsJob:
    def test_no_articles_returns_zero(self):
        """When scraper finds no articles, inserted count is 0."""
        repo = MagicMock()
        notifier = MagicMock()
        company = make_company()

        with patch("kncompanyscraper.jobs.news_job.MfnScraper") as MockScraper:
            MockScraper.return_value.get_matched_articles.return_value = []
            job = NewsJob(repo, notifier)
            result = job.run(company)

        assert result == 0
        repo.save.assert_not_called()
        notifier.notify_new_release.assert_not_called()

    def test_all_new_articles_saved_and_notified(self):
        """All scraped articles are new — saved and notified."""
        repo = MagicMock()
        repo.exists.return_value = False
        notifier = MagicMock()
        company = make_company()
        article = make_article()

        with patch("kncompanyscraper.jobs.news_job.MfnScraper") as MockScraper:
            MockScraper.return_value.get_matched_articles.return_value = [article]
            job = NewsJob(repo, notifier)
            result = job.run(company)

        assert result == 1
        repo.exists.assert_called_once_with(article.url)
        repo.save.assert_called_once_with(article, company.id)
        notifier.notify_new_release.assert_called_once_with(article)

    def test_duplicate_is_skipped(self):
        """Articles already in DB are skipped — not saved, not notified."""
        repo = MagicMock()
        repo.exists.return_value = True
        notifier = MagicMock()
        company = make_company()
        article = make_article()

        with patch("kncompanyscraper.jobs.news_job.MfnScraper") as MockScraper:
            MockScraper.return_value.get_matched_articles.return_value = [article]
            job = NewsJob(repo, notifier)
            result = job.run(company)

        assert result == 0
        repo.exists.assert_called_once_with(article.url)
        repo.save.assert_not_called()
        notifier.notify_new_release.assert_not_called()

    def test_mixed_new_and_existing(self):
        """Some articles are new, some exist. Only new ones are saved/notified."""
        repo = MagicMock()
        repo.exists.side_effect = lambda url: "existing" in url
        notifier = MagicMock()
        company = make_company()

        new = make_article("New Release")
        old = ScrapedArticle(
            company="TestCo",
            slug="testco",
            url="https://example.com/existing/42",
            title="Old Release",
            body="Already seen.",
        )

        with patch("kncompanyscraper.jobs.news_job.MfnScraper") as MockScraper:
            MockScraper.return_value.get_matched_articles.return_value = [new, old]
            job = NewsJob(repo, notifier)
            result = job.run(company)

        assert result == 1
        repo.save.assert_called_once_with(new, company.id)
        notifier.notify_new_release.assert_called_once_with(new)

    def test_multiple_companies_independent_runs(self):
        """Running the same job for different companies yields independent results."""
        repo = MagicMock()
        repo.exists.return_value = False
        notifier = MagicMock()

        company_a = Company(
            id=1,
            name="Alpha",
            ticker="ALP",
            mfn_slug="alpha",
            borsdata_id=10,
            last_updated=None,
        )
        company_b = Company(
            id=2,
            name="Beta",
            ticker="BET",
            mfn_slug="beta",
            borsdata_id=20,
            last_updated=None,
        )

        article_a = ScrapedArticle(
            company="Alpha",
            slug="alpha",
            url="https://example.com/a/1",
            title="Alpha News",
            body="Alpha body.",
        )
        article_b = ScrapedArticle(
            company="Beta",
            slug="beta",
            url="https://example.com/b/1",
            title="Beta News",
            body="Beta body.",
        )

        with patch("kncompanyscraper.jobs.news_job.MfnScraper") as MockScraper:
            mock_scraper_instance = MockScraper.return_value
            mock_scraper_instance.get_matched_articles.side_effect = [
                [article_a],
                [article_b],
            ]

            job = NewsJob(repo, notifier)
            result_a = job.run(company_a)
            result_b = job.run(company_b)

        assert result_a == 1
        assert result_b == 1
        repo.save.assert_any_call(article_a, company_a.id)
        repo.save.assert_any_call(article_b, company_b.id)
