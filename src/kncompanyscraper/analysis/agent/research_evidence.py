from dataclasses import asdict, dataclass, field
from datetime import date, timedelta, timezone
from math import isfinite
import re

from kncompanyscraper.analysis.agent.research_document_ingestion import (
    _document_type,
    _report_period,
)


@dataclass(frozen=True)
class EvidenceDocument:
    source_id: str
    source_type: str
    title: str
    url: str
    published_at: str | None
    text: str
    structured_financial_values: list[dict] = field(default_factory=list)
    source_release_url: str | None = None
    report_year: int | None = None
    report_period: int | None = None
    release_category: str | None = None
    review_required: bool = False
    equivalent_source_ids: list[str] = field(default_factory=list)
    equivalent_source_urls: list[str] = field(default_factory=list)
    equivalence_match_reason: str | None = None
    body_source_id: str | None = None
    body_source_url: str | None = None


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
    ownership_liquidity: dict = field(default_factory=dict)
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
    ANNUAL_REPORT_LIMIT = 2
    INTERIM_REPORT_LIMIT = 2
    NEWS_LIMIT = 8
    INSIDER_LIMIT = 50
    INSIDER_LOOKBACK_DAYS = 5 * 365
    RETURN_HORIZONS = (90, 180, 365)

    def __init__(
        self,
        document_repository,
        news_repository,
        insider_repository,
        valuation_repository,
        ownership_liquidity_builder=None,
    ):
        self.document_repository = document_repository
        self.news_repository = news_repository
        self.insider_repository = insider_repository
        self.valuation_repository = valuation_repository
        self.ownership_liquidity_builder = ownership_liquidity_builder

    def build(
        self,
        company_id: int,
        as_of: date | None = None,
        filter_ids: set[str] | None = None,
    ) -> ResearchEvidence:
        as_of = as_of or date.today()
        if filter_ids is None:
            documents, document_limitations = self._selected_documents(company_id, as_of)
        else:
            documents = self._all_documents(company_id, as_of)
            document_limitations = []
        insiders = self._insiders(company_id, as_of, unbounded=filter_ids is not None)
        if filter_ids is not None:
            documents = [item for item in documents if item.source_id in filter_ids]
            insiders = [item for item in insiders if item.source_id in filter_ids]
        missing = list(document_limitations)
        if not documents:
            missing.append("No textual company reports or releases are stored")
        if not insiders:
            missing.append("No insider transactions are stored for the five-year lookback")
        missing.extend(
            [
                "Free-float percentage is unavailable",
                "Named large-holder coverage is unavailable",
                "Ownership-change history is unavailable",
            ]
        )
        ownership_liquidity = (
            self.ownership_liquidity_builder.build(
                company_id,
                as_of,
                **({"filter_ids": filter_ids} if filter_ids is not None else {}),
            ).to_dict()
            if self.ownership_liquidity_builder is not None
            else {}
        )
        if filter_ids is not None and not filter_ids.intersection(
            ownership_liquidity.get("source_ids", [])
        ):
            ownership_liquidity = {}

        return ResearchEvidence(
            as_of=as_of.isoformat(),
            documents=documents,
            insider_transactions=insiders,
            ownership_liquidity=ownership_liquidity,
            missing_information=missing,
        )

    def _documents(
        self, company_id: int, as_of: date, *, unbounded: bool = False
    ) -> list[EvidenceDocument]:
        if unbounded:
            return self._all_documents(company_id, as_of)
        return self._selected_documents(company_id, as_of)[0]

    def _selected_documents(
        self, company_id: int, as_of: date
    ) -> tuple[list[EvidenceDocument], list[str]]:
        documents = self.document_repository.list_for_company(
            company_id, as_of=as_of, limit=None
        )
        report_candidates = _group_reports(documents)
        selected_documents, limitations = _select_report_documents(report_candidates)
        result = [_document_evidence(document) for document in selected_documents]

        latest_report_date = max(
            (document.published_at for document in selected_documents if document.published_at),
            default=None,
        )
        releases = []
        for release in self.news_repository.list_for_company(
            company_id, as_of=as_of, limit=None
        ):
            if latest_report_date is not None and (
                release.published_at is not None
                and release.published_at < latest_report_date
            ):
                continue
            if _report_announcement_matches(release, selected_documents):
                continue
            category = _classify_release(release.title, release.body)
            if category is None:
                continue
            releases.append((release, category))
        releases = _deduplicate_equivalent_releases(releases)[: self.NEWS_LIMIT]
        return [*result, *releases], limitations

    def _all_documents(self, company_id: int, as_of: date) -> list[EvidenceDocument]:
        result = [_document_evidence(document) for document in self.document_repository.list_for_company(
            company_id, as_of=as_of, limit=None
        ) if not _is_auxiliary_document(document.title)]
        result.extend(
            _release_evidence(release, _classify_release(release.title, release.body) or "review_required")
            for release in self.news_repository.list_for_company(company_id, as_of=as_of, limit=None)
        )
        return result

    def _insiders(
        self, company_id: int, as_of: date, *, unbounded: bool = False
    ) -> list[InsiderTransactionEvidence]:
        since = as_of - timedelta(days=self.INSIDER_LOOKBACK_DAYS)
        transactions = self.insider_repository.list_for_company(
            company_id, since=since, limit=None if unbounded else self.INSIDER_LIMIT
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


def _document_evidence(document) -> EvidenceDocument:
    report_year, report_period = _document_period(document)
    return EvidenceDocument(
        source_id=f"document:{document.id}",
        source_type=document.document_type,
        title=document.title,
        url=document.url,
        published_at=_isoformat(document.published_at),
        text=document.text,
        structured_financial_values=_structured_financial_values(document.metadata),
        source_release_url=document.source_release_url,
        report_year=report_year,
        report_period=report_period,
        body_source_id=f"document:{document.id}",
        body_source_url=document.url,
    )


def _release_evidence(
    release,
    category: str,
    *,
    equivalent_releases=(),
    equivalence_match_reason: str | None = None,
) -> EvidenceDocument:
    source_id = f"news:{release.id}"
    return EvidenceDocument(
        source_id=source_id,
        source_type="company_release",
        title=release.title,
        url=release.url,
        published_at=_isoformat(release.published_at),
        text=release.body,
        release_category=category,
        review_required=category == "review_required",
        equivalent_source_ids=[f"news:{item.id}" for item, _ in equivalent_releases],
        equivalent_source_urls=[item.url for item, _ in equivalent_releases],
        equivalence_match_reason=equivalence_match_reason,
        body_source_id=source_id,
        body_source_url=release.url,
    )


def _deduplicate_equivalent_releases(releases) -> list[EvidenceDocument]:
    grouped = {}
    for release, category in releases:
        fingerprint = _release_event_fingerprint(release, category)
        if fingerprint is not None:
            grouped.setdefault(fingerprint, []).append((release, category))

    result = []
    emitted = set()
    for release, category in releases:
        fingerprint = _release_event_fingerprint(release, category)
        if fingerprint is None:
            result.append(_release_evidence(release, category))
            continue
        if fingerprint in emitted:
            continue
        emitted.add(fingerprint)
        matches = grouped[fingerprint]
        canonical, canonical_category = max(
            matches,
            key=lambda item: (len(item[0].body or ""), -int(item[0].id)),
        )
        equivalent = sorted(
            (item for item in matches if item[0].id != canonical.id),
            key=lambda item: int(item[0].id),
        )
        result.append(
            _release_evidence(
                canonical,
                canonical_category,
                equivalent_releases=equivalent,
                equivalence_match_reason="translated_release_event_fingerprint",
            )
        )
    return result


def _group_reports(documents) -> dict[tuple[str, int | None, int | None], list]:
    grouped = {}
    for document in documents:
        if _is_auxiliary_document(document.title):
            continue
        report_year, report_period = _document_period(document)
        document_type = document.document_type or _document_type(document.title)
        if document_type not in {"annual_report", "interim_report"}:
            continue
        grouped.setdefault((document_type, report_year, report_period), []).append(document)
    return grouped


def _select_report_documents(
    grouped: dict[tuple[str, int | None, int | None], list]
) -> tuple[list, list[str]]:
    annuals = _best_documents(grouped, "annual_report")
    interims = _best_documents(grouped, "interim_report")
    limitations = []

    dated_annuals = [item for item in annuals if _document_period(item)[0] is not None]
    latest_annual = _by_year(dated_annuals, latest=True)
    if latest_annual is None:
        limitations.append("No dated annual report is available.")
        selected_annuals = []
    else:
        latest_year = _document_period(latest_annual)[0]
        preceding_annual = _find_document(annuals, latest_year - 1, 4)
        selected_annuals = [latest_annual]
        if preceding_annual is None:
            limitations.append(
                f"Annual report history has a broken fiscal year: expected {latest_year - 1}."
            )
        else:
            selected_annuals.append(preceding_annual)

    ambiguous_interims = [
        item
        for item in interims
        if _document_period(item)[0] is not None and _has_ambiguous_report_period(item)
    ]
    dated_interims = [
        item
        for item in interims
        if _document_period(item)[0] is not None and _document_period(item)[1] in (1, 2, 3)
    ]
    latest_interim = _latest_period_document(dated_interims)
    if latest_interim is None:
        limitations.append("No dated interim report is available.")
        selected_interims = []
    else:
        interim_year, interim_period = _document_period(latest_interim)
        preceding_interim = _find_document(interims, interim_year - 1, interim_period)
        selected_interims = [latest_interim]
        if preceding_interim is None:
            limitations.append(
                "No comparable prior-year interim report is available for "
                f"{interim_year} Q{interim_period}."
            )
    if ambiguous_interims:
        limitations.append(
            "An interim report has an ambiguous period and is not treated as a "
            "prior-year comparable."
        )
    if latest_interim is not None and preceding_interim is not None:
        selected_interims.append(preceding_interim)

    return [*selected_annuals, *selected_interims], limitations


def _best_documents(grouped, document_type: str) -> list:
    return [
        max(documents, key=_document_priority)
        for (kind, _, _), documents in grouped.items()
        if kind == document_type
    ]


def _by_year(documents, *, latest: bool):
    if not documents:
        return None
    return sorted(
        documents,
        key=lambda item: (
            _document_period(item)[0],
            item.published_at.isoformat() if item.published_at else "",
        ),
        reverse=latest,
    )[0]


def _latest_period_document(documents):
    if not documents:
        return None
    return max(
        documents,
        key=lambda item: (
            _document_period(item)[0],
            _document_period(item)[1],
            item.published_at.isoformat() if item.published_at else "",
        ),
    )


def _find_document(documents, year: int, period: int):
    matches = [
        item
        for item in documents
        if _document_period(item) == (year, period)
    ]
    return max(matches, key=_document_priority) if matches else None


def _report_announcement_matches(release, selected_documents) -> bool:
    if not _is_report_announcement(release.title):
        return False

    for document in selected_documents:
        if document.source_release_url == release.url:
            return True
        metadata = document.metadata or {}
        attachment_urls = metadata.get("source_attachment_urls", [])
        if isinstance(attachment_urls, str):
            attachment_urls = [attachment_urls]
        if release.url in {
            document.url,
            metadata.get("source_attachment_url"),
            metadata.get("attachment_url"),
            *attachment_urls,
        }:
            return True
        if _report_metadata_matches(release, document):
            return True
    return False


def _report_metadata_matches(release, document) -> bool:
    if release.company_id != document.company_id:
        return False
    metadata = document.metadata or {}
    if not {"report_year", "report_period"}.issubset(metadata):
        return False
    release_type = _document_type(release.title)
    document_type = document.document_type or _document_type(document.title)
    if release_type != document_type:
        return False
    release_period = _release_period(release)
    document_period = _document_period(document)
    if (metadata.get("report_year"), metadata.get("report_period")) != document_period:
        return False
    if release_period != document_period:
        return False
    if release.published_at is None or document.published_at is None:
        return False
    return release.published_at.date() == document.published_at.date()


def _release_period(release) -> tuple[int | None, int | None]:
    title = release.title or ""
    year_match = re.search(r"\b(20\d{2})\b", title)
    year = int(year_match.group(1)) if year_match else None
    period = _report_period(title.casefold())
    if year is None and period in (1, 2, 3) and release.published_at is not None:
        year = release.published_at.year
    if period == 4 and _document_type(title) != "annual_report":
        period = None
    return year, period


def _release_event_fingerprint(release, category: str):
    if release.published_at is None:
        return None
    numeric_markers = _normalized_numeric_currency_markers(
        f"{release.title} {release.body}"
    )
    if not numeric_markers:
        return None
    upstream_identity = (release.slug or "").casefold().strip() or None
    return (
        release.company_id,
        _normalized_publication_timestamp(release.published_at),
        category,
        tuple(numeric_markers),
        upstream_identity,
    )


def _normalized_publication_timestamp(value) -> str:
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(timezone.utc).isoformat()


_NUMBER_PATTERN = r"(?:\d{1,3}(?:[ .]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
_MONEY_MARKER_PATTERN = r"(?:msek|mkr|sek|kr|kronor|eur|euro|usd|dollar)"
_MONEY_SCALE_PATTERN = r"(?:million|millions|miljon|miljoner|billion|miljard(?:er)?)"


def _normalized_numeric_currency_markers(text: str) -> list[str]:
    patterns = (
        re.compile(
            rf"\b(?P<marker>{_MONEY_MARKER_PATTERN})\s*"
            rf"(?P<value>{_NUMBER_PATTERN})\s*"
            rf"(?P<scale>{_MONEY_SCALE_PATTERN})?\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\b(?P<value>{_NUMBER_PATTERN})\s*"
            rf"(?P<scale>{_MONEY_SCALE_PATTERN})?\s*"
            rf"(?P<marker>{_MONEY_MARKER_PATTERN})\b",
            re.IGNORECASE,
        ),
    )
    markers = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            marker = match.group("marker").casefold()
            scale = (match.group("scale") or "").casefold()
            currency = {
                "kr": "sek",
                "kronor": "sek",
                "mkr": "sek",
                "msek": "sek",
                "euro": "eur",
                "dollar": "usd",
            }.get(marker, marker)
            if marker in {"mkr", "msek"} or scale in {
                "million",
                "millions",
                "miljon",
                "miljoner",
                "billion",
                "miljard",
                "miljarder",
            }:
                currency = f"{currency}_scaled"
            value = match.group("value").replace(" ", "")
            if "," in value and "." in value:
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", ".")
            markers.add(f"{currency}:{value}")
    return sorted(markers)


def _document_period(document) -> tuple[int | None, int | None]:
    metadata = document.metadata or {}
    year = metadata.get("report_year")
    period = metadata.get("report_period")
    if not isinstance(year, int) or isinstance(year, bool):
        year = None
    if not isinstance(period, int) or isinstance(period, bool) or period not in range(1, 5):
        period = None

    title = document.title or ""
    if year is None:
        match = re.search(r"\b(20\d{2})\b", title)
        year = int(match.group(1)) if match else None
    if period is None:
        period = _report_period(title.casefold())
    if year is None and period in (1, 2, 3) and document.published_at is not None:
        year = document.published_at.year
    if period == 4 and (document.document_type or _document_type(title)) != "annual_report":
        period = None
    return year, period


def _has_ambiguous_report_period(document) -> bool:
    metadata_period = (document.metadata or {}).get("report_period")
    if (
        isinstance(metadata_period, int)
        and not isinstance(metadata_period, bool)
        and metadata_period in range(1, 5)
    ):
        return False
    return _report_period((document.title or "").casefold()) is None


def _is_auxiliary_document(title: str) -> bool:
    normalized = title.casefold()
    return "invitation" in normalized or "inbjudan" in normalized


def _document_priority(document) -> tuple[int, int]:
    normalized = document.title.casefold()
    penalties = ("key figures", "nyckeltal", "press release", "presentation", "prm")
    return (-sum(term in normalized for term in penalties), len(document.text))


def _is_report_announcement(title: str) -> bool:
    normalized = title.casefold()
    return any(
        term in normalized
        for term in (
            "annual report",
            "interim report",
            "quarterly report",
            "year-end report",
            "årsredovisning",
            "delårsrapport",
            "kvartalsrapport",
            "bokslutskommuniké",
        )
    )


def _classify_release(title: str, body: str) -> str | None:
    normalized = f"{title} {body}".casefold()
    if _is_non_material_release(title):
        return None
    if _is_report_announcement(title):
        return "review_required"
    categories = (
        (
            "acquisition_or_divestment",
            ("acquisition", "acquire", "divest", "merger", "förvärv", "avyttr", "fusion"),
        ),
        (
            "profit_warning_or_guidance_change",
            ("profit warning", "guidance", "outlook", "earnings warning", "vinstvarning", "prognos"),
        ),
        (
            "material_order_contract_or_customer_change",
            ("large order", "major order", "order worth", "contract", "customer", "kund", "avtal", "ramavtal"),
        ),
        (
            "financing_capital_raise_refinancing_dividend_or_buyback",
            (
                "financing", "capital raise", "rights issue", "refinanc", "dividend",
                "buyback", "repurchase", "nyemission", "företrädesemission", "återköp", "utdelning",
            ),
        ),
        (
            "material_management_change",
            (
                "appoints ceo", "new ceo", "ceo resign", "appoints cfo", "new cfo", "cfo resign",
                "chairman", "chief executive", "verkställande direktör", "vd lämnar", "styrelseordförande",
            ),
        ),
        (
            "material_regulatory_litigation_or_operational_disruption",
            (
                "regulatory", "regulator", "litigation", "lawsuit", "investigation", "cyberattack",
                "disruption", "recall", "myndighet", "rättstv", "driftstör", "operational incident",
            ),
        ),
    )
    for category, terms in categories:
        if any(term in normalized for term in terms):
            return category
    return "review_required"


def _is_non_material_release(title: str) -> bool:
    normalized = title.casefold()
    return any(
        term in normalized
        for term in (
            "invitation",
            "inbjudan",
            "financial calendar",
            "reporting calendar",
            "calendar notice",
            "webcast",
            "investor relations",
            "capital markets day",
            "annual general meeting notice",
        )
    )


def _structured_financial_values(metadata: dict | None) -> list[dict]:
    """Return explicitly stored report values without interpreting report prose."""
    values = (metadata or {}).get("structured_financial_values", [])
    if not isinstance(values, list):
        return []

    result = []
    for value in values:
        if not isinstance(value, dict):
            continue
        metric = value.get("metric")
        amount = value.get("value")
        period = value.get("period")
        period_end = value.get("period_end")
        if (
            not isinstance(metric, str)
            or not metric.strip()
            or not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or not isfinite(amount)
            or not isinstance(period, str) and not isinstance(period_end, str)
        ):
            continue
        result.append(
            {
                "metric": metric.strip(),
                "value": amount,
                "period": period,
                "period_end": period_end,
            }
        )
    return result
