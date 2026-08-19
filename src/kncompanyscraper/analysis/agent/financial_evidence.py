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
class StructuredFinancialEvidence:
    as_of: str
    annual_reports: tuple[FinancialReportEvidence, ...]
    quarterly_reports: tuple[FinancialReportEvidence, ...]
    latest_r12: FinancialReportEvidence | None

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
        latest_r12 = r12_reports[0] if r12_reports else None
        return StructuredFinancialEvidence(
            as_of=as_of.isoformat(),
            annual_reports=tuple(
                self._serialize(report, "annual") for report in annual
            ),
            quarterly_reports=tuple(
                self._serialize(report, "quarterly") for report in quarterly
            ),
            latest_r12=(
                self._serialize(latest_r12, "r12") if latest_r12 is not None else None
            ),
        )

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
