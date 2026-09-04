from datetime import date, datetime, timezone

from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.models.insider_transaction import InsiderTransaction
from kncompanyscraper.models.research_document import ResearchDocument
from kncompanyscraper.repositories.news_repository import NewsRelease


class StubDocumentRepository:
    def list_for_company(self, company_id, as_of=None, limit=None):
        return [
            ResearchDocument(
                id=11,
                company_id=company_id,
                document_type="interim_report",
                title="Q2 report",
                url="https://storage.mfn.se/q2.pdf",
                published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
                text="CEO outlook from the attached report.",
                metadata={
                    "structured_financial_values": [
                        {"metric": "revenue", "period": "2026-H1", "value": 210.0}
                    ]
                },
            )
        ]


class StubNewsRepository:
    def list_for_company(self, company_id, as_of=None, limit=None):
        return [
            NewsRelease(
                id=21,
                company_id=company_id,
                slug="test",
                url="https://mfn.se/a/test/q2",
                title="Interim report Q2 2026",
                body="Release body.",
                published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )
        ]


class StubInsiderRepository:
    def list_for_company(self, company_id, since=None, limit=None):
        return [
            InsiderTransaction(
                person_name="Ada Example",
                person_role="CEO",
                transaction_type="Buy",
                shares=1_000,
                price_per_share=10.0,
                total_value=10_000.0,
                transaction_date=date(2025, 1, 2),
                source="borsdata",
                currency="SEK",
            )
        ]


class StubValuationRepository:
    def get_stock_price_on_or_after(self, company_id, target_date, max_age_days=None):
        return StockPrice(date=date(2025, 1, 2), close=10.0, currency="SEK")

    def get_stock_price_on_date(self, company_id, target_date, max_age_days=None):
        prices = {
            date(2025, 4, 2): 12.0,
            date(2025, 7, 1): 9.0,
            date(2026, 1, 2): 15.0,
        }
        close = prices.get(target_date)
        return StockPrice(target_date, close, "SEK") if close is not None else None


def test_research_evidence_contains_citable_documents_and_raw_insider_outcomes():
    evidence = ResearchEvidenceBuilder(
        StubDocumentRepository(),
        StubNewsRepository(),
        StubInsiderRepository(),
        StubValuationRepository(),
    ).build(company_id=42, as_of=date(2026, 8, 9))

    assert [document.source_id for document in evidence.documents] == [
        "document:11",
        "news:21",
    ]
    assert evidence.documents[0].text == "CEO outlook from the attached report."
    assert evidence.documents[0].url == "https://storage.mfn.se/q2.pdf"
    assert evidence.documents[0].published_at == "2026-07-15T00:00:00+00:00"
    assert evidence.documents[0].structured_financial_values == [
        {"metric": "revenue", "period": "2026-H1", "value": 210.0, "period_end": None}
    ]

    transaction = evidence.insider_transactions[0]
    assert transaction.source_id.startswith("insider:")
    assert transaction.transaction_type == "Buy"
    assert transaction.returns == {
        "90d": 0.2,
        "180d": -0.1,
        "365d": 0.5,
    }
    assert "price return" in evidence.insider_methodology.lower()
    assert "Free-float percentage is unavailable" in evidence.missing_information
    assert "Named large-holder coverage is unavailable" in evidence.missing_information
    assert "Ownership-change history is unavailable" in evidence.missing_information


def test_research_evidence_does_not_score_insider_activity():
    evidence = ResearchEvidenceBuilder(
        StubDocumentRepository(),
        StubNewsRepository(),
        StubInsiderRepository(),
        StubValuationRepository(),
    ).build(company_id=42, as_of=date(2025, 2, 1))

    payload = evidence.to_dict()
    assert "score" not in payload
    assert payload["insider_status"] == "available"
    assert payload["insider_event_count"] == 1
    assert payload["insider_transactions"][0]["returns"] == {
        "90d": None,
        "180d": None,
        "365d": None,
    }


def test_research_evidence_can_reconstruct_an_original_source_packet():
    evidence = ResearchEvidenceBuilder(
        StubDocumentRepository(),
        StubNewsRepository(),
        StubInsiderRepository(),
        StubValuationRepository(),
    ).build(company_id=42, as_of=date(2026, 8, 9), filter_ids={"news:21"})

    assert [item.source_id for item in evidence.documents] == ["news:21"]
    assert evidence.insider_transactions == []


def test_original_packet_excludes_uncited_current_liquidity_evidence():
    class LiquidityBuilder:
        class Result:
            def to_dict(self):
                return {
                    "source_ids": ["liquidity:borsdata:42:2026-08-09:20d"],
                    "status": "partial",
                }

        def build(self, company_id, as_of, filter_ids=None):
            return self.Result()

    evidence = ResearchEvidenceBuilder(
        StubDocumentRepository(),
        StubNewsRepository(),
        StubInsiderRepository(),
        StubValuationRepository(),
        LiquidityBuilder(),
    ).build(company_id=42, as_of=date(2026, 8, 9), filter_ids={"news:21"})

    assert evidence.ownership_liquidity == {}


class _Documents:
    def __init__(self, documents):
        self.documents = documents

    def list_for_company(self, company_id, as_of=None, limit=None):
        return list(self.documents)


class _News:
    def __init__(self, releases):
        self.releases = releases

    def list_for_company(self, company_id, as_of=None, limit=None):
        return list(self.releases)


class _NoInsiders:
    def list_for_company(self, company_id, since=None, limit=None):
        return []


def _report(document_id, document_type, title, year, period, published_day):
    return ResearchDocument(
        id=document_id,
        company_id=42,
        document_type=document_type,
        title=title,
        url=f"https://storage.mfn.se/{document_id}.pdf",
        published_at=datetime(year, 7, published_day, tzinfo=timezone.utc),
        text=f"exact text for {document_id}",
        source_release_url=f"https://mfn.se/release/{document_id}",
        metadata={"report_year": year, "report_period": period},
    )


def _evidence(documents, releases=()):
    return ResearchEvidenceBuilder(
        _Documents(documents),
        _News(releases),
        _NoInsiders(),
        StubValuationRepository(),
    ).build(company_id=42, as_of=date(2026, 12, 31))


def test_document_selection_uses_two_annual_and_two_comparable_interim_reports():
    documents = [
        _report(1, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(2, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(3, "annual_report", "Annual report 2023", 2023, 4, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
        _report(5, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(6, "interim_report", "Interim report Q1 2026", 2026, 1, 15),
    ]

    evidence = _evidence(documents)

    assert [item.source_id for item in evidence.documents] == [
        "document:2",
        "document:1",
        "document:5",
        "document:4",
    ]
    assert evidence.missing_information == [
        "No insider transactions are stored for the five-year lookback",
        "Free-float percentage is unavailable",
        "Named large-holder coverage is unavailable",
        "Ownership-change history is unavailable",
    ]


def test_selected_report_text_is_lossless_even_when_longer_than_legacy_limit():
    long_text = "full-report-text-" * 2_000
    document = _report(9, "annual_report", "Annual report 2025", 2025, 4, 15)
    document.text = long_text

    evidence = _evidence([document])

    assert evidence.documents[0].text == long_text


def test_document_selection_reports_missing_annual_history_without_filling_the_slot():
    evidence = _evidence([
        _report(1, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(2, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
    ])

    assert [item.source_id for item in evidence.documents] == ["document:1", "document:2"]
    assert any("broken fiscal year" in item for item in evidence.missing_information)


def test_document_selection_reports_missing_comparable_interim_history():
    evidence = _evidence([
        _report(1, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(2, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
    ])

    assert [item.source_id for item in evidence.documents] == [
        "document:2",
        "document:1",
        "document:3",
    ]
    assert any("comparable prior-year interim" in item for item in evidence.missing_information)


def test_ambiguous_interim_is_not_used_as_a_comparable_report():
    evidence = _evidence([
        _report(1, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(2, "annual_report", "Annual report 2025", 2025, 4, 15),
        ResearchDocument(
            id=3,
            company_id=42,
            document_type="interim_report",
            title="Interim report 2026",
            url="https://storage.mfn.se/3.pdf",
            published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            text="ambiguous interim",
            metadata={"report_year": 2026},
        ),
    ])

    assert "document:3" not in [item.source_id for item in evidence.documents]
    assert any("ambiguous period" in item for item in evidence.missing_information)


def test_explicit_q4_interim_is_excluded_without_an_ambiguity_warning():
    evidence = _evidence([
        _report(1, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(2, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
        _report(5, "interim_report", "Year-end report Q4 2025", 2025, 4, 15),
    ])

    assert "document:5" not in [item.source_id for item in evidence.documents]
    assert not any("ambiguous period" in item for item in evidence.missing_information)


def test_broken_fiscal_year_does_not_treat_an_older_annual_as_the_preceding_one():
    evidence = _evidence([
        _report(1, "annual_report", "Annual report 2023", 2023, 4, 15),
        _report(2, "annual_report", "Annual report 2025", 2025, 4, 15),
    ])

    assert [item.source_id for item in evidence.documents] == ["document:2"]
    assert any("expected 2024" in item for item in evidence.missing_information)


def test_material_release_policy_classifies_allowed_and_review_candidates_and_deduplicates_report_notice():
    reports = [
        _report(1, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(2, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
    ]
    releases = [
        NewsRelease(10, 42, "order", "https://mfn.se/order", "Major order from customer", "New customer contract.", datetime(2026, 8, 1, tzinfo=timezone.utc)),
        NewsRelease(11, 42, "unknown", "https://mfn.se/unknown", "Strategic update", "Details require review.", datetime(2026, 8, 2, tzinfo=timezone.utc)),
        NewsRelease(12, 42, "notice", "https://mfn.se/notice", "Invitation to presentation", "Join webcast.", datetime(2026, 8, 3, tzinfo=timezone.utc)),
        NewsRelease(13, 42, "duplicate", "https://mfn.se/release/3", "Interim report Q2 2026", "Report announcement.", datetime(2026, 7, 15, tzinfo=timezone.utc)),
    ]

    evidence = _evidence(reports, releases)

    assert [item.source_id for item in evidence.documents] == [
        "document:1", "document:2", "document:3", "document:4", "news:10", "news:11"
    ]
    assert evidence.documents[-2].release_category == "material_order_contract_or_customer_change"
    assert evidence.documents[-1].release_category == "review_required"
    assert evidence.documents[-1].review_required is True


def test_selected_report_suppresses_cross_domain_report_announcement():
    reports = [
        _report(1, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(2, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
    ]
    reports[0].source_release_url = "https://mb.cision.com/release/annual-2025"
    releases = [
        NewsRelease(
            20,
            42,
            "micro-systemation",
            "https://mfn.se/a/micro-systemation/annual-report-2025",
            "MSAB Annual Report 2025",
            "The annual report is available.",
            datetime(2025, 7, 15, tzinfo=timezone.utc),
        )
    ]

    evidence = _evidence(reports, releases)

    assert "news:20" not in [item.source_id for item in evidence.documents]


def test_msab_q2_announcement_matches_selected_report_across_domains():
    reports = [
        _report(1, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(2, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
    ]
    reports[2].source_release_url = "https://mb.cision.com/release/q2-2026"
    releases = [
        NewsRelease(
            21,
            42,
            "micro-systemation",
            "https://mfn.se/a/micro-systemation/interim-report-q2-2026",
            "MSAB Interim Report – Q2 2026",
            "The report is available for download.",
            datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
    ]

    evidence = _evidence(reports, releases)

    assert "news:21" not in [item.source_id for item in evidence.documents]


def test_translated_contract_releases_collapse_with_complete_provenance():
    reports = [
        _report(1, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(2, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
    ]
    published_at = datetime(2026, 9, 1, 16, 15, tzinfo=timezone.utc)
    releases = [
        NewsRelease(
            51,
            42,
            "micro-systemation",
            "https://mfn.se/a/micro-systemation/contract-en",
            "MSAB secures contract worth SEK 25.7 million",
            "A major contract worth SEK 25.7 million was secured from a European defense organization.",
            published_at,
        ),
        NewsRelease(
            52,
            42,
            "micro-systemation",
            "https://mfn.se/a/micro-systemation/contract-sv",
            "MSAB säkrar avtal värt 25,7 MSEK",
            "MSAB har erhållit en order värd 25,7 MSEK från en större försvarskund i Europa.",
            published_at,
        ),
    ]
    original_releases = list(releases)

    evidence = _evidence(reports, releases)
    contract = next(item for item in evidence.documents if item.source_id == "news:51")

    assert [item.source_id for item in evidence.documents].count("news:51") == 1
    assert "news:52" not in [item.source_id for item in evidence.documents]
    assert contract.equivalent_source_ids == ["news:52"]
    assert contract.equivalent_source_urls == ["https://mfn.se/a/micro-systemation/contract-sv"]
    assert contract.equivalence_match_reason == "translated_release_event_fingerprint"
    assert contract.body_source_id == "news:51"
    assert contract.body_source_url == "https://mfn.se/a/micro-systemation/contract-en"
    assert releases == original_releases


def test_same_day_releases_with_different_event_fingerprints_remain_separate():
    reports = [
        _report(1, "annual_report", "Annual report 2025", 2025, 4, 15),
        _report(2, "annual_report", "Annual report 2024", 2024, 4, 15),
        _report(3, "interim_report", "Interim report Q2 2026", 2026, 2, 15),
        _report(4, "interim_report", "Interim report Q2 2025", 2025, 2, 15),
    ]
    published_at = datetime(2026, 9, 1, 16, 15, tzinfo=timezone.utc)
    releases = [
        NewsRelease(
            61,
            42,
            "micro-systemation",
            "https://mfn.se/a/micro-systemation/order-25",
            "MSAB secures contract worth SEK 25.7 million",
            "Contract worth SEK 25.7 million.",
            published_at,
        ),
        NewsRelease(
            62,
            42,
            "micro-systemation",
            "https://mfn.se/a/micro-systemation/order-19",
            "MSAB secures contract worth SEK 19.3 million",
            "Contract worth SEK 19.3 million.",
            published_at,
        ),
    ]

    evidence = _evidence(reports, releases)

    assert {item.source_id for item in evidence.documents} >= {"news:61", "news:62"}
