from dataclasses import dataclass, field
from datetime import datetime
import re
import unicodedata
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, Page
from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.company import Company

logger = get_logger(__name__)


@dataclass
class ArticleAttachment:
    title: str
    url: str


@dataclass
class ScrapedArticle:
    company: str
    slug: str
    url: str
    title: str
    body: str
    published_at: datetime | None = None
    attachments: list[ArticleAttachment] = field(default_factory=list)


class MfnScraper:
    BASE_URL = "https://mfn.se"
    MAX_ARTICLES = 24
    REPORT_TITLE_TERMS = (
        "annual report",
        "interim report",
        "quarterly report",
        "year-end report",
        "årsredovisning",
        "delårsrapport",
        "kvartalsrapport",
        "bokslutskommuniké",
    )

    def __init__(self, company: Company, headless: bool = True):
        self.company = company
        self.headless = headless

    def get_matched_articles(self) -> list[ScrapedArticle]:
        with sync_playwright() as p:
            logger.info("Launching browser")
            browser = p.chromium.launch(headless=self.headless)

            logger.info("Creating page")
            page = browser.new_page()

            try:
                logger.info("Starting feed scrape")
                matches = self._scrape_feed(page)
                logger.info("Feed scrape finished. Matches: %d", len(matches))

                logger.info("Starting detail scrape")
                results = self._scrape_details(page, matches)
                logger.info("Detail scrape finished. Results: %d", len(results))
            finally:
                logger.info("Closing browser")
                browser.close()
                logger.info("Browser closed")

        logger.info("Returning results")
        return results

    def _scrape_feed(self, page: Page) -> list[dict]:
        author_slug = self.company.mfn_slug or _slugify(self.company.name)
        feed_url = f"{self.BASE_URL}/all/a/{author_slug}"
        logger.info("Loading feed: %s", feed_url)
        page.goto(feed_url, timeout=20000)
        page.wait_for_load_state("domcontentloaded")

        article_links = page.query_selector_all("a.title-link.item-link")
        logger.info("Found %d feed items", len(article_links))

        matched = []
        for link_el in article_links:
            href = link_el.get_attribute("href")
            if not href:
                continue

            path_parts = href.strip("/").split("/")
            item_author_slug = (
                path_parts[2]
                if len(path_parts) >= 4 and path_parts[:2] == ["cis", "a"]
                else path_parts[1] if len(path_parts) >= 3 else author_slug
            )
            title = link_el.inner_text().strip()
            matched.append(
                {
                    "company": self.company.name,
                    "slug": item_author_slug,
                    "href": href,
                    "title": title,
                }
            )

        reports = [item for item in matched if self._is_report_title(item["title"])]
        other = [item for item in matched if not self._is_report_title(item["title"])]
        selected = (reports + other)[: self.MAX_ARTICLES]
        logger.info("Selected %d evidence items from %d feed items", len(selected), len(matched))
        return selected

    @classmethod
    def _is_report_title(cls, title: str) -> bool:
        normalized = title.casefold()
        return any(term in normalized for term in cls.REPORT_TITLE_TERMS)

    def _scrape_details(self, page: Page, matches: list[dict]) -> list[ScrapedArticle]:
        logger.info("Entered _scrape_details with %d matches", len(matches))
        results = []
        for match in matches:
            try:
                detail = self._scrape_detail_page(page, match["href"])
                results.append(ScrapedArticle(
                    company=match["company"],
                    slug=match["slug"],
                    url=detail["url"],
                    title=detail["title"],
                    body=detail["body"],
                    published_at=detail["published_at"],
                    attachments=detail["attachments"],
                ))
            except Exception as e:
                logger.error("Failed scraping %s (%s): %s", match["company"], match["href"], e)
        return results

    def _scrape_detail_page(self, page: Page, url: str) -> dict:
        full_url = f"{self.BASE_URL}{url}" if url.startswith("/") else url
        logger.info("Scraping detail page: %s", full_url)

        page.goto(full_url, timeout=20000)
        page.wait_for_load_state("domcontentloaded")

        title_el = page.query_selector("h1")
        title = title_el.inner_text() if title_el else "N/A"

        body_el = page.query_selector(".release-body, article, .mfn-release, main")
        body = body_el.inner_text() if body_el else "N/A"

        return {
            "title": title,
            "body": body,
            "url": full_url,
            "published_at": self._extract_published_at(page, body),
            "attachments": self._extract_attachments(page, full_url),
        }

    @staticmethod
    def _extract_published_at(page: Page, body: str) -> datetime | None:
        time_el = page.query_selector("time")
        if time_el:
            raw = time_el.get_attribute("datetime") or time_el.inner_text()
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                pass

        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\b", body)
        if match:
            return datetime.strptime(
                f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=ZoneInfo("Europe/Stockholm"))
        return None

    @staticmethod
    def _extract_attachments(page: Page, page_url: str) -> list[ArticleAttachment]:
        attachments = []
        seen = set()
        for link in page.query_selector_all('a[href*="storage.mfn.se"], a[href$=".pdf"]'):
            href = link.get_attribute("href")
            if not href:
                continue
            url = urljoin(page_url, href)
            if url in seen:
                continue
            seen.add(url)
            attachments.append(ArticleAttachment(title=link.inner_text().strip(), url=url))
        return attachments


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
