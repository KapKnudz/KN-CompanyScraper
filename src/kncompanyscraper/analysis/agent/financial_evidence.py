from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class FinancialReportEvidence:
    source_id: str
    period_type: str
    period_end: str | None
    year: int | None
    period: int | None
    currency: str | None
    revenue: float | None
    gross_income: float | None
    operating_profit: float | None
    ebit: float | None
    ebitda: float | None
    net_income: float | None
    operating_cash_flow: float | None
    investing_cash_flow: float | None
    free_cash_flow: float | None
    total_assets: float | None
    equity: float | None
    total_debt: float | None
    shares_outstanding: float | None


@dataclass(frozen=True)
class HalfYearFinancialFraming:
    observed_period_count: int
    latest_year: int | None
    prior_year: int | None
    latest_period_end: str | None
    prior_period_end: str | None
    latest_revenue: float | None
    prior_revenue: float | None
    revenue_change: float | None
    latest_ebit_margin: float | None
    prior_ebit_margin: float | None
    ebit_margin_change: float | None
    historical_average_ebit_margin: float | None
    periods_below_historical_average: int | None
    latest_source_ids: tuple[str, ...]
    prior_source_ids: tuple[str, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuredFinancialEvidence:
    as_of: str
    annual_reports: tuple[FinancialReportEvidence, ...]
    quarterly_reports: tuple[FinancialReportEvidence, ...]
    latest_r12: FinancialReportEvidence | None
    half_year_comparison: HalfYearFinancialFraming | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class StructuredFinancialEvidenceBuilder:
    """Build a comparison-ready, bounded financial history for one thesis."""

    ANNUAL_LIMIT = 10
    QUARTER_LIMIT = 12

    def __init__(self, financial_repository):
        self.financial_repository = financial_repository

    def build(
        self,
        company_id: int,
        as_of: date | None = None,
    ) -> StructuredFinancialEvidence:
        as_of = as_of or date.today()
        annual = self._reports(company_id, "year", as_of, self.ANNUAL_LIMIT)
        quarterly = self._reports(
            company_id, "quarter", as_of, self.QUARTER_LIMIT
        )
        r12_reports = self.financial_repository.get_reports_as_of(
            company_id, "r12", as_of
        )
        quarterly_evidence = tuple(
            self._serialize(report, "quarterly") for report in quarterly
        )
        latest_r12 = r12_reports[0] if r12_reports else None
        return StructuredFinancialEvidence(
            as_of=as_of.isoformat(),
            annual_reports=tuple(
                self._serialize(report, "annual") for report in annual
            ),
            quarterly_reports=quarterly_evidence,
            latest_r12=(
                self._serialize(latest_r12, "r12") if latest_r12 is not None else None
            ),
            half_year_comparison=self._half_year_comparison(quarterly_evidence),
        )

    @classmethod
    def _half_year_comparison(
        cls, quarterly_reports: tuple[FinancialReportEvidence, ...]
    ) -> HalfYearFinancialFraming:
        by_year: dict[int, dict[int, FinancialReportEvidence]] = {}
        for report in quarterly_reports:
            if report.year is None or report.period not in (1, 2):
                continue
            by_year.setdefault(report.year, {})[report.period] = report

        complete = {
            year: tuple(by_year[year][period] for period in (1, 2))
            for year in sorted(by_year)
            if {1, 2}.issubset(by_year[year])
        }
        if not complete:
            return HalfYearFinancialFraming(
                observed_period_count=0,
                latest_year=None,
                prior_year=None,
                latest_period_end=None,
                prior_period_end=None,
                latest_revenue=None,
                prior_revenue=None,
                revenue_change=None,
                latest_ebit_margin=None,
                prior_ebit_margin=None,
                ebit_margin_change=None,
                historical_average_ebit_margin=None,
                periods_below_historical_average=None,
                latest_source_ids=(),
                prior_source_ids=(),
                limitations=(
                    "No complete Q1 and Q2 pair is available for H1 framing.",
                ),
            )

        latest_year = max(complete)
        prior_year = latest_year - 1 if latest_year - 1 in complete else None
        latest = cls._aggregate_half_year(complete[latest_year])
        prior = cls._aggregate_half_year(complete[prior_year]) if prior_year else None
        margins = [
            margin
            for year in complete
            for margin in [cls._aggregate_half_year(complete[year])["ebit_margin"]]
            if margin is not None
        ]
        historical_average = sum(margins) / len(margins) if margins else None
        limitations = []
        if prior is None:
            limitations.append("No comparable prior-year H1 is available.")
        if latest["revenue"] is None or latest["ebit_margin"] is None:
            limitations.append("Latest H1 revenue or EBIT is incomplete.")
        return HalfYearFinancialFraming(
            observed_period_count=len(complete),
            latest_year=latest_year,
            prior_year=prior_year,
            latest_period_end=latest["period_end"],
            prior_period_end=prior["period_end"] if prior else None,
            latest_revenue=latest["revenue"],
            prior_revenue=prior["revenue"] if prior else None,
            revenue_change=cls._relative_change(
                latest["revenue"], prior["revenue"] if prior else None
            ),
            latest_ebit_margin=latest["ebit_margin"],
            prior_ebit_margin=prior["ebit_margin"] if prior else None,
            ebit_margin_change=cls._difference(
                latest["ebit_margin"], prior["ebit_margin"] if prior else None
            ),
            historical_average_ebit_margin=historical_average,
            periods_below_historical_average=(
                sum(margin < historical_average for margin in margins)
                if historical_average is not None
                else None
            ),
            latest_source_ids=tuple(report.source_id for report in complete[latest_year]),
            prior_source_ids=(
                tuple(report.source_id for report in complete[prior_year])
                if prior_year
                else ()
            ),
            limitations=tuple(limitations),
        )

    @staticmethod
    def _aggregate_half_year(
        reports: tuple[FinancialReportEvidence, FinancialReportEvidence]
    ) -> dict[str, float | str | None]:
        revenues = [report.revenue for report in reports]
        ebits = [report.ebit for report in reports]
        revenue = sum(revenues) if all(value is not None for value in revenues) else None
        ebit = sum(ebits) if all(value is not None for value in ebits) else None
        period_ends = [
            report.period_end for report in reports if report.period_end is not None
        ]
        return {
            "period_end": max(period_ends) if period_ends else None,
            "revenue": revenue,
            "ebit_margin": ebit / revenue if ebit is not None and revenue else None,
        }

    @staticmethod
    def _relative_change(current: float | None, prior: float | None) -> float | None:
        if current is None or prior is None or prior == 0:
            return None
        return current / prior - 1

    @staticmethod
    def _difference(current: float | None, prior: float | None) -> float | None:
        if current is None or prior is None:
            return None
        return current - prior

    def _reports(
        self,
        company_id: int,
        period_type: str,
        as_of: date,
        limit: int,
    ):
        return self.financial_repository.get_reports_as_of(
            company_id, period_type, as_of
        )[:limit]

    @staticmethod
    def _serialize(report, label: str) -> FinancialReportEvidence:
        period_end = report.period_end.isoformat() if report.period_end else None
        identity = period_end or f"{report.year or 'unknown'}-{report.period or 'unknown'}"
        return FinancialReportEvidence(
            source_id=f"financial:{label}:{identity}",
            period_type=label,
            period_end=period_end,
            year=report.year,
            period=report.period,
            currency=report.currency,
            revenue=report.revenue,
            gross_income=report.gross_income,
            operating_profit=report.operating_profit,
            ebit=report.ebit,
            ebitda=report.ebitda,
            net_income=report.net_income,
            operating_cash_flow=report.operating_cash_flow,
            investing_cash_flow=report.investing_cash_flow,
            free_cash_flow=report.free_cash_flow,
            total_assets=report.total_assets,
            equity=report.equity,
            total_debt=report.total_debt,
            shares_outstanding=report.shares_outstanding,
        )
