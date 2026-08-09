from dataclasses import dataclass
from io import BytesIO
import re

import requests

from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.research_document import ResearchDocument
from kncompanyscraper.scraper.mfn_scraper import MfnScraper


REPORT_TERMS = (
    "annual report",
    "interim report",
    "quarterly report",
    "year-end report",
    "årsredovisning",
    "delårsrapport",
    "kvartalsrapport",
    "bokslutskommuniké",
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class EvidenceSyncResult:
    releases_added: int = 0
    documents_added: int = 0


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
        releases_added = 0
        documents_added = 0
        articles = self.scraper_factory(company).get_matched_articles()

        for article in articles:
            if not self.news_repository.exists(article.url):
                self.news_repository.save(article, company.id)
                releases_added += 1

            if not _is_report(article.title):
                continue
            for attachment in article.attachments:
                if not attachment.url.lower().split("?", 1)[0].endswith(".pdf"):
                    continue
                if self.document_repository.exists(attachment.url):
                    continue
                try:
                    pdf_bytes = self.download_func(attachment.url)
                    text = self.extract_pdf_text_func(pdf_bytes)
                except Exception as exc:
                    logger.warning("Could not extract report PDF %s: %s", attachment.url, exc)
                    continue
                if not text.strip():
                    continue
                inserted = self.document_repository.save(
                    ResearchDocument(
                        id=None,
                        company_id=company.id,
                        document_type=_document_type(article.title),
                        title=attachment.title or article.title,
                        url=attachment.url,
                        published_at=article.published_at,
                        text=text,
                        source_release_url=article.url,
                        metadata={"source": "MFN attachment"},
                    )
                )
                documents_added += int(inserted is not False)

        return EvidenceSyncResult(releases_added, documents_added)


def _is_report(title: str) -> bool:
    normalized = title.casefold()
    if "invitation" in normalized or "inbjudan" in normalized:
        return False
    return any(term in normalized for term in REPORT_TERMS)


def _document_type(title: str) -> str:
    normalized = title.casefold()
    if "annual report" in normalized or "årsredovisning" in normalized:
        return "annual_report"
    return "interim_report"


def _download(url: str) -> bytes:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "").strip() for page in reader.pages[:30]]
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(page for page in pages if page))
