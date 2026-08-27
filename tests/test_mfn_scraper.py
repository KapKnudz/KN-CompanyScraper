from datetime import datetime
from types import SimpleNamespace

from kncompanyscraper.models.company import Company
from kncompanyscraper.scraper.mfn_scraper import MfnScraper, _author_slug_from_href, _slugify


def test_slug_helpers_handle_accents_and_mfn_path_shapes():
    assert _slugify("Ångström & Co.") == "angstrom-co"
    assert _author_slug_from_href("/cis/a/acme/123", "fallback") == "acme"
    assert _author_slug_from_href("/a/acme/123", "fallback") == "acme"
    assert _author_slug_from_href("/unexpected", "fallback") == "fallback"


def test_report_title_and_published_at_helpers():
    assert MfnScraper._is_report_title("Q2 Interim Report")
    assert not MfnScraper._is_report_title("Invitation to presentation")

    page = SimpleNamespace(
        query_selector=lambda selector: SimpleNamespace(
            get_attribute=lambda name: "2026-08-24T12:30:00Z"
        )
    )
    assert MfnScraper._extract_published_at(page, "") == datetime.fromisoformat(
        "2026-08-24T12:30:00+00:00"
    )


def test_attachment_helper_deduplicates_and_resolves_relative_urls():
    links = [
        SimpleNamespace(
            get_attribute=lambda name, value=value: value,
            inner_text=lambda title=title: title,
        )
        for value, title in (
            ("https://storage.mfn.se/report.pdf", "Report"),
            ("/report.pdf", "Duplicate"),
            ("https://storage.mfn.se/report.pdf", "Duplicate"),
        )
    ]
    page = SimpleNamespace(query_selector_all=lambda selector: links)

    attachments = MfnScraper._extract_attachments(page, "https://mfn.se/a/acme/release")

    assert [item.url for item in attachments] == [
        "https://storage.mfn.se/report.pdf",
        "https://mfn.se/report.pdf",
    ]
