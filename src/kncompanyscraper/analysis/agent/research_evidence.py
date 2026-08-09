from dataclasses import asdict, dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class EvidenceDocument:
    source_id: str
    source_type: str
    title: str
    url: str
    published_at: str | None
    text: str


@dataclass(frozen=True)
class InsiderTransactionEvidence:
    source_id: str
    person_name: str
    person_role: str | None
    transaction_type: str
    shares: int
    price_per_share: float | None
    total_value: float | None
    transaction_date: str
    currency: str | None
    source: str | None
    entry_market_price: float | None
    entry_market_price_date: str | None
    returns: dict[str, float | None]


@dataclass(frozen=True)
class ResearchEvidence:
    as_of: str
    documents: list[EvidenceDocument] = field(default_factory=list)
    insider_transactions: list[InsiderTransactionEvidence] = field(default_factory=list)
    insider_methodology: str = (
        "Returns are unadjusted price returns from the first stored closing price on or after "
        "the transaction date to the stored close on or before each horizon. They exclude "
        "dividends and are evidence for interpretation, not an insider score."
    )
    missing_information: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["insider_status"] = "available" if self.insider_transactions else "unavailable"
        payload["insider_event_count"] = len(self.insider_transactions)
        return payload


class ResearchEvidenceBuilder:
    REPORT_LIMIT = 4
    NEWS_LIMIT = 8
    INSIDER_LIMIT = 50
    INSIDER_LOOKBACK_DAYS = 5 * 365
    MAX_DOCUMENT_CHARS = 12_000
    RETURN_HORIZONS = (90, 180, 365)

    def __init__(
        self,
        document_repository,
        news_repository,
        insider_repository,
        valuation_repository,
    ):
        self.document_repository = document_repository
        self.news_repository = news_repository
        self.insider_repository = insider_repository
        self.valuation_repository = valuation_repository

    def build(self, company_id: int, as_of: date | None = None) -> ResearchEvidence:
        as_of = as_of or date.today()
        documents = self._documents(company_id, as_of)
        insiders = self._insiders(company_id, as_of)
        missing = []
        if not documents:
            missing.append("No textual company reports or releases are stored")
        if not insiders:
            missing.append("No insider transactions are stored for the five-year lookback")

        return ResearchEvidence(
            as_of=as_of.isoformat(),
            documents=documents,
            insider_transactions=insiders,
            missing_information=missing,
        )

    def _documents(self, company_id: int, as_of: date) -> list[EvidenceDocument]:
        result = []
        documents = self.document_repository.list_for_company(
            company_id, as_of=as_of, limit=self.REPORT_LIMIT * 6
        )
        grouped_documents = {}
        for document in documents:
            if _is_auxiliary_document(document.title):
                continue
            period_key = (
                document.document_type,
                document.published_at.date() if document.published_at else document.url,
            )
            grouped_documents.setdefault(period_key, []).append(document)

        for period_documents in grouped_documents.values():
            document = max(period_documents, key=_document_priority)
            result.append(
                EvidenceDocument(
                    source_id=f"document:{document.id}",
                    source_type=document.document_type,
                    title=document.title,
                    url=document.url,
                    published_at=_isoformat(document.published_at),
                    text=document.text[: self.MAX_DOCUMENT_CHARS],
                )
            )
            if len(result) >= self.REPORT_LIMIT:
                break

        seen_release_times = set()
        for release in self.news_repository.list_for_company(
            company_id, as_of=as_of, limit=self.NEWS_LIMIT * 3
        ):
            release_key = release.published_at or release.url
            if release_key in seen_release_times:
                continue
            seen_release_times.add(release_key)
            result.append(
                EvidenceDocument(
                    source_id=f"news:{release.id}",
                    source_type="company_release",
                    title=release.title,
                    url=release.url,
                    published_at=_isoformat(release.published_at),
                    text=release.body[: self.MAX_DOCUMENT_CHARS],
                )
            )
            if len(seen_release_times) >= self.NEWS_LIMIT:
                break
        return result

    def _insiders(self, company_id: int, as_of: date) -> list[InsiderTransactionEvidence]:
        since = as_of - timedelta(days=self.INSIDER_LOOKBACK_DAYS)
        transactions = self.insider_repository.list_for_company(
            company_id, since=since, limit=self.INSIDER_LIMIT
        )
        return [
            self._insider_evidence(company_id, transaction, as_of, index)
            for index, transaction in enumerate(transactions, 1)
            if transaction.transaction_date <= as_of
        ]

    def _insider_evidence(self, company_id, transaction, as_of: date, index: int):
        entry = self.valuation_repository.get_stock_price_on_or_after(
            company_id, transaction.transaction_date, max_age_days=7
        )
        returns = {}
        for horizon in self.RETURN_HORIZONS:
            target = transaction.transaction_date + timedelta(days=horizon)
            if target > as_of or entry is None or entry.close == 0:
                returns[f"{horizon}d"] = None
                continue
            outcome = self.valuation_repository.get_stock_price_on_date(
                company_id, target, max_age_days=7
            )
            returns[f"{horizon}d"] = (
                round(outcome.close / entry.close - 1, 4) if outcome is not None else None
            )

        source_id = (
            f"insider:{transaction.transaction_date.isoformat()}:"
            f"{transaction.person_name}:{index}"
        )
        return InsiderTransactionEvidence(
            source_id=source_id,
            person_name=transaction.person_name,
            person_role=transaction.person_role,
            transaction_type=transaction.transaction_type,
            shares=transaction.shares,
            price_per_share=transaction.price_per_share,
            total_value=transaction.total_value,
            transaction_date=transaction.transaction_date.isoformat(),
            currency=transaction.currency,
            source=transaction.source,
            entry_market_price=entry.close if entry else None,
            entry_market_price_date=entry.date.isoformat() if entry else None,
            returns=returns,
        )


def _isoformat(value) -> str | None:
    return value.isoformat() if value is not None else None


def _is_auxiliary_document(title: str) -> bool:
    normalized = title.casefold()
    return "invitation" in normalized or "inbjudan" in normalized


def _document_priority(document) -> tuple[int, int]:
    normalized = document.title.casefold()
    penalties = ("key figures", "nyckeltal", "press release", "presentation", "prm")
    return (-sum(term in normalized for term in penalties), len(document.text))
