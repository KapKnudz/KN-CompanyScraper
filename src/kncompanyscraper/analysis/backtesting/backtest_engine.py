from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean
from typing import TYPE_CHECKING

from kncompanyscraper.analysis.backtesting.backtest_result import (
    CategoryCorrelation,
    DecilePerformance,
    PeriodResult,
)
from kncompanyscraper.analysis.financial.financial_calculator import FinancialCalculator
from kncompanyscraper.analysis.financial.financial_mapper import FinancialMapper
from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
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
    "reverse_dcf_score",
    "balance_sheet_score",
    "total_score",
)
_NUM_DECILES = 10
_ANNUAL_REPORT_LAG_DAYS = 90
_INTERIM_REPORT_LAG_DAYS = 45
_MAX_PRICE_AGE_DAYS = 7

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
)


class BacktestEngine:
    def __init__(
        self,
        company_repository: CompanyRepository,
        financial_repository: FinancialRepository,
        valuation_repository: ValuationRepository,
    ):
        self.company_repository = company_repository
        self.financial_repository = financial_repository
        self.valuation_repository = valuation_repository
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
        dates = self.valuation_repository.get_backtest_month_end_dates(
            min_date=today - timedelta(days=3 * 365),
            max_date=today - timedelta(days=365),
        )
        return dates[-num_periods:]

    # ------------------------------------------------------------------
    # Single-period execution
    # ------------------------------------------------------------------

    def _run_single_period(self, companies, period_date: date) -> PeriodResult | None:
        results_by_company: dict[int, dict] = {}
        forward_returns: dict[int, tuple[float | None, float | None]] = {}

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
            forward_returns[company.id] = self._forward_returns(company.id, period_date)

        if not results_by_company:
            return None

        ranking = self.ranking_engine.rank(companies, results_by_company)

        eligible = [s for s in ranking.scores if s.rank_eligible]
        eligible.sort(key=lambda s: s.total_score, reverse=True)
        if not eligible:
            return None

        deciles = self._build_deciles(eligible, forward_returns)

        top = deciles[0] if deciles else None
        bot = deciles[-1] if deciles else None
        spread_6m = (
            (top.avg_6m_return - bot.avg_6m_return)
            if top is not None
            and top.avg_6m_return is not None
            and bot is not None
            and bot.avg_6m_return is not None
            else None
        )
        spread_12m = (
            (top.avg_12m_return - bot.avg_12m_return)
            if top is not None
            and top.avg_12m_return is not None
            and bot is not None
            and bot.avg_12m_return is not None
            else None
        )

        # Category correlations
        correlations = self._compute_category_correlations(eligible, forward_returns)

        return PeriodResult(
            observation_date=period_date.isoformat(),
            deciles=deciles,
            correlations=correlations,
            top_decile_spread_6m=spread_6m,
            top_decile_spread_12m=spread_12m,
            company_count=len(companies),
            eligible_count=len(eligible),
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
        current_report = latest_r12 or latest_year
        if current_report is None:
            return None, None, None, {}, {}

        historical_reports = self._historical_reports_as_of(company.id, period_date)
        current = self.financial_mapper.to_current(current_report)
        historical = self.financial_mapper.to_historical(historical_reports)
        financial = self.financial_calculator.calculate(current, historical)
        reverse_dcf = self.reverse_dcf_skill.analyze_reports(
            company,
            latest_annual=latest_year,
            latest_r12=latest_r12,
            history=historical_reports,
            price=observation_price,
            as_of=period_date,
        )

        # KPI snapshots as of period_date
        kpi_snapshot = self.valuation_repository.get_snapshot_history_as_of(
            company.id, _HISTORICAL_KPIS, period_date
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
        """Compute price-only forward returns from *from_date*."""
        start_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            from_date,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        if start_price is None:
            return None, None

        ret_6m = self._price_return(company_id, from_date, 180)
        ret_12m = self._price_return(company_id, from_date, 365)
        return ret_6m, ret_12m

    def _price_return(
        self,
        company_id: int,
        from_date: date,
        days: int,
    ) -> float | None:
        target = from_date + timedelta(days=days)
        end_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            target,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        start_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            from_date,
            max_age_days=_MAX_PRICE_AGE_DAYS,
        )
        if end_price is None or start_price is None or start_price.close == 0:
            return None
        return (end_price.close - start_price.close) / start_price.close

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
            returns_6m = [
                forward_returns[score.company_id][0]
                for score in bucket
                if forward_returns.get(score.company_id, (None, None))[0] is not None
            ]
            returns_12m = [
                forward_returns[score.company_id][1]
                for score in bucket
                if forward_returns.get(score.company_id, (None, None))[1] is not None
            ]
            deciles.append(
                DecilePerformance(
                    decile=i + 1,
                    avg_6m_return=mean(returns_6m) if returns_6m else None,
                    avg_12m_return=mean(returns_12m) if returns_12m else None,
                    hit_rate_6m=(
                        sum(value > 0 for value in returns_6m) / len(returns_6m)
                        if returns_6m
                        else None
                    ),
                    hit_rate_12m=(
                        sum(value > 0 for value in returns_12m) / len(returns_12m)
                        if returns_12m
                        else None
                    ),
                    count=len(bucket),
                    count_6m=len(returns_6m),
                    count_12m=len(returns_12m),
                )
            )
        return deciles

    def _compute_category_correlations(self, scores, forward_returns):
        correlations: list[CategoryCorrelation] = []
        for category in _CATEGORIES:
            pairs_6m, pairs_12m = [], []
            for score in scores:
                fwd = forward_returns.get(score.company_id, (None, None))
                cat_value = getattr(score, category, None)
                if cat_value is None:
                    continue
                if fwd[0] is not None:
                    pairs_6m.append((cat_value, fwd[0]))
                if fwd[1] is not None:
                    pairs_12m.append((cat_value, fwd[1]))
            corr_6m = self._pearson(pairs_6m) if len(pairs_6m) >= 5 else None
            corr_12m = self._pearson(pairs_12m) if len(pairs_12m) >= 5 else None
            correlations.append(
                CategoryCorrelation(
                    category=category,
                    correlation_6m=corr_6m,
                    correlation_12m=corr_12m,
                )
            )
        return correlations

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
