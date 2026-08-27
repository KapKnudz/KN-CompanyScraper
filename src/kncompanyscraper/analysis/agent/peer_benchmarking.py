"""Deterministic peer benchmarking for the agent evidence packet."""

from dataclasses import asdict, dataclass
from datetime import date
from statistics import median


PEER_POLICY_VERSION = "peer-benchmark-v1"


@dataclass(frozen=True)
class PeerMetric:
    value: float | None
    as_of: str
    source_ids: tuple[str, ...]
    definition: str


@dataclass(frozen=True)
class PeerSnapshot:
    company_id: int
    ticker: str
    name: str
    report_currency: str
    report_period_end: str
    metrics: dict[str, PeerMetric]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class PeerExclusion:
    company_id: int
    ticker: str
    name: str
    reason: str


@dataclass(frozen=True)
class PeerRange:
    metric: str
    count: int
    minimum: float
    median: float
    maximum: float
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class PeerComparison:
    status: str
    policy_version: str
    as_of: str
    target_company_id: int
    selection_basis: str
    target_metrics: dict[str, PeerMetric]
    target_terminal_ev_ebit: dict[str, PeerMetric]
    peer_ranges: dict[str, PeerRange]
    included_peers: tuple[PeerSnapshot, ...]
    excluded_peers: tuple[PeerExclusion, ...]
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


class PeerComparisonBuilder:
    """Build peer evidence from stored company, report, and price records."""

    MAX_REPORT_DATE_DISTANCE_DAYS = 180
    MAX_PEERS = 12

    def __init__(
        self,
        company_repository,
        financial_repository,
        valuation_repository,
        *,
        max_peers: int = MAX_PEERS,
    ):
        self.company_repository = company_repository
        self.financial_repository = financial_repository
        self.valuation_repository = valuation_repository
        self.max_peers = max_peers

    def build(
        self,
        company_id: int,
        *,
        as_of: date | None = None,
        target_terminal_ev_ebit: tuple[float | None, float | None] = (None, None),
    ) -> PeerComparison:
        as_of = as_of or date.today()
        target = self.company_repository.get_by_id(company_id)
        if target is None:
            return self._unavailable(
                company_id, as_of, "target company metadata is unavailable"
            )

        basis = self._selection_basis(target)
        if basis is None:
            return self._unavailable(
                company_id,
                as_of,
                "target has no branch or sector identity for peer selection",
            )
        target_report = self.financial_repository.get_latest_report_as_of(
            company_id, "year", as_of
        )
        target_currency = _financial_currency(target, target_report)
        target_listing_currency = _listing_currency(target)
        if target_report is None or target_report.period_end is None or not target_currency:
            return self._unavailable(
                company_id,
                as_of,
                "target lacks a dated annual report or reporting currency",
                selection_basis=basis,
            )

        target_metrics = self._metrics(
            target,
            target_report,
            self._prior_report(company_id, target_report),
            as_of,
            price=self.valuation_repository.get_stock_price_on_date(
                company_id, as_of, max_age_days=self.MAX_REPORT_DATE_DISTANCE_DAYS
            ),
            prefix="target",
        )
        target_terminal = self._target_terminal_metrics(
            target_terminal_ev_ebit, as_of
        )

        included = []
        excluded = []
        companies = sorted(
            self.company_repository.get_active_companies(),
            key=lambda company: company.id,
        )
        for peer in companies:
            if peer.id == company_id:
                continue
            reason = self._exclusion_reason(
                target,
                peer,
                basis,
                target_currency,
                target_listing_currency,
            )
            if reason:
                excluded.append(self._exclusion(peer, reason))
                continue

            report = self.financial_repository.get_latest_report_as_of(
                peer.id, "year", as_of
            )
            if report is None or report.period_end is None:
                excluded.append(self._exclusion(peer, "dated annual report unavailable"))
                continue
            peer_report_currency = _financial_currency(peer, report)
            if not peer_report_currency or peer_report_currency.upper() != target_currency.upper():
                excluded.append(self._exclusion(peer, "reporting currencies differ"))
                continue
            if abs((target_report.period_end - report.period_end).days) > self.MAX_REPORT_DATE_DISTANCE_DAYS:
                excluded.append(self._exclusion(peer, "annual report dates are not comparable"))
                continue
            if report.revenue is None or report.revenue <= 0:
                excluded.append(self._exclusion(peer, "positive annual revenue unavailable"))
                continue
            if report.ebit is None or report.ebit <= 0:
                excluded.append(self._exclusion(peer, "positive annual EBIT unavailable"))
                continue

            included.append(
                self._snapshot(
                    peer,
                    report,
                    self._prior_report(peer.id, report),
                    as_of,
                )
            )

        if len(included) > self.max_peers:
            overflow = included[self.max_peers :]
            included = included[: self.max_peers]
            excluded.extend(
                self._exclusion(peer, "peer set limit reached")
                for peer in overflow
            )

        ranges = self._ranges(included)
        limitations = [
            "Geography is approximated by listing/reporting currency because country metadata is unavailable.",
            "Lease and accounting treatment are not normalized by the stored source fields.",
        ]
        if not included:
            limitations.append("No comparable peers passed the selection policy.")
        for metric in ("current_ev_ebit", "revenue_growth", "ebit_margin", "net_debt_to_revenue"):
            if metric not in ranges:
                limitations.append(f"No comparable peer values are available for {metric}.")
        if any(
            metric.value is None for metric in target_metrics.values()
        ):
            limitations.append("One or more target comparison metrics are unavailable.")

        return PeerComparison(
            status="available" if included else "insufficient_evidence",
            policy_version=PEER_POLICY_VERSION,
            as_of=as_of.isoformat(),
            target_company_id=company_id,
            selection_basis=basis,
            target_metrics=target_metrics,
            target_terminal_ev_ebit=target_terminal,
            peer_ranges=ranges,
            included_peers=tuple(included),
            excluded_peers=tuple(excluded),
            limitations=tuple(dict.fromkeys(limitations)),
        )

    def _selection_basis(self, target):
        if getattr(target, "branch_id", None) is not None:
            return "same_branch_id_and_currency"
        if getattr(target, "sector_id", None) is not None:
            return "same_sector_id_and_currency"
        return None

    def _exclusion_reason(
        self,
        target,
        peer,
        basis,
        target_currency,
        target_listing_currency,
    ):
        if basis.startswith("same_branch") and peer.branch_id != target.branch_id:
            return "different branch_id"
        if basis.startswith("same_sector") and peer.sector_id != target.sector_id:
            return "different sector_id"
        peer_currency = _financial_currency(peer)
        if not peer_currency:
            return "reporting currency unavailable"
        if peer_currency.upper() != target_currency.upper():
            return "reporting currencies differ"
        peer_listing_currency = _listing_currency(peer)
        if (
            target_listing_currency
            and peer_listing_currency
            and peer_listing_currency.upper() != target_listing_currency.upper()
        ):
            return "listing currencies differ"
        return None

    def _prior_report(self, company_id, current_report):
        reports = self.financial_repository.get_historical_reports(company_id, "year")
        prior = [
            report
            for report in reports
            if report.period_end
            and current_report.period_end
            and report.period_end < current_report.period_end
        ]
        return max(prior, key=lambda report: report.period_end) if prior else None

    def _snapshot(self, company, report, prior_report, as_of):
        limitations = []
        price = self.valuation_repository.get_stock_price_on_date(
            company.id, as_of, max_age_days=self.MAX_REPORT_DATE_DISTANCE_DAYS
        )
        if price is None:
            limitations.append("current valuation price unavailable")
        metrics = self._metrics(
            company,
            report,
            prior_report,
            as_of,
            price=price,
            prefix="peer",
        )
        return PeerSnapshot(
            company_id=company.id,
            ticker=company.ticker,
            name=company.name,
            report_currency=_financial_currency(company, report),
            report_period_end=report.period_end.isoformat(),
            metrics=metrics,
            limitations=tuple(limitations),
        )

    def _metrics(self, company, report, prior_report, as_of, *, prefix, price=None):
        report_source = _source_id(prefix, "financial", company.id, report.period_end)
        prior_source = (
            _source_id(prefix, "financial", company.id, prior_report.period_end)
            if prior_report and prior_report.period_end
            else None
        )
        report_as_of = report.period_end.isoformat() if report.period_end else as_of.isoformat()
        metrics = {
            "revenue_growth": PeerMetric(
                _growth(report.revenue, prior_report.revenue if prior_report else None),
                report_as_of,
                tuple(source for source in (report_source, prior_source) if source),
                "latest annual revenue growth versus the immediately prior annual report",
            ),
            "ebit_margin": PeerMetric(
                _ratio(report.ebit, report.revenue),
                report_as_of,
                (report_source,),
                "latest annual EBIT divided by latest annual revenue",
            ),
            "net_debt_to_revenue": PeerMetric(
                _ratio(report.total_debt, report.revenue),
                report_as_of,
                (report_source,),
                "latest annual Börsdata net debt divided by latest annual revenue",
            ),
        }
        valuation_source = (
            _source_id(prefix, "valuation", company.id, price.date) if price else None
        )
        metrics["current_ev_ebit"] = PeerMetric(
            _current_ev_ebit(report, price),
            price.date.isoformat() if price else as_of.isoformat(),
            tuple(source for source in (valuation_source, report_source) if source),
            "latest price times shares plus net debt, divided by latest annual EBIT",
        )
        return metrics

    @staticmethod
    def _target_terminal_metrics(values, as_of):
        names = ("low", "high")
        return {
            name: PeerMetric(
                value,
                as_of.isoformat(),
                (f"full_results.valuation.ev_ebit_guardrail_{name}",),
                "company-history EV/EBIT guardrail used for terminal assumptions",
            )
            for name, value in zip(names, values)
            if value is not None
        }

    @staticmethod
    def _ranges(peers):
        result = {}
        for metric in ("current_ev_ebit", "revenue_growth", "ebit_margin", "net_debt_to_revenue"):
            values = [
                peer.metrics[metric].value
                for peer in peers
                if peer.metrics[metric].value is not None
            ]
            if not values:
                continue
            sources = tuple(
                source_id
                for peer in peers
                for source_id in peer.metrics[metric].source_ids
                if peer.metrics[metric].value is not None
            )
            result[metric] = PeerRange(
                metric=metric,
                count=len(values),
                minimum=min(values),
                median=median(values),
                maximum=max(values),
                source_ids=tuple(dict.fromkeys(sources)),
            )
        return result

    @staticmethod
    def _exclusion(company, reason):
        return PeerExclusion(company.id, company.ticker, company.name, reason)

    @staticmethod
    def _unavailable(company_id, as_of, limitation, selection_basis="unavailable"):
        return PeerComparison(
            status="insufficient_evidence",
            policy_version=PEER_POLICY_VERSION,
            as_of=as_of.isoformat(),
            target_company_id=company_id,
            selection_basis=selection_basis,
            target_metrics={},
            target_terminal_ev_ebit={},
            peer_ranges={},
            included_peers=(),
            excluded_peers=(),
            limitations=(limitation,),
        )


def _financial_currency(company, report=None):
    return (
        getattr(report, "currency", None)
        or getattr(company, "report_currency", None)
        or getattr(company, "financial_currency", None)
    )


def _listing_currency(company):
    return (
        getattr(company, "listing_currency", None)
        or getattr(company, "stock_price_currency", None)
        or getattr(company, "currency", None)
    )


def _source_id(prefix, kind, company_id, period_end):
    namespace = "peer" if prefix == "peer" else "peer:target"
    return f"{namespace}:{kind}:{company_id}:{period_end.isoformat()}"


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _growth(current, prior):
    if current is None or prior is None or prior <= 0:
        return None
    return current / prior - 1


def _current_ev_ebit(report, price):
    if (
        price is None
        or report.shares_outstanding is None
        or report.total_debt is None
        or report.ebit is None
        or report.ebit <= 0
    ):
        return None
    enterprise_value = price.close * report.shares_outstanding + report.total_debt
    return enterprise_value / report.ebit
