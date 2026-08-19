from __future__ import annotations

import math
from calendar import monthrange
from datetime import date, timedelta
from statistics import mean
from typing import TYPE_CHECKING

from kncompanyscraper.analysis.backtesting.backtest_result import (
    CategoryCorrelation,
    CompanyAttribution,
    DecilePerformance,
    MetricAttribution,
    PeriodResult,
)
from kncompanyscraper.analysis.financial.financial_calculator import FinancialCalculator
from kncompanyscraper.analysis.financial.financial_mapper import FinancialMapper
from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
from kncompanyscraper.analysis.realized_total_return import (
    RealizedReturnObservation,
    RealizedTotalReturnCalculator,
)
from kncompanyscraper.analysis.valuation.raw_valuation import (
    compute_raw_valuation,
)
from kncompanyscraper.analysis.valuation.current_valuation import CurrentValuation
from kncompanyscraper.analysis.valuation.valuation_calculator import ValuationCalculator
from kncompanyscraper.analysis.valuation.valuation_mapper import ValuationMapper
from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.analysis.valuation.reverse_dcf_skill import ReverseDcfSkill
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.logger import get_logger

if TYPE_CHECKING:
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

logger = get_logger(__name__)

_CATEGORIES = (
    "quality_score",
    "growth_score",
    "valuation_score",
    "balance_sheet_score",
    "total_score",
)
_NUM_DECILES = 10
_ANNUAL_REPORT_LAG_DAYS = 90
_INTERIM_REPORT_LAG_DAYS = 45
_MAX_PRICE_AGE_DAYS = 7
_RETURN_HORIZONS = (6, 12, 24, 36, 48)

# KPIs we try to reconstruct from snapshot history for each backtest date.
_HISTORICAL_KPIS = (
    KpiIds.PE,
    KpiIds.EV_EBIT,
    KpiIds.EV_EBITDA,
    KpiIds.PB,
    KpiIds.PS,
    KpiIds.PFCF,
    KpiIds.PEG,
    KpiIds.DIVIDEND_YIELD,
    KpiIds.MARKET_CAP,
    KpiIds.ENTERPRISE_VALUE,
    KpiIds.ROIC,
    KpiIds.NET_DEBT_EBITDA,
    *KpiIds.PROPERTY_KPIS,
    *KpiIds.BANK_KPIS,
)


class BacktestEngine:
    def __init__(
        self,
        company_repository: CompanyRepository,
        financial_repository: FinancialRepository,
        valuation_repository: ValuationRepository,
        dividend_repository=None,
        benchmark_repository=None,
    ):
        self.company_repository = company_repository
        self.financial_repository = financial_repository
        self.valuation_repository = valuation_repository
        self.dividend_repository = dividend_repository
        self.benchmark_repository = benchmark_repository
        self.total_return_calculator = (
            RealizedTotalReturnCalculator(
                valuation_repository,
                dividend_repository,
            )
            if dividend_repository is not None
            else None
        )
        self.financial_mapper = FinancialMapper()
        self.financial_calculator = FinancialCalculator()
        self.valuation_mapper = ValuationMapper()
        self.valuation_calculator = ValuationCalculator()
        self.reverse_dcf_skill = ReverseDcfSkill(
            valuation_repository,
            financial_repository,
        )
        self.ranking_engine = RankingEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, num_periods: int = 12) -> list[PeriodResult]:
        companies = self.company_repository.get_backtest_companies()
        if not companies:
            logger.warning("No companies with price history — backtest aborted.")
            return []

        period_dates = self._find_period_dates(num_periods)
        if not period_dates:
            logger.warning("Insufficient price history for backtesting.")
            return []

        results: list[PeriodResult] = []
        for period_date in period_dates:
            period_result = self._run_single_period(companies, period_date)
            if period_result is not None:
                results.append(period_result)
            logger.info(
                "Backtest period %s: %d eligible companies",
                period_date,
                period_result.eligible_count if period_result else 0,
            )
        return results

    # ------------------------------------------------------------------
    # Period discovery
    # ------------------------------------------------------------------

    def _find_period_dates(self, num_periods: int) -> list[date]:
        """Return one market-wide observation date per calendar month."""
        today = date.today()
        return_cutoff = today - timedelta(days=365)
        last_complete_month_end = date(
            return_cutoff.year,
            return_cutoff.month,
            1,
        ) - timedelta(days=1)
        dates = self.valuation_repository.get_backtest_month_end_dates(
            min_date=today - timedelta(days=(num_periods + 48) * 31),
            max_date=last_complete_month_end,
        )
        return dates[-num_periods:]

    # ------------------------------------------------------------------
    # Single-period execution
    # ------------------------------------------------------------------

    def _run_single_period(self, companies, period_date: date) -> PeriodResult | None:
        results_by_company: dict[int, dict] = {}
        forward_returns: dict[int, dict[int, float | None]] = {}
        forward_observations = {}

        for company in companies:
            observation_price = self.valuation_repository.get_stock_price_on_date(
                company.id,
                period_date,
                max_age_days=_MAX_PRICE_AGE_DAYS,
            )
            if observation_price is None:
                continue
            financial, valuation, reverse_dcf, sector_kpis, fundamental_kpis = self._reconstruct(
                company,
                period_date,
                observation_price,
            )
            if financial is None:
                continue
            results_by_company[company.id] = {
                "financial": financial,
                "valuation": valuation,
                "reverse_dcf": reverse_dcf,
                "sector_kpis": sector_kpis,
                "fundamental_kpis": fundamental_kpis,
            }
            observations = self._forward_return_observations_by_horizon(
                company.id,
                period_date,
            )
            forward_observations[company.id] = observations
            forward_returns[company.id] = {
                horizon: observation.total_return
                for horizon, observation in observations.items()
            }

        if not results_by_company:
            return None

        ranking = self.ranking_engine.rank(companies, results_by_company)

        eligible = [s for s in ranking.scores if s.rank_eligible]
        eligible.sort(key=lambda s: s.total_score, reverse=True)
        if not eligible:
            return None

        deciles = self._build_deciles(eligible, forward_returns)
        companies_by_id = {company.id: company for company in companies}
        top = deciles[0] if deciles else None
        bot = deciles[-1] if deciles else None
        spreads = {}
        for horizon in _RETURN_HORIZONS:
            top_return = getattr(top, f"avg_{horizon}m_return", None)
            bottom_return = getattr(bot, f"avg_{horizon}m_return", None)
            spreads[horizon] = (
                top_return - bottom_return
                if top_return is not None and bottom_return is not None
                else None
            )
        benchmarks = {
            horizon: self._benchmark_return_for_horizon(period_date, horizon)
            for horizon in _RETURN_HORIZONS
        }
        attributions = self._build_attributions(
            period_date,
            eligible,
            companies_by_id,
            forward_observations,
            results_by_company,
            benchmarks,
        )
        metric_attributions = self._build_metric_attributions(
            period_date,
            eligible,
            companies_by_id,
            forward_observations,
            benchmarks,
        )
        top_excess = {}
        for horizon in _RETURN_HORIZONS:
            top_return = getattr(top, f"avg_{horizon}m_return", None)
            benchmark_return = benchmarks[horizon]
            top_excess[horizon] = (
                top_return - benchmark_return
                if top_return is not None and benchmark_return is not None
                else None
            )
        eligible_ids = [score.company_id for score in eligible]
        missing = {
            horizon: tuple(
                company_id
                for company_id in eligible_ids
                if forward_observations[company_id][horizon].total_return is None
            )
            for horizon in _RETURN_HORIZONS
        }

        # Category correlations
        correlations = self._compute_category_correlations(eligible, forward_returns)

        horizon_fields = {}
        for horizon in _RETURN_HORIZONS:
            horizon_fields.update(
                {
                    f"top_decile_spread_{horizon}m": spreads[horizon],
                    f"benchmark_{horizon}m_return": benchmarks[horizon],
                    f"top_decile_excess_{horizon}m": top_excess[horizon],
                    f"return_coverage_{horizon}m_count": (
                        len(eligible_ids) - len(missing[horizon])
                    ),
                    f"missing_return_company_ids_{horizon}m": missing[horizon],
                }
            )
        return PeriodResult(
            observation_date=period_date.isoformat(),
            deciles=deciles,
            attributions=attributions,
            metric_attributions=metric_attributions,
            correlations=correlations,
            return_basis=(
                "gross_total_return"
                if self.total_return_calculator is not None
                else "unavailable"
            ),
            company_count=len(companies),
            eligible_count=len(eligible),
            **horizon_fields,
        )

    # ------------------------------------------------------------------
    # Historical reconstruction
    # ------------------------------------------------------------------

    def _reconstruct(self, company, period_date: date, observation_price):
        """Reconstruct ranking inputs as they would have appeared on *period_date*."""
        # Financial data
        latest_year = self.financial_repository.get_latest_report_as_of(
            company.id,
            "year",
            period_date,
            availability_lag_days=_ANNUAL_REPORT_LAG_DAYS,
        )
        latest_r12 = self.financial_repository.get_latest_report_as_of(
            company.id,
            "r12",
            period_date,
            availability_lag_days=_INTERIM_REPORT_LAG_DAYS,
        )
        if latest_year is None:
            return None, None, None, {}, {}
        current_report = latest_r12 or latest_year

        historical_reports = self._historical_reports_as_of(company.id, period_date)
        current = self.financial_mapper.to_current(current_report)
        annual_current = self.financial_mapper.to_current(latest_year)
        historical = self.financial_mapper.to_historical(historical_reports)
        quarter_reports = self.financial_repository.get_reports_as_of(
            company.id,
            "quarter",
            period_date,
            availability_lag_days=_INTERIM_REPORT_LAG_DAYS,
        )
        latest_quarter = quarter_reports[0] if quarter_reports else None
        prior_year_quarter = None
        if latest_quarter is not None:
            prior_year_quarter = next(
                (
                    report
                    for report in quarter_reports[1:]
                    if report.period == latest_quarter.period
                    and report.year == latest_quarter.year - 1
                ),
                None,
            )
        financial = self.financial_calculator.calculate(
            current,
            historical,
            growth_current=annual_current,
            latest_quarter=(
                self.financial_mapper.to_current(latest_quarter)
                if latest_quarter
                else None
            ),
            prior_year_quarter=(
                self.financial_mapper.to_current(prior_year_quarter)
                if prior_year_quarter
                else None
            ),
        )

        # Point-in-time KPI evidence must be resolved before reverse DCF so the
        # reinvestment policy never uses today's ROIC in a historical period.
        kpi_snapshot = self.valuation_repository.get_snapshot_history_as_of(
            company.id, _HISTORICAL_KPIS, period_date
        )
        fundamental_sources = {
            kpi_id: "historical_snapshot"
            for kpi_id in KpiIds.GENERAL_FUNDAMENTAL_KPIS
            if kpi_snapshot.get(kpi_id) is not None
        }
        annual_fundamentals = self.valuation_repository.get_kpi_values_for_year(
            company.id,
            KpiIds.GENERAL_FUNDAMENTAL_KPIS,
            latest_year.year,
        )
        for kpi_id, value in annual_fundamentals.items():
            if kpi_snapshot.get(kpi_id) is None and value is not None:
                kpi_snapshot[kpi_id] = value
                fundamental_sources[kpi_id] = "annual_kpi_history"
        reverse_dcf = self.reverse_dcf_skill.analyze_reports(
            company,
            latest_annual=latest_year,
            latest_r12=latest_r12,
            history=historical_reports,
            price=observation_price,
            as_of=period_date,
            roic=kpi_snapshot.get(KpiIds.ROIC),
        )

        valuation = self._reconstruct_valuation(
            company.id,
            period_date,
            current_report,
            kpi_snapshot,
        )
        fundamental_kpis = {
            kpi_id: kpi_snapshot.get(kpi_id)
            for kpi_id in KpiIds.GENERAL_FUNDAMENTAL_KPIS
        }
        fundamental_kpis["_sources"] = fundamental_sources

        sector_kpis = {"current": {}, "histories": {}}
        if company.branch_id == 75:
            for kpi_id in KpiIds.PROPERTY_KPIS:
                value = kpi_snapshot.get(kpi_id)
                if value is not None:
                    sector_kpis["current"][kpi_id] = value
            # Also fetch dated histories for NOI/share and income/share
            sector_kpis["histories"] = self.valuation_repository.get_snapshot_history(
                company.id,
                (KpiIds.PROPERTY_NOI_PER_SHARE, KpiIds.PROPERTY_INCOME_PER_SHARE),
            )
            # Filter histories to only include observations up to period_date
            sector_kpis["histories"] = {
                kpi_id: [(d, v) for d, v in obs if d <= period_date]
                for kpi_id, obs in sector_kpis["histories"].items()
            }
        elif company.branch_id in (68, 69, 70):
            for kpi_id in KpiIds.BANK_KPIS:
                value = kpi_snapshot.get(kpi_id)
                if value is not None:
                    sector_kpis["current"][kpi_id] = value

        return financial, valuation, reverse_dcf, sector_kpis, fundamental_kpis

    def _historical_reports_as_of(self, company_id: int, as_of: date) -> list[Report]:
        """Historical annual reports with period_end ≤ *as_of*, excluding the latest."""
        reports = self.financial_repository.get_reports_as_of(
            company_id,
            "year",
            as_of,
            availability_lag_days=_ANNUAL_REPORT_LAG_DAYS,
        )
        return list(reversed(reports[1:]))  # exclude the latest, oldest-first

    def _reconstruct_valuation(
        self,
        company_id: int,
        period_date: date,
        report: Report | None,
        kpi_snapshot: dict[int, float | None],
    ) -> ValuationResult | None:
        """Build a ValuationResult as of *period_date* using raw price × report."""
        stock_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            period_date,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        raw = compute_raw_valuation(stock_price, report)

        pe_hist, ev_ebit_hist, pb_hist = self._historical_kpi_values(
            company_id,
            period_date,
        )
        current = CurrentValuation(
            market_cap=kpi_snapshot.get(KpiIds.MARKET_CAP),
            enterprise_value=kpi_snapshot.get(KpiIds.ENTERPRISE_VALUE),
            pe=kpi_snapshot.get(KpiIds.PE),
            ev_ebit=kpi_snapshot.get(KpiIds.EV_EBIT),
            ev_ebitda=kpi_snapshot.get(KpiIds.EV_EBITDA),
            pb=kpi_snapshot.get(KpiIds.PB),
            ps=kpi_snapshot.get(KpiIds.PS),
            pfcf=kpi_snapshot.get(KpiIds.PFCF),
            peg=kpi_snapshot.get(KpiIds.PEG),
            dividend_yield=kpi_snapshot.get(KpiIds.DIVIDEND_YIELD),
        )
        if raw.market_cap is not None:
            current.market_cap = raw.market_cap
        if raw.enterprise_value is not None:
            current.enterprise_value = raw.enterprise_value
        if raw.pe is not None:
            current.pe = raw.pe
        if raw.pfcf is not None:
            current.pfcf = raw.pfcf
        if raw.ev_ebit is not None:
            current.ev_ebit = raw.ev_ebit
        if raw.ev_ebitda is not None:
            current.ev_ebitda = raw.ev_ebitda
        if raw.pb is not None:
            current.pb = raw.pb
        if raw.ps is not None:
            current.ps = raw.ps
        historical = self.valuation_mapper.to_historical(pe_hist, ev_ebit_hist, pb_hist)
        return self.valuation_calculator.calculate(current, historical, raw)

    def _historical_kpi_values(
        self,
        company_id: int,
        as_of: date,
    ) -> tuple[list[float], list[float], list[float]]:
        """PE, EV/EBIT, PB history restricted to completed prior years."""
        return self.valuation_repository.get_historical_as_of(company_id, as_of)

    # ------------------------------------------------------------------
    # Forward returns
    # ------------------------------------------------------------------

    def _forward_returns(
        self,
        company_id: int,
        from_date: date,
    ) -> tuple[float | None, float | None]:
        """Compute coverage-certified gross total returns from *from_date*."""
        observations = self._forward_return_observations(company_id, from_date)
        return observations[0].total_return, observations[1].total_return

    def _forward_return_observations(
        self,
        company_id: int,
        from_date: date,
    ) -> tuple[RealizedReturnObservation, RealizedReturnObservation]:
        start_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            from_date,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        if self.total_return_calculator is None:
            unavailable = RealizedReturnObservation(
                None, None, "incomplete_dividends", None
            )
            return unavailable, unavailable
        return (
            self.total_return_calculator.calculate(
                company_id,
                start_price,
                from_date + timedelta(days=180),
            ),
            self.total_return_calculator.calculate(
                company_id,
                start_price,
                from_date + timedelta(days=365),
            ),
        )

    def _forward_return_observations_by_horizon(
        self,
        company_id: int,
        from_date: date,
    ) -> dict[int, RealizedReturnObservation]:
        observation_6m, observation_12m = self._forward_return_observations(
            company_id,
            from_date,
        )
        observations = {6: observation_6m, 12: observation_12m}
        start_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            from_date,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        for horizon in (24, 36, 48):
            if self.total_return_calculator is None:
                observation = RealizedReturnObservation(
                    None, None, "incomplete_dividends", None
                )
            else:
                observation = self.total_return_calculator.calculate(
                    company_id,
                    start_price,
                    self._add_months(from_date, horizon),
                )
            observations[horizon] = observation
        return observations

    def _benchmark_return_for_horizon(
        self, from_date: date, horizon_months: int
    ) -> float | None:
        target_date = self._add_months(from_date, horizon_months)
        return self._benchmark_return(
            from_date,
            (target_date - from_date).days,
        )

    def _benchmark_return(self, from_date: date, days: int) -> float | None:
        if (
            self.benchmark_repository is None
            or self.benchmark_repository.get_return_basis("OMXS30GI")
            != "gross_total_return"
        ):
            return None
        start = self.benchmark_repository.get_value_on_or_before(
            "OMXS30GI",
            from_date,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        end = self.benchmark_repository.get_value_on_or_before(
            "OMXS30GI",
            from_date + timedelta(days=days),
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        if start is None or end is None or start[1] <= 0:
            return None
        return end[1] / start[1] - 1.0

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, min(value.day, monthrange(year, month)[1]))

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_deciles(scores, forward_returns) -> list[DecilePerformance]:
        if len(scores) < _NUM_DECILES:
            return []

        deciles: list[DecilePerformance] = []
        for i in range(_NUM_DECILES):
            start = i * len(scores) // _NUM_DECILES
            end = (i + 1) * len(scores) // _NUM_DECILES
            bucket = scores[start:end]
            returns = {
                horizon: [
                    value
                    for score in bucket
                    if (
                        value := BacktestEngine._return_for_horizon(
                            forward_returns.get(score.company_id), horizon
                        )
                    )
                    is not None
                ]
                for horizon in _RETURN_HORIZONS
            }
            horizon_fields = {}
            for horizon, values in returns.items():
                horizon_fields.update(
                    {
                        f"avg_{horizon}m_return": (
                            mean(values) if values else None
                        ),
                        f"hit_rate_{horizon}m": (
                            sum(value > 0 for value in values) / len(values)
                            if values
                            else None
                        ),
                        f"count_{horizon}m": len(values),
                    }
                )
            deciles.append(
                DecilePerformance(
                    decile=i + 1,
                    count=len(bucket),
                    **horizon_fields,
                )
            )
        return deciles

    @staticmethod
    def _build_attributions(
        period_date,
        scores,
        companies_by_id,
        forward_observations,
        results_by_company=None,
        benchmarks=None,
    ) -> list[CompanyAttribution]:
        results_by_company = results_by_company or {}
        benchmarks = benchmarks or {}
        decile_by_company = {}
        counts_by_decile = {}
        if len(scores) >= _NUM_DECILES:
            for i in range(_NUM_DECILES):
                start = i * len(scores) // _NUM_DECILES
                end = (i + 1) * len(scores) // _NUM_DECILES
                bucket = scores[start:end]
                decile = i + 1
                counts_by_decile[decile] = {
                    horizon: sum(
                        BacktestEngine._observation_for_horizon(
                            forward_observations[score.company_id], horizon
                        ).total_return
                        is not None
                        for score in bucket
                    )
                    for horizon in _RETURN_HORIZONS
                }
                for score in bucket:
                    decile_by_company[score.company_id] = decile

        attributions = []
        for rank, score in enumerate(scores, 1):
            company = companies_by_id[score.company_id]
            observations = forward_observations[score.company_id]
            valuation = results_by_company.get(score.company_id, {}).get("valuation")
            decile = decile_by_company.get(score.company_id)
            counts = counts_by_decile.get(decile, {})
            horizon_fields = {}
            for horizon in _RETURN_HORIZONS:
                observation = BacktestEngine._observation_for_horizon(
                    observations, horizon
                )
                count = counts.get(horizon, 0)
                horizon_fields.update(
                    {
                        f"return_{horizon}m": observation.total_return,
                        f"price_return_{horizon}m": observation.price_return,
                        f"contribution_{horizon}m": (
                            observation.total_return / count
                            if observation.total_return is not None and count
                            else None
                        ),
                        f"return_issue_{horizon}m": observation.issue,
                        f"return_end_date_{horizon}m": (
                            observation.end_date.isoformat()
                            if observation.end_date is not None
                            else None
                        ),
                        f"benchmark_{horizon}m_return": benchmarks.get(horizon),
                    }
                )
            attributions.append(
                CompanyAttribution(
                    observation_date=period_date.isoformat(),
                    company_id=score.company_id,
                    company_name=company.name,
                    ticker=company.ticker,
                    rank=rank,
                    decile=decile,
                    quality_score=getattr(score, "quality_score", None),
                    growth_score=getattr(score, "growth_score", None),
                    valuation_score=getattr(score, "valuation_score", None),
                    balance_sheet_score=getattr(
                        score, "balance_sheet_score", None
                    ),
                    total_score=score.total_score,
                    sector_id=company.sector_id,
                    ranking_model=getattr(score, "ranking_model", None),
                    market_cap=(
                        valuation.raw_market_cap if valuation is not None else None
                    ),
                    **horizon_fields,
                )
            )
        return attributions

    def _compute_category_correlations(self, scores, forward_returns):
        correlations: list[CategoryCorrelation] = []
        for category in _CATEGORIES:
            pairs = {horizon: [] for horizon in _RETURN_HORIZONS}
            for score in scores:
                fwd = forward_returns.get(score.company_id)
                cat_value = getattr(score, category, None)
                if cat_value is None:
                    continue
                for horizon in _RETURN_HORIZONS:
                    value = self._return_for_horizon(fwd, horizon)
                    if value is not None:
                        pairs[horizon].append((cat_value, value))
            horizon_fields = {
                f"correlation_{horizon}m": (
                    self._pearson(pairs[horizon])
                    if len(pairs[horizon]) >= 5
                    else None
                )
                for horizon in _RETURN_HORIZONS
            }
            correlations.append(
                CategoryCorrelation(
                    category=category,
                    **horizon_fields,
                )
            )
        return correlations

    @staticmethod
    def _build_metric_attributions(
        period_date,
        scores,
        companies_by_id,
        forward_observations=None,
        benchmarks=None,
    ) -> list[MetricAttribution]:
        forward_observations = forward_observations or {}
        benchmarks = benchmarks or {}
        rows = []
        for score in scores:
            company = companies_by_id[score.company_id]
            observations = forward_observations.get(score.company_id)
            for category, audit in getattr(score, "scoring_audit", {}).items():
                for component in audit["components"]:
                    horizon_fields = {}
                    for horizon in _RETURN_HORIZONS:
                        observation = BacktestEngine._observation_for_horizon(
                            observations, horizon
                        )
                        horizon_fields.update(
                            {
                                f"return_{horizon}m": observation.total_return,
                                f"benchmark_{horizon}m_return": benchmarks.get(
                                    horizon
                                ),
                            }
                        )
                    rows.append(
                        MetricAttribution(
                            observation_date=period_date.isoformat(),
                            company_id=score.company_id,
                            company_name=company.name,
                            ticker=company.ticker,
                            ranking_model=score.ranking_model,
                            category=category,
                            metric=component["name"],
                            raw_value=component["raw_value"],
                            normalized_score=component["normalized_score"],
                            configured_weight=component["configured_weight"],
                            effective_weight=component["effective_weight"],
                            category_contribution=component["category_contribution"],
                            category_score=audit["production_score"],
                            reconstruction_error=audit["reconstruction_error"],
                            total_category_weight=audit["total_category_weight"],
                            total_contribution=component["total_contribution"],
                            available=component["available"],
                            transformation=component["transformation"],
                            dependencies="|".join(component["dependencies"]),
                            cross_category_dependencies="|".join(
                                component["cross_category_dependencies"]
                            ),
                            provenance=component["provenance"],
                            **horizon_fields,
                        )
                    )
        return rows

    @staticmethod
    def _return_for_horizon(values, horizon: int) -> float | None:
        if isinstance(values, dict):
            return values.get(horizon)
        if values is None:
            return None
        if horizon == 6 and len(values) > 0:
            return values[0]
        if horizon == 12 and len(values) > 1:
            return values[1]
        return None

    @staticmethod
    def _observation_for_horizon(
        observations, horizon: int
    ) -> RealizedReturnObservation:
        if isinstance(observations, dict):
            observation = observations.get(horizon)
        elif observations is not None and horizon == 6:
            observation = observations[0]
        elif observations is not None and horizon == 12:
            observation = observations[1]
        else:
            observation = None
        return observation or RealizedReturnObservation(
            None, None, "missing_price", None
        )

    @staticmethod
    def _pearson(pairs: list[tuple[float, float]]) -> float:
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        if len(xs) < 3:
            return 0.0
        mean_x = mean(xs)
        mean_y = mean(ys)
        num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
        denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
        if denom_x == 0 or denom_y == 0:
            return 0.0
        return num / (denom_x * denom_y)
