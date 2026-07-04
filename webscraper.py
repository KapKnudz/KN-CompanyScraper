from playwright.sync_api import sync_playwright

COMPANIES_TO_TRACK = [
    "norsk-titanium",
    "volvo-cars",
    "ericsson",
]

FEED_URL = "https://mfn.se/all/s/nordic?limit=435"


def scrape_detail_page(page, url):
    full_url = f"https://mfn.se{url}" if url.startswith("/") else url
    page.goto(full_url, timeout=20000)
    page.wait_for_load_state("networkidle")

    try:
        title = page.query_selector("h1").inner_text()
    except:
        title = "N/A"

    try:
        body_el = page.query_selector(".release-body, article, .mfn-release, main")
        body = body_el.inner_text() if body_el else "N/A"
    except:
        body = "N/A"

    return {"title": title, "body": body, "url": full_url}


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("Loading feed...")
    page.goto(FEED_URL, timeout=20000)
    page.wait_for_load_state("networkidle")

    author_links = page.query_selector_all("a.author-link")
    print(f"Found {len(author_links)} feed items")

    matched = []
    for link_el in author_links:
        author_slug = link_el.get_attribute("author")
        company_name = link_el.inner_text().strip()

        if author_slug in COMPANIES_TO_TRACK:
            try:
                parent = link_el.evaluate_handle(
                    "el => el.closest('.mfn-feed-item, .feed-item, [class*=\"item\"]')"
                )
                # ✅ Fixed selector — matches the item-link class specifically
                article_link = parent.query_selector("a.title-link.item-link")
                href = article_link.get_attribute("href") if article_link else None
            except:
                href = None

            if href:
                print(f"  Matched: {company_name} ({author_slug}) -> {href}")
                matched.append({"company": company_name, "slug": author_slug, "href": href})
            else:
                print(f"  Matched {company_name} but couldn't find article link")

    print(f"\n{len(matched)} articles matched. Scraping detail pages...\n")

    results = []
    for match in matched:
        print(f"Scraping: {match['company']} -> {match['href']}")
        detail = scrape_detail_page(page, match["href"])
        detail["company"] = match["company"]
        results.append(detail)

    browser.close()

for r in results:
    print(f"\n{'='*60}")
    print(f"Company : {r['company']}")
    print(f"URL     : {r['url']}")
    print(f"Title   : {r['title']}")
    print(f"Body preview: {r['body'][:300]}...")