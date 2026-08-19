from dataclasses import asdict, dataclass
from datetime import date
from calendar import monthrange
from statistics import mean

from kncompanyscraper.analysis.base.performance_evaluator import BasePerformanceEvaluator


@dataclass(frozen=True)
class PortfolioReturn:
    value: float | None
    company_count: int
    observed_count: int
    missing_company_ids: tuple[int, ...]
    price_value: float | None = None
    price_observed_count: int = 0
    missing_price_company_ids: tuple[int, ...] = ()
    incomplete_dividend_company_ids: tuple[int, ...] = ()
    currency_mismatch_company_ids: tuple[int, ...] = ()
    dividend_review_company_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class CohortRecall:
    value: float | None
    cohort_count: int
    universe_count: int
    observed_count: int
    winner_count: int
    captured_winner_count: int | None
    missing_company_ids: tuple[int, ...]
    missing_price_company_ids: tuple[int, ...] = ()
    incomplete_dividend_company_ids: tuple[int, ...] = ()
    currency_mismatch_company_ids: tuple[int, ...] = ()
    dividend_review_company_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class RankingPerformanceEvaluation:
    ranking_run_id: int
    horizon_months: int
    status: str
    start_date: str
    target_date: str
    final_ranking: PortfolioReturn
    individual_thesis_ranking: PortfolioReturn
    deterministic_shortlist: PortfolioReturn
    cohort_recall_at_30: CohortRecall
    benchmark_return: float | None
    agent_value_added: float | None
    comparative_agent_value_added: float | None
    excess_vs_benchmark: float | None
    stock_return_basis: str
    benchmark_code: str
    benchmark_return_basis: str
    comparison_basis: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class RankingPerformanceEvaluator(BasePerformanceEvaluator):
    POLICY_VERSION = "ranking-performance-v3-dividend-review"

    def evaluate(
        self,
        ranking_run: dict,
        horizon_months: int,
        *,
        as_of: date,
        benchmark_code: str = "OMXS30GI",
    ) -> RankingPerformanceEvaluation:
        if horizon_months <= 0:
            raise ValueError("horizon_months must be positive")
        inputs = ranking_run.get("inputs_summary") or {}
        start_date = date.fromisoformat(inputs["as_of"])
        target_date = self._add_months(start_date, horizon_months)
        individual_ids = tuple(inputs.get("final_actionable_company_ids") or [])
        has_comparative_review = "comparative_final_actionable_company_ids" in inputs
        final_ids = tuple(
            inputs.get("comparative_final_actionable_company_ids") or []
        )
        deterministic_ids = tuple(
            inputs.get("deterministic_shortlist_company_ids") or []
        )
        cohort_ids = tuple(inputs.get("agent_cohort_company_ids") or [])
        recall_universe_ids = tuple(inputs.get("recall_universe_company_ids") or [])
        benchmark_basis = self.benchmark_repository.get_return_basis(benchmark_code)

        if target_date > as_of:
            final_return = PortfolioReturn(None, len(final_ids), 0, final_ids)
            individual_return = PortfolioReturn(
                None, len(individual_ids), 0, individual_ids
            )
            deterministic_return = PortfolioReturn(
                None, len(deterministic_ids), 0, deterministic_ids
            )
            recall = CohortRecall(
                None,
                len(cohort_ids),
                len(recall_universe_ids),
                0,
                min(30, len(recall_universe_ids)),
                None,
                recall_universe_ids,
            )
            benchmark_return = None
        else:
            final_return = self._portfolio_return(final_ids, start_date, target_date)
            individual_return = self._portfolio_return(
                individual_ids, start_date, target_date
            )
            deterministic_return = self._portfolio_return(
                deterministic_ids, start_date, target_date
            )
            recall = self._cohort_recall(
                cohort_ids,
                recall_universe_ids,
                start_date,
                target_date,
            )
            benchmark_return = (
                self._benchmark_return(benchmark_code, start_date, target_date)
                if benchmark_basis == "gross_total_return"
                else None
            )
        warnings = []
        if benchmark_basis != "gross_total_return":
            warnings.append("OMXS30GI gross-total-return data is unavailable")

        if target_date > as_of:
            status = "pending"
            warnings.append("target date has not been reached")
        elif not has_comparative_review:
            status = "insufficient_membership"
            warnings.append("comparative agent review is missing")
        elif not final_ids or not individual_ids or not deterministic_ids or not cohort_ids or not recall_universe_ids:
            status = "insufficient_membership"
            warnings.append("snapshot membership is missing")
        elif (
            final_return.value is None
            or individual_return.value is None
            or deterministic_return.value is None
            or benchmark_return is None
            or recall.value is None
        ):
            status = "pending"
            warnings.append(
                "complete price, dividend, and currency coverage is not yet available"
            )
        else:
            status = "complete"

        agent_value_added = (
            final_return.value - deterministic_return.value
            if final_return.value is not None and deterministic_return.value is not None
            else None
        )
        comparative_agent_value_added = (
            final_return.value - individual_return.value
            if final_return.value is not None and individual_return.value is not None
            else None
        )
        excess_vs_benchmark = (
            final_return.value - benchmark_return
            if final_return.value is not None and benchmark_return is not None
            else None
        )
        return RankingPerformanceEvaluation(
            ranking_run_id=ranking_run["id"],
            horizon_months=horizon_months,
            status=status,
            start_date=start_date.isoformat(),
            target_date=target_date.isoformat(),
            final_ranking=final_return,
            individual_thesis_ranking=individual_return,
            deterministic_shortlist=deterministic_return,
            cohort_recall_at_30=recall,
            benchmark_return=benchmark_return,
            agent_value_added=agent_value_added,
            comparative_agent_value_added=comparative_agent_value_added,
            excess_vs_benchmark=excess_vs_benchmark,
            stock_return_basis="gross_total_return_reinvested_on_ex_date",
            benchmark_code=benchmark_code,
            benchmark_return_basis=benchmark_basis or "unavailable",
            comparison_basis=f"gross_total_return_vs_{benchmark_basis or 'unavailable'}",
            warnings=tuple(warnings),
        )

    def _portfolio_return(
        self,
        company_ids: tuple[int, ...],
        start_date: date,
        target_date: date,
    ) -> PortfolioReturn:
        returns = []
        price_returns = []
        missing_price = []
        incomplete_dividends = []
        currency_mismatches = []
        dividend_reviews = []
        for company_id in company_ids:
            observation = self._company_total_return(
                company_id, start_date, target_date
            )
            if observation["price_return"] is not None:
                price_returns.append(observation["price_return"])
            if observation["total_return"] is not None:
                returns.append(observation["total_return"])
            issue = observation["issue"]
            if issue == "missing_price":
                missing_price.append(company_id)
            elif issue == "incomplete_dividends":
                incomplete_dividends.append(company_id)
            elif issue == "currency_mismatch":
                currency_mismatches.append(company_id)
            elif issue == "dividend_review_required":
                dividend_reviews.append(company_id)
        missing = tuple(
            missing_price
            + incomplete_dividends
            + currency_mismatches
            + dividend_reviews
        )
        value = mean(returns) if company_ids and not missing else None
        price_value = (
            mean(price_returns)
            if company_ids and len(price_returns) == len(company_ids)
            else None
        )
        return PortfolioReturn(
            value,
            len(company_ids),
            len(returns),
            missing,
            price_value,
            len(price_returns),
            tuple(missing_price),
            tuple(incomplete_dividends),
            tuple(currency_mismatches),
            tuple(dividend_reviews),
        )

    def _cohort_recall(
        self,
        cohort_ids: tuple[int, ...],
        universe_ids: tuple[int, ...],
        start_date: date,
        target_date: date,
    ) -> CohortRecall:
        returns = {}
        missing_price = []
        incomplete_dividends = []
        currency_mismatches = []
        dividend_reviews = []
        for company_id in universe_ids:
            observation = self._company_total_return(
                company_id, start_date, target_date
            )
            if observation["total_return"] is not None:
                returns[company_id] = observation["total_return"]
            elif observation["issue"] == "missing_price":
                missing_price.append(company_id)
            elif observation["issue"] == "incomplete_dividends":
                incomplete_dividends.append(company_id)
            elif observation["issue"] == "currency_mismatch":
                currency_mismatches.append(company_id)
            elif observation["issue"] == "dividend_review_required":
                dividend_reviews.append(company_id)
        missing = tuple(
            missing_price
            + incomplete_dividends
            + currency_mismatches
            + dividend_reviews
        )
        winner_count = min(30, len(universe_ids))
        if not cohort_ids or not universe_ids or missing:
            return CohortRecall(
                None,
                len(cohort_ids),
                len(universe_ids),
                len(returns),
                winner_count,
                None,
                missing,
                tuple(missing_price),
                tuple(incomplete_dividends),
                tuple(currency_mismatches),
                tuple(dividend_reviews),
            )
        winners = {
            company_id
            for company_id, _ in sorted(
                returns.items(), key=lambda item: (-item[1], item[0])
            )[:winner_count]
        }
        captured = len(winners & set(cohort_ids))
        return CohortRecall(
            captured / winner_count,
            len(cohort_ids),
            len(universe_ids),
            len(returns),
            winner_count,
            captured,
            (),
        )

