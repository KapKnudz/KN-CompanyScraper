from datetime import datetime, timezone
from unittest.mock import MagicMock

from kncompanyscraper.analysis.agent.research_document_ingestion import (
    ResearchDocumentIngestionService,
)
from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
from kncompanyscraper.models.company import Company
from kncompanyscraper.models.research_document import ResearchDocument
from kncompanyscraper.scraper.mfn_scraper import ArticleAttachment, ScrapedArticle


class InMemoryDocumentRepository:
    def __init__(self, documents):
        self.documents = documents
        self.update_calls = []

    def list_for_company(self, company_id, as_of=None, limit=None):
        return [item for item in self.documents if item.company_id == company_id]

    def update_metadata(self, document_id, metadata):
        document = next(item for item in self.documents if item.id == document_id)
        document.metadata.update(metadata)
        self.update_calls.append((document_id, metadata))
        return True


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
    assert saved.metadata["report_year"] == 2026
    assert saved.metadata["report_period"] == 2


def test_ambiguous_interim_title_does_not_guess_report_period():
    article = ScrapedArticle(
        company="Test AB",
        slug="test",
        url="https://mfn.se/a/test/interim",
        title="Interim report 2026",
        body="Release body",
        published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        attachments=[ArticleAttachment("Interim report", "https://storage.mfn.se/q.pdf")],
    )
    scraper = MagicMock()
    scraper.get_matched_articles.return_value = [article]
    news_repository = MagicMock()
    news_repository.exists.return_value = False
    document_repository = MagicMock()
    document_repository.exists.return_value = False

    ResearchDocumentIngestionService(
        news_repository,
        document_repository,
        scraper_factory=lambda _: scraper,
        download_func=MagicMock(return_value=b"pdf"),
        extract_pdf_text_func=MagicMock(return_value="report text"),
    ).sync_company(Company(42, "Test AB", "TEST", None, 100, None))

    saved = document_repository.save.call_args.args[0]
    assert saved.metadata["report_year"] == 2026
    assert "report_period" not in saved.metadata


def test_backfill_recognizes_english_and_swedish_numbered_quarters_idempotently():
    documents = InMemoryDocumentRepository(
        [
            ResearchDocument(
                id=1,
                company_id=153,
                document_type="interim_report",
                title="AVTECH Interim Report Quarter 2 2026 EN",
                url="https://storage.mfn.se/quarter-2-en.pdf",
                published_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
                text="report",
                metadata={"source": "MFN attachment"},
            ),
            ResearchDocument(
                id=2,
                company_id=153,
                document_type="interim_report",
                title="AVTECH Delårsrapport Kvartal 1 2026 SV",
                url="https://storage.mfn.se/kvartal-1-sv.pdf",
                published_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
                text="rapport",
                metadata={"source": "MFN attachment"},
            ),
        ]
    )
    news_repository = MagicMock()
    news_repository.list_for_company.return_value = []
    ingestion = ResearchDocumentIngestionService(news_repository, documents)
    company = Company(153, "Avtech", "AVT B", "avtech-sweden", 153, None)

    assert ingestion.backfill_report_metadata(company) == 2
    assert documents.documents[0].metadata["report_period"] == 2
    assert documents.documents[0].metadata["report_year"] == 2026
    assert documents.documents[1].metadata["report_period"] == 1
    assert documents.documents[1].metadata["report_year"] == 2026
    assert ingestion.backfill_report_metadata(company) == 0
    assert len(documents.update_calls) == 2


def test_backfill_uses_linked_release_title_and_does_not_overwrite_metadata():
    document = ResearchDocument(
        id=7,
        company_id=114,
        document_type="annual_report",
        title="MSAB - ÅR 2025",
        url="https://storage.mfn.se/msab-2025.pdf",
        published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        text="report",
        source_release_url="https://mfn.se/a/msab/annual-2025",
        metadata={"source": "MFN attachment", "report_period": 4},
    )
    documents = InMemoryDocumentRepository([document])
    news_repository = MagicMock()
    news_repository.list_for_company.return_value = [
        type(
            "Release",
            (),
            {
                "url": document.source_release_url,
                "title": "MSAB publishes Annual Report for 2025",
            },
        )()
    ]

    updated = ResearchDocumentIngestionService(
        news_repository, documents
    ).backfill_report_metadata(
        Company(114, "Micro Systemation AB", "MSAB B", "micro-systemation", 114, None)
    )

    assert updated == 1
    assert document.metadata["report_year"] == 2025
    assert document.metadata["report_period"] == 4
    assert documents.update_calls == [(7, {"report_year": 2025})]


def test_backfill_does_not_guess_when_attachment_and_release_years_conflict():
    document = ResearchDocument(
        id=8,
        company_id=42,
        document_type="interim_report",
        title="Interim Report Quarter 2 2025",
        url="https://storage.mfn.se/conflict.pdf",
        published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        text="report",
        source_release_url="https://mfn.se/a/test/conflict",
        metadata={},
    )
    documents = InMemoryDocumentRepository([document])
    news_repository = MagicMock()
    news_repository.list_for_company.return_value = [
        type(
            "Release",
            (),
            {"url": document.source_release_url, "title": "Interim Report Q2 2026"},
        )()
    ]

    ResearchDocumentIngestionService(
        news_repository, documents
    ).backfill_report_metadata(
        Company(42, "Test AB", "TEST", None, 42, None)
    )

    assert document.metadata == {"report_period": 2}


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


def test_delta_sync_with_no_unseen_feed_urls_visits_no_detail_pages():
    scraper = MagicMock()
    scraper.discover_feed.return_value = [
        {"url": "https://mfn.se/a/test/seen", "title": "Seen"}
    ]
    news_repository = MagicMock()
    news_repository.list_urls_for_company.return_value = {"https://mfn.se/a/test/seen"}

    result = ResearchDocumentIngestionService(
        news_repository,
        MagicMock(),
        scraper_factory=lambda _: scraper,
    ).sync_company_delta(Company(42, "Test AB", "TEST", None, 100, None))

    assert result.feed_items == 1
    assert result.detail_pages_visited == 0
    scraper.scrape_details.assert_not_called()
    news_repository.record_feed_check.assert_called_once()


def test_delta_sync_scrapes_one_unseen_release_and_downloads_only_unseen_pdf():
    article = ScrapedArticle(
        company="Test AB",
        slug="test",
        url="https://mfn.se/a/test/unseen",
        title="Interim report Q2 2026",
        body="Release body",
        attachments=[
            ArticleAttachment("Already stored", "https://storage.mfn.se/old.pdf"),
            ArticleAttachment("New report", "https://storage.mfn.se/new.pdf"),
            ArticleAttachment("Not a PDF", "https://storage.mfn.se/data.csv"),
        ],
    )
    scraper = MagicMock()
    scraper.discover_feed.return_value = [
        {"href": "/a/test/seen", "title": "Seen"},
        {"href": "/a/test/unseen", "title": "Interim report Q2 2026"},
    ]
    scraper.scrape_details.return_value = [article]
    news_repository = MagicMock()
    news_repository.list_urls_for_company.return_value = {"https://mfn.se/a/test/seen"}
    news_repository.exists.return_value = False
    documents = MagicMock()
    documents.exists.side_effect = lambda url: url.endswith("old.pdf")
    downloader = MagicMock(return_value=b"pdf")
    extractor = MagicMock(return_value="report text")

    result = ResearchDocumentIngestionService(
        news_repository,
        documents,
        scraper_factory=lambda _: scraper,
        download_func=downloader,
        extract_pdf_text_func=extractor,
    ).sync_company_delta(Company(42, "Test AB", "TEST", None, 100, None))

    assert result.releases_added == 1
    assert result.documents_added == 1
    scraper.scrape_details.assert_called_once_with(
        [{"href": "/a/test/unseen", "title": "Interim report Q2 2026"}]
    )
    downloader.assert_called_once_with("https://storage.mfn.se/new.pdf")
    news_repository.record_feed_check.assert_called_once_with(
        42,
        result.feed_checked_at,
        discovered_count=2,
        unseen_count=1,
    )


def test_authoritative_msab_2024_report_repair_fills_annual_selection_slot():
    stored_documents = [
        ResearchDocument(
            id=1,
            company_id=114,
            document_type="annual_report",
            title="MSAB Annual Report 2025",
            url="https://investors.msab.com/files/Main/20675/4290000/msab--annual-report-2025.pdf",
            published_at=datetime(2026, 4, 21, 13, 0, tzinfo=timezone.utc),
            text="2025 annual report",
            source_release_url="https://investors.msab.com/investors/newsroom/press-releases/2026/annual-report-2025/",
            metadata={"report_year": 2025, "report_period": 4},
        )
    ]
    document_repository = MagicMock()
    document_repository.exists.return_value = False
    document_repository.save.side_effect = lambda document: stored_documents.append(
        ResearchDocument(**{**document.__dict__, "id": 2})
    ) or True
    document_repository.list_for_company.side_effect = (
        lambda company_id, as_of=None, limit=None: list(stored_documents)
    )
    ingestion = ResearchDocumentIngestionService(
        MagicMock(),
        document_repository,
        download_func=MagicMock(return_value=b"authoritative pdf"),
        extract_pdf_text_func=MagicMock(return_value="complete 2024 annual report text"),
    )

    repaired = ingestion.ingest_authoritative_report(
        Company(114, "Micro Systemation AB", "MSAB B", "micro-systemation", 114, None),
        title="MSAB Annual Report 2024",
        url="https://mb.cision.com/Main/20675/4138510/3400464.pdf",
        published_at=datetime(2025, 4, 23, 13, 0, tzinfo=timezone.utc),
        source_release_url="https://investors.msab.com/investors/newsroom/press-releases/2025/msabs-annual-report-2024/",
    )

    evidence = ResearchEvidenceBuilder(
        document_repository,
        MagicMock(list_for_company=lambda *args, **kwargs: []),
        MagicMock(list_for_company=lambda *args, **kwargs: []),
        MagicMock(),
    ).build(company_id=114, as_of=datetime(2026, 9, 2).date())
    repaired_document = stored_documents[1]

    assert repaired is True
    assert repaired_document.metadata["authoritative_source"] is True
    assert repaired_document.metadata["report_year"] == 2024
    assert repaired_document.metadata["report_period"] == 4
    assert [item.source_id for item in evidence.documents[:2]] == [
        "document:1",
        "document:2",
    ]
    assert not any("broken fiscal year" in item for item in evidence.missing_information)
