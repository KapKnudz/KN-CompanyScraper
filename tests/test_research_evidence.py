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

    transaction = evidence.insider_transactions[0]
    assert transaction.source_id.startswith("insider:")
    assert transaction.transaction_type == "Buy"
    assert transaction.returns == {
        "90d": 0.2,
        "180d": -0.1,
        "365d": 0.5,
    }
    assert "price return" in evidence.insider_methodology.lower()


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
