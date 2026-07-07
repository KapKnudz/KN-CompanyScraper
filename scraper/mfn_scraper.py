from dataclasses import dataclass
from playwright.sync_api import sync_playwright, Page
from scraper.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScrapedArticle:
    company: str
    slug: str
    url: str
    title: str
    body: str


class MfnScraper:
    FEED_URL = "https://mfn.se/all/s/nordic?limit=435"
    BASE_URL = "https://mfn.se"

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
        logger.info("Loading feed: %s", self.FEED_URL)
        page.goto(self.FEED_URL, timeout=20000)
        page.wait_for_load_state("domcontentloaded")

        author_links = page.query_selector_all("a.author-link")
        logger.info("Found %d feed items", len(author_links))

        matched = []
        for i, link_el in enumerate(author_links):
            logger.info("Processing feed item %s/%s", i + 1, len(author_links))

            author_slug = link_el.get_attribute("author")
            if author_slug != self.company.mfn_slug:
                continue

            logger.info("Found company match: %s", author_slug)

            company_name = link_el.inner_text().strip()
            href = self._extract_article_href(link_el)

            if href:
                logger.info("Matched: %s (%s) -> %s", company_name, author_slug, href)
                matched.append({"company": company_name, "slug": author_slug, "href": href})
            else:
                logger.warning("Matched %s but couldn't find article link", company_name)

        return matched

    def _extract_article_href(self, link_el) -> str | None:
        try:
            parent = link_el.evaluate_handle(
                "el => el.closest('.mfn-feed-item, .feed-item, [class*=\"item\"]')"
            )
            article_link = parent.query_selector("a.title-link.item-link")
            return article_link.get_attribute("href") if article_link else None
        except Exception as e:
            logger.warning("Failed extracting href: %s", e)
            return None

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

        return {"title": title, "body": body, "url": full_url}