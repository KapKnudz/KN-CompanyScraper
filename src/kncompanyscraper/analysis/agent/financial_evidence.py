from dataclasses import asdict, dataclass, replace
from datetime import date
from math import isfinite


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
    report_date: str | None = None
    broken_fiscal_year: bool | None = None


@dataclass(frozen=True)
class ScenarioFinancialObservation:
    period_type: str
    period_end: str | None
    value: float | None
    source_id: str


@dataclass(frozen=True)
class ScenarioFinancialHistory:
    """Compact deterministic summaries calculated from the full report history."""

    as_of: str
    coverage_start: str | None
    coverage_end: str | None
    annual_observation_count: int
    quarterly_observation_count: int
    r12_observation_count: int
    observation_counts: dict[str, int]
    revenue_cagr_3_year: float | None
    revenue_cagr_5_year: float | None
    revenue_cagr_10_year: float | None
    r12_revenue_growth_lower: float | None
    r12_revenue_growth_upper: float | None
    r12_ebit_margin_median: float | None
    r12_ebit_margin_lower_range: float | None
    r12_ebit_margin_upper_range: float | None
    r12_ebit_margin_peak: float | None
    r12_ebit_margin_trough: float | None
    share_count_growth_3_year: float | None
    share_count_growth_5_year: float | None
    maximum_observed_dilution: float | None
    net_debt_change_3_year: float | None
    net_debt_change_5_year: float | None
    recent_dividend_per_share_history: tuple[ScenarioFinancialObservation, ...]
    dividend_consistency: bool | None
    operating_cash_flow_observations: tuple[ScenarioFinancialObservation, ...]
    investing_cash_flow_observations: tuple[ScenarioFinancialObservation, ...]
    financing_cash_flow_observations: tuple[ScenarioFinancialObservation, ...]
    source_ids: dict[str, tuple[str, ...]]
    exclusions: tuple[str, ...]

    @property
    def r12_revenue_growth_range(self) -> tuple[float | None, float | None]:
        return self.r12_revenue_growth_lower, self.r12_revenue_growth_upper

    @property
    def r12_revenue_growth_min(self) -> float | None:
        return self.r12_revenue_growth_lower

    @property
    def r12_revenue_growth_max(self) -> float | None:
        return self.r12_revenue_growth_upper

    @property
    def r12_ebit_margin_range(self) -> tuple[float | None, float | None]:
        return self.r12_ebit_margin_lower_range, self.r12_ebit_margin_upper_range

    @property
    def r12_ebit_margin_p10(self) -> float | None:
        return self.r12_ebit_margin_lower_range

    @property
    def r12_ebit_margin_p90(self) -> float | None:
        return self.r12_ebit_margin_upper_range


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
    scenario_history: ScenarioFinancialHistory | None = None
    half_year_comparison: HalfYearFinancialFraming | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def with_document_reconciliations(self, documents) -> "StructuredFinancialEvidence":
        framing = self.half_year_comparison
        if framing is None or framing.latest_year is None:
            return self

        canonical_values = {
            "revenue": framing.latest_revenue,
            "ebit_margin": framing.latest_ebit_margin,
        }
        period = f"{framing.latest_year}-H1"
        source_ids = ", ".join(framing.latest_source_ids)
        limitations = list(framing.limitations)
        for document in documents or ():
            source_id = _field(document, "source_id")
            for value in _field(document, "structured_financial_values") or ():
                metric = value.get("metric")
                canonical = canonical_values.get(metric)
                if (
                    not source_id
                    or canonical is None
                    or not isfinite(canonical)
                    or not _matches_period(value, period, framing.latest_period_end)
                ):
                    continue
                reported = value.get("value")
                if not _materially_differs(reported, canonical):
                    continue
                limitations.append(
                    _reconciliation_limitation(
                        source_id,
                        metric,
                        period,
                        reported,
                        canonical,
                        source_ids,
                    )
                )

        return replace(
            self,
            half_year_comparison=replace(
                framing, limitations=tuple(dict.fromkeys(limitations))
            ),
        )


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
        annual_history = self._all_reports(company_id, "year", as_of)
        quarterly_history = self._all_reports(company_id, "quarter", as_of)
        r12_history = self._all_reports(company_id, "r12", as_of)
        annual = annual_history[: self.ANNUAL_LIMIT]
        quarterly = quarterly_history[: self.QUARTER_LIMIT]
        quarterly_evidence = tuple(
            self._serialize(report, "quarterly") for report in quarterly
        )
        latest_r12 = r12_history[0] if r12_history else None
        return StructuredFinancialEvidence(
            as_of=as_of.isoformat(),
            annual_reports=tuple(
                self._serialize(report, "annual") for report in annual
            ),
            quarterly_reports=quarterly_evidence,
            latest_r12=(
                self._serialize(latest_r12, "r12") if latest_r12 is not None else None
            ),
            scenario_history=self._scenario_history(
                as_of,
                annual_history,
                quarterly_history,
                r12_history,
            ),
            half_year_comparison=self._half_year_comparison(quarterly_evidence),
        )

    @classmethod
    def _scenario_history(
        cls,
        as_of: date,
        annual_reports,
        quarterly_reports,
        r12_reports,
    ) -> ScenarioFinancialHistory:
        all_reports = [
            ("annual", report) for report in annual_reports
        ] + [
            ("quarterly", report) for report in quarterly_reports
        ] + [
            ("r12", report) for report in r12_reports
        ]
        dated_reports = [
            report for _, report in all_reports if report.period_end is not None
        ]
        coverage_start = min(
            (report.period_end for report in dated_reports), default=None
        )
        coverage_end = max(
            (report.period_end for report in dated_reports), default=None
        )
        exclusions = [
            f"{cls._source_id(report, label)} excluded from ordinary comparisons: "
            "broken fiscal year"
            for label, report in all_reports
            if getattr(report, "broken_fiscal_year", False)
        ]
        comparison_annual = [
            report
            for report in annual_reports
            if not getattr(report, "broken_fiscal_year", False)
        ]
        comparison_r12 = [
            report
            for report in r12_reports
            if not getattr(report, "broken_fiscal_year", False)
        ]
        incomplete_r12_revenue = cls._missing_source_ids(
            comparison_r12, "r12", "revenue"
        )
        if incomplete_r12_revenue:
            exclusions.append(
                "r12 revenue comparisons exclude incomplete rows: "
                + ", ".join(incomplete_r12_revenue)
            )
        incomplete_r12_margin = cls._missing_source_ids(
            comparison_r12,
            "r12",
            "ebit",
        ) + cls._missing_source_ids(comparison_r12, "r12", "revenue")
        if incomplete_r12_margin:
            exclusions.append(
                "r12 EBIT-margin summaries exclude incomplete rows: "
                + ", ".join(dict.fromkeys(incomplete_r12_margin))
            )

        source_ids: dict[str, tuple[str, ...]] = {
            "coverage": tuple(
                cls._source_id(report, label) for label, report in all_reports
            )
        }
        cagr_values = {}
        for years in (3, 5, 10):
            value, ids, exclusion = cls._annual_growth_summary(
                comparison_annual, "revenue", years, as_percentage=False
            )
            cagr_values[years] = value
            source_ids[f"revenue_cagr_{years}_year"] = ids
            if exclusion:
                exclusions.append(exclusion)

        r12_growth, growth_ids, growth_exclusion = cls._r12_revenue_growth(
            comparison_r12
        )
        source_ids["r12_revenue_growth"] = growth_ids
        if growth_exclusion:
            exclusions.append(growth_exclusion)

        margins, margin_ids, margin_exclusion = cls._r12_margin_summary(
            comparison_r12
        )
        source_ids["r12_ebit_margin"] = margin_ids
        if margin_exclusion:
            exclusions.append(margin_exclusion)

        share_growth = {}
        debt_changes = {}
        for years in (3, 5):
            share_growth[years], ids, exclusion = cls._annual_growth_summary(
                comparison_annual, "shares_outstanding", years, as_percentage=True
            )
            source_ids[f"share_count_growth_{years}_year"] = ids
            if exclusion:
                exclusions.append(exclusion)
            debt_changes[years], ids, exclusion = cls._net_debt_change(
                comparison_annual, years
            )
            source_ids[f"net_debt_change_{years}_year"] = ids
            if exclusion:
                exclusions.append(exclusion)

        dilution, dilution_ids, dilution_exclusion = cls._maximum_dilution(
            comparison_annual
        )
        source_ids["maximum_observed_dilution"] = dilution_ids
        if dilution_exclusion:
            exclusions.append(dilution_exclusion)

        dividend_history = tuple(
            cls._observation(report, "annual", "dividend_per_share")
            for report in comparison_annual[:5]
        )
        dividend_ids = tuple(item.source_id for item in dividend_history)
        source_ids["recent_dividend_per_share_history"] = dividend_ids
        dividend_values = [item.value for item in dividend_history]
        if not any(value is not None for value in dividend_values):
            dividend_consistency = None
            if dividend_history:
                exclusions.append(
                    "dividend_consistency unavailable: dividend-per-share history is incomplete"
                )
        else:
            dividend_consistency = all(value is not None for value in dividend_values)
            if not dividend_consistency:
                exclusions.append(
                    "dividend_consistency excludes annual rows with missing dividend-per-share"
                )
        source_ids["dividend_consistency"] = dividend_ids

        cash_flow_observations = {}
        for field in (
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        ):
            observations = tuple(
                cls._observation(report, "annual", field)
                for report in comparison_annual
                if getattr(report, field, None) is not None
            )
            cash_flow_observations[field] = observations
            source_ids[f"{field}_observations"] = tuple(
                item.source_id for item in observations
            )
            if not observations:
                exclusions.append(
                    f"{field}_observations unavailable: no complete annual observations"
                )
            else:
                missing = cls._missing_source_ids(comparison_annual, "annual", field)
                if missing:
                    exclusions.append(
                        f"{field}_observations exclude incomplete rows: "
                        + ", ".join(missing)
                    )

        return ScenarioFinancialHistory(
            as_of=as_of.isoformat(),
            coverage_start=coverage_start.isoformat() if coverage_start else None,
            coverage_end=coverage_end.isoformat() if coverage_end else None,
            annual_observation_count=len(annual_reports),
            quarterly_observation_count=len(quarterly_reports),
            r12_observation_count=len(r12_reports),
            observation_counts={
                "annual": len(annual_reports),
                "quarterly": len(quarterly_reports),
                "r12": len(r12_reports),
            },
            revenue_cagr_3_year=cagr_values[3],
            revenue_cagr_5_year=cagr_values[5],
            revenue_cagr_10_year=cagr_values[10],
            r12_revenue_growth_lower=r12_growth[0],
            r12_revenue_growth_upper=r12_growth[1],
            r12_ebit_margin_median=margins["median"],
            r12_ebit_margin_lower_range=margins["lower"],
            r12_ebit_margin_upper_range=margins["upper"],
            r12_ebit_margin_peak=margins["peak"],
            r12_ebit_margin_trough=margins["trough"],
            share_count_growth_3_year=share_growth[3],
            share_count_growth_5_year=share_growth[5],
            maximum_observed_dilution=dilution,
            net_debt_change_3_year=debt_changes[3],
            net_debt_change_5_year=debt_changes[5],
            recent_dividend_per_share_history=dividend_history,
            dividend_consistency=dividend_consistency,
            operating_cash_flow_observations=cash_flow_observations[
                "operating_cash_flow"
            ],
            investing_cash_flow_observations=cash_flow_observations[
                "investing_cash_flow"
            ],
            financing_cash_flow_observations=cash_flow_observations[
                "financing_cash_flow"
            ],
            source_ids=source_ids,
            exclusions=tuple(dict.fromkeys(exclusions)),
        )

    @classmethod
    def _annual_growth_summary(
        cls, reports, field: str, years: int, as_percentage: bool
    ) -> tuple[float | None, tuple[str, ...], str | None]:
        latest = cls._latest_annual_report(reports)
        prior = cls._report_for_year(
            reports,
            latest.year - years if latest is not None and latest.year is not None else None,
        )
        label = f"{field}_{years}_year"
        if latest is None or prior is None:
            return None, (), f"{label} unavailable: no comparable annual reports"
        latest_value = getattr(latest, field, None)
        prior_value = getattr(prior, field, None)
        ids = (cls._source_id(latest, "annual"), cls._source_id(prior, "annual"))
        if not _valid_number(latest_value) or not _valid_number(prior_value):
            return None, ids, f"{label} unavailable: incomplete source data"
        if prior_value <= 0 or latest_value < 0:
            return None, ids, f"{label} unavailable: non-positive source data"
        value = latest_value / prior_value - 1
        if not as_percentage:
            value = (latest_value / prior_value) ** (1 / years) - 1
        return value, ids, None

    @classmethod
    def _net_debt_change(
        cls, reports, years: int
    ) -> tuple[float | None, tuple[str, ...], str | None]:
        latest = cls._latest_annual_report(reports)
        prior = cls._report_for_year(
            reports,
            latest.year - years if latest is not None and latest.year is not None else None,
        )
        label = f"net_debt_change_{years}_year"
        if latest is None or prior is None:
            return None, (), f"{label} unavailable: no comparable annual reports"
        ids = (cls._source_id(latest, "annual"), cls._source_id(prior, "annual"))
        latest_debt = cls._net_debt(latest)
        prior_debt = cls._net_debt(prior)
        if latest_debt is None or prior_debt is None:
            return None, ids, f"{label} unavailable: net debt is incomplete"
        return latest_debt - prior_debt, ids, None

    @classmethod
    def _r12_revenue_growth(
        cls, reports
    ) -> tuple[tuple[float | None, float | None], tuple[str, ...], str | None]:
        values = []
        source_ids = []
        for current in reports:
            prior = cls._matching_prior_report(reports, current)
            if prior is None:
                continue
            current_revenue = getattr(current, "revenue", None)
            prior_revenue = getattr(prior, "revenue", None)
            ids = (cls._source_id(current, "r12"), cls._source_id(prior, "r12"))
            if not _valid_number(current_revenue) or not _valid_number(prior_revenue):
                continue
            if prior_revenue <= 0:
                continue
            values.append(current_revenue / prior_revenue - 1)
            source_ids.extend(ids)
        if not values:
            return (None, None), (), (
                "r12_revenue_growth unavailable: no complete year-over-year pairs"
            )
        return (min(values), max(values)), tuple(dict.fromkeys(source_ids)), None

    @classmethod
    def _r12_margin_summary(
        cls, reports
    ) -> tuple[dict[str, float | None], tuple[str, ...], str | None]:
        margins = []
        source_ids = []
        for report in reports:
            revenue = getattr(report, "revenue", None)
            ebit = getattr(report, "ebit", None)
            if not _valid_number(revenue) or not _valid_number(ebit) or revenue == 0:
                continue
            margins.append(ebit / revenue)
            source_ids.append(cls._source_id(report, "r12"))
        if not margins:
            return (
                {key: None for key in ("median", "lower", "upper", "peak", "trough")},
                (),
                "r12_ebit_margin unavailable: no complete observations",
            )
        ordered = sorted(margins)
        return (
            {
                "median": _quantile(ordered, 0.5),
                "lower": _quantile(ordered, 0.1),
                "upper": _quantile(ordered, 0.9),
                "peak": max(ordered),
                "trough": min(ordered),
            },
            tuple(source_ids),
            None,
        )

    @classmethod
    def _maximum_dilution(
        cls, reports
    ) -> tuple[float | None, tuple[str, ...], str | None]:
        values = []
        source_ids = []
        for current, prior in zip(reports, reports[1:]):
            if (
                getattr(current, "year", None) is None
                or getattr(prior, "year", None) is None
                or current.year - prior.year != 1
            ):
                continue
            current_shares = getattr(current, "shares_outstanding", None)
            prior_shares = getattr(prior, "shares_outstanding", None)
            if not _valid_number(current_shares) or not _valid_number(prior_shares):
                continue
            if prior_shares <= 0:
                continue
            growth = current_shares / prior_shares - 1
            if growth > 0:
                values.append(growth)
                source_ids.extend(
                    (cls._source_id(current, "annual"), cls._source_id(prior, "annual"))
                )
        if not values:
            return None, (), "maximum_observed_dilution unavailable: no complete positive share-count changes"
        return max(values), tuple(dict.fromkeys(source_ids)), None

    @staticmethod
    def _matching_prior_report(reports, current):
        current_year = getattr(current, "year", None)
        current_period = getattr(current, "period", None)
        if current_year is None:
            return None
        candidates = [
            report
            for report in reports
            if getattr(report, "year", None) == current_year - 1
            and (
                current_period is None
                or getattr(report, "period", None) == current_period
            )
        ]
        if candidates:
            return candidates[0]
        return None

    @staticmethod
    def _report_for_year(reports, year):
        if year is None:
            return None
        return next(
            (report for report in reports if getattr(report, "year", None) == year),
            None,
        )

    @staticmethod
    def _latest_annual_report(reports):
        return max(
            (report for report in reports if getattr(report, "year", None) is not None),
            key=lambda report: (report.year, report.period_end or date.min),
            default=None,
        )

    @staticmethod
    def _net_debt(report) -> float | None:
        # Report.total_debt is the canonical Börsdata net_Debt field.
        net_debt = getattr(report, "total_debt", None)
        if not _valid_number(net_debt):
            return None
        return net_debt

    @classmethod
    def _observation(cls, report, label: str, field: str):
        return ScenarioFinancialObservation(
            period_type=label,
            period_end=(
                report.period_end.isoformat() if report.period_end is not None else None
            ),
            value=getattr(report, field, None),
            source_id=cls._source_id(report, label),
        )

    @staticmethod
    def _source_id(report, label: str) -> str:
        period_end = report.period_end.isoformat() if report.period_end else None
        identity = period_end or f"{report.year or 'unknown'}-{report.period or 'unknown'}"
        return f"financial:{label}:{identity}"

    @classmethod
    def _missing_source_ids(cls, reports, label: str, field: str) -> tuple[str, ...]:
        return tuple(
            cls._source_id(report, label)
            for report in reports
            if not _valid_number(getattr(report, field, None))
        )

    @classmethod
    def _half_year_comparison(
        cls, quarterly_reports: tuple[FinancialReportEvidence, ...]
    ) -> HalfYearFinancialFraming:
        by_year: dict[int, dict[int, FinancialReportEvidence]] = {}
        for report in quarterly_reports:
            if getattr(report, "broken_fiscal_year", False):
                continue
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

    def _all_reports(
        self,
        company_id: int,
        period_type: str,
        as_of: date,
    ):
        reports = self.financial_repository.get_reports_as_of(
            company_id, period_type, as_of
        )
        return sorted(reports, key=self._report_sort_key, reverse=True)

    @staticmethod
    def _report_sort_key(report):
        return (
            report.period_end or date.min,
            report.year or 0,
            report.period or 0,
        )

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
            report_date=(
                report.report_date.isoformat()
                if getattr(report, "report_date", None)
                else None
            ),
            broken_fiscal_year=getattr(report, "broken_fiscal_year", None),
        )


def _valid_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
    )


def _quantile(values: list[float], quantile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _field(value, name):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _matches_period(value, expected_period: str, expected_period_end: str | None) -> bool:
    period = value.get("period")
    period_end = value.get("period_end")
    return (period is None or period == expected_period) and (
        period_end is None or period_end == expected_period_end
    )


def _materially_differs(reported, canonical) -> bool:
    if not isinstance(reported, (int, float)) or isinstance(reported, bool):
        return False
    if not isfinite(reported):
        return False
    return abs(reported - canonical) > max(abs(reported), abs(canonical), 1.0) * 0.005


def _reconciliation_limitation(
    report_source_id, metric, period, reported, canonical, standardized_source_ids
) -> str:
    return (
        f"Report {report_source_id} states {metric}={reported:g} for {period}, "
        f"versus standardized history {metric}={canonical:g} from "
        f"{standardized_source_ids}; standardized history remains the calculation source."
    )
