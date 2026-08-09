from datetime import datetime, timezone
from unittest.mock import MagicMock

from kncompanyscraper.analysis.agent.research_document_ingestion import (
    ResearchDocumentIngestionService,
)
from kncompanyscraper.models.company import Company
from kncompanyscraper.scraper.mfn_scraper import ArticleAttachment, ScrapedArticle


def test_report_pdf_attachments_are_extracted_and_persisted():
    article = ScrapedArticle(
        company="Test AB",
        slug="test",
        url="https://mfn.se/a/test/q2",
        title="Interim report Q2 2026",
        body="Release body",
        published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        attachments=[
            ArticleAttachment(
                title="Interim report Q2 2026",
                url="https://storage.mfn.se/q2.pdf",
            )
        ],
    )
    scraper = MagicMock()
    scraper.get_matched_articles.return_value = [article]
    news_repository = MagicMock()
    news_repository.exists.return_value = False
    document_repository = MagicMock()
    document_repository.exists.return_value = False
    downloader = MagicMock(return_value=b"pdf bytes")
    extractor = MagicMock(return_value="CEO statement and outlook")
    company = Company(42, "Test AB", "TEST", None, 100, None)

    result = ResearchDocumentIngestionService(
        news_repository,
        document_repository,
        scraper_factory=lambda _: scraper,
        download_func=downloader,
        extract_pdf_text_func=extractor,
    ).sync_company(company)

    assert result.releases_added == 1
    assert result.documents_added == 1
    news_repository.save.assert_called_once_with(article, 42)
    downloader.assert_called_once_with("https://storage.mfn.se/q2.pdf")
    saved = document_repository.save.call_args.args[0]
    assert saved.document_type == "interim_report"
    assert saved.text == "CEO statement and outlook"
    assert saved.source_release_url == article.url


def test_non_report_attachments_are_not_downloaded():
    article = ScrapedArticle(
        company="Test AB",
        slug="test",
        url="https://mfn.se/a/test/invitation",
        title="Invitation to presentation",
        body="Join the webcast",
        attachments=[ArticleAttachment(title="Invitation", url="https://storage.mfn.se/invite.pdf")],
    )
    scraper = MagicMock()
    scraper.get_matched_articles.return_value = [article]
    downloader = MagicMock()

    result = ResearchDocumentIngestionService(
        MagicMock(),
        MagicMock(),
        scraper_factory=lambda _: scraper,
        download_func=downloader,
        extract_pdf_text_func=MagicMock(),
    ).sync_company(Company(42, "Test AB", "TEST", None, 100, None))

    assert result.documents_added == 0
    downloader.assert_not_called()
