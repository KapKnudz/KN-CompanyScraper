from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import re
from urllib.parse import urljoin

import requests

from kncompanyscraper.logger import get_logger
from kncompanyscraper.http_transport import request_with_retry
from kncompanyscraper.models.research_document import ResearchDocument
from kncompanyscraper.scraper.mfn_scraper import MfnScraper
from kncompanyscraper.constants import REPORT_TITLE_TERMS


REPORT_TERMS = REPORT_TITLE_TERMS

logger = get_logger(__name__)


@dataclass(frozen=True)
class EvidenceSyncResult:
    releases_added: int = 0
    documents_added: int = 0
    feed_checked_at: datetime | None = None
    feed_items: int = 0
    detail_pages_visited: int = 0
    documents_updated: int = 0


class ResearchDocumentIngestionService:
    def __init__(
        self,
        news_repository,
        document_repository,
        scraper_factory=None,
        download_func=None,
        extract_pdf_text_func=None,
    ):
        self.news_repository = news_repository
        self.document_repository = document_repository
        self.scraper_factory = scraper_factory or MfnScraper
        self.download_func = download_func or _download
        self.extract_pdf_text_func = extract_pdf_text_func or _extract_pdf_text

    def sync_company(self, company) -> EvidenceSyncResult:
        articles = self.scraper_factory(company).get_matched_articles()
        return self._persist_articles(company, articles)

    def sync_company_delta(self, company) -> EvidenceSyncResult:
        """Check the MFN feed first, then scrape only unseen release URLs."""
        scraper = self.scraper_factory(company)
        feed_items = scraper.discover_feed()
        existing_urls = self.news_repository.list_urls_for_company(company.id)
        unseen_items = [
            item
            for item in feed_items
            if _feed_item_url(item) not in existing_urls
        ]
        checked_at = datetime.now(timezone.utc)
        self.news_repository.record_feed_check(
            company.id,
            checked_at,
            discovered_count=len(feed_items),
            unseen_count=len(unseen_items),
        )
        articles = scraper.scrape_details(unseen_items) if unseen_items else []
        result = self._persist_articles(company, articles)
        return EvidenceSyncResult(
            result.releases_added,
            result.documents_added,
            checked_at,
            len(feed_items),
            len(unseen_items),
            result.documents_updated,
        )

    def _persist_articles(self, company, articles) -> EvidenceSyncResult:
        releases_added = 0
        documents_added = 0

        for article in articles:
            if not self.news_repository.exists(article.url):
                self.news_repository.save(article, company.id)
                releases_added += 1

            if not _is_report(article.title):
                continue
            for attachment in article.attachments:
                if not attachment.url.lower().split("?", 1)[0].endswith(".pdf"):
                    continue
                documents_added += int(
                    self._ingest_report_pdf(
                        company,
                        title=attachment.title or article.title,
                        url=attachment.url,
                        published_at=article.published_at,
                        source_release_url=article.url,
                        metadata={
                            "source": "MFN attachment",
                            **_normalized_report_metadata(
                                article.title, article.published_at
                            ),
                        },
                    )
                )

        documents_updated = self.backfill_report_metadata(company)
        return EvidenceSyncResult(
            releases_added,
            documents_added,
            documents_updated=documents_updated,
        )

    def backfill_report_metadata(self, company) -> int:
        """Fill missing report year/period fields on stored documents."""
        releases_by_url = {
            release.url: release
            for release in self.news_repository.list_for_company(company.id)
        }
        updated = 0
        for document in self.document_repository.list_for_company(company.id):
            if document.id is None:
                continue
            release = releases_by_url.get(document.source_release_url)
            inferred = _backfill_report_metadata(
                document,
                release.title if release is not None else None,
            )
            additions = {
                key: value
                for key, value in inferred.items()
                if key not in (document.metadata or {})
            }
            if additions:
                updated += int(
                    self.document_repository.update_metadata(document.id, additions)
                )
        return updated

    def ingest_authoritative_report(
        self,
        company,
        *,
        title: str,
        url: str,
        published_at: datetime | None,
        source_release_url: str | None = None,
        document_type: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """Ingest a manually identified authoritative report PDF.

        This is intentionally explicit: it repairs a known missing report slot
        without changing or deduplicating the upstream release table.
        """
        report_metadata = {
            "source": "authoritative report repair",
            "authoritative_source": True,
        }
        report_metadata.update(_normalized_report_metadata(title, published_at))
        report_metadata.update(metadata or {})
        return self._ingest_report_pdf(
            company,
            title=title,
            url=url,
            published_at=published_at,
            source_release_url=source_release_url,
            document_type=document_type,
            metadata=report_metadata,
        )

    def _ingest_report_pdf(
        self,
        company,
        *,
        title: str,
        url: str,
        published_at: datetime | None,
        source_release_url: str | None,
        document_type: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        if self.document_repository.exists(url):
            return False
        try:
            pdf_bytes = self.download_func(url)
            text = self.extract_pdf_text_func(pdf_bytes)
        except Exception as exc:
            logger.warning("Could not extract report PDF %s: %s", url, exc)
            return False
        if not text.strip():
            return False
        report_metadata = dict(metadata or {})
        normalized_metadata = _normalized_report_metadata(title, published_at)
        normalized_metadata.update(report_metadata)
        inserted = self.document_repository.save(
            ResearchDocument(
                id=None,
                company_id=company.id,
                document_type=document_type or _document_type(title),
                title=title,
                url=url,
                published_at=published_at,
                text=text,
                source_release_url=source_release_url,
                metadata=normalized_metadata,
            )
        )
        return inserted is not False


def _feed_item_url(item: dict) -> str:
    value = item.get("url") or item.get("href")
    if not value:
        raise ValueError("MFN feed item has no release URL")
    return urljoin(MfnScraper.BASE_URL, value)


def _is_report(title: str) -> bool:
    normalized = title.casefold()
    if "invitation" in normalized or "inbjudan" in normalized:
        return False
    return any(term in normalized for term in REPORT_TERMS) or bool(
        re.search(r"\b(?:q[1-4]|h[12])\s*(?:report|rapport)\b", normalized)
    )


def _document_type(title: str) -> str:
    normalized = title.casefold()
    if any(
        term in normalized
        for term in (
            "annual report",
            "årsredovisning",
            "year-end report",
            "bokslutskommuniké",
        )
    ):
        return "annual_report"
    return "interim_report"


def _normalized_report_metadata(title: str, published_at: datetime | None) -> dict:
    """Return unambiguous report-period fields without guessing fiscal periods."""
    normalized = title.casefold()
    if not _is_report(title):
        return {}

    year_match = re.search(r"\b(20\d{2})\b", title)
    year = int(year_match.group(1)) if year_match else None
    period = _report_period(normalized)

    # A quarter/half-year title without a year can use its publication year.
    # An annual report published in the following calendar year cannot.
    if year is None and period is not None and published_at is not None:
        year = published_at.year

    metadata = {}
    if year is not None:
        metadata["report_year"] = year
    if period is not None:
        metadata["report_period"] = period
    return metadata


def _report_period(title: str) -> int | None:
    quarter_match = re.search(
        r"\bq([1-4])\b|\b([1-4])q\b|\b(?:quarter|kvartal)\s*([1-4])\b",
        title,
    )
    if quarter_match:
        return int(next(value for value in quarter_match.groups() if value))
    if re.search(r"\bh[12]\b|\bhalf[- ]year\b|\bhalvår\b", title):
        return 2 if not re.search(r"\bh2\b|\bsecond half\b|\bandra halvåret\b", title) else 4

    if any(month in title for month in ("march", "mars")):
        return 1
    if any(month in title for month in ("june", "jun", "juni")):
        return 2
    if any(month in title for month in ("september", "sep")):
        return 3
    if any(month in title for month in ("december", "dec")):
        return 4
    return 4 if _document_type(title) == "annual_report" else None


def _backfill_report_metadata(document, release_title: str | None) -> dict:
    titles = [title for title in (document.title, release_title) if title]
    years = {
        int(match.group(1))
        for title in titles
        if (match := re.search(r"\b(20\d{2})\b", title))
    }
    periods = {
        period
        for title in titles
        if (period := _report_period(title.casefold())) is not None
    }
    if not periods and document.document_type == "annual_report":
        periods.add(4)

    metadata = {}
    if len(years) == 1:
        metadata["report_year"] = next(iter(years))
    if len(periods) == 1:
        metadata["report_period"] = next(iter(periods))
    if (
        "report_year" not in metadata
        and not years
        and metadata.get("report_period") in (1, 2, 3)
        and document.published_at is not None
    ):
        metadata["report_year"] = document.published_at.year
    return metadata


def _download(url: str) -> bytes:
    response = request_with_retry(
        requests.get,
        source="research document",
        method="GET",
        url=url,
        timeout=60,
    )
    response.raise_for_status()
    return response.content


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "").strip() for page in reader.pages[:30]]
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(page for page in pages if page))
