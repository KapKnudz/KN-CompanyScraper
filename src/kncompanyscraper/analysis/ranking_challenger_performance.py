from dataclasses import asdict, dataclass
from datetime import date
from math import sqrt
from statistics import mean

from kncompanyscraper.analysis.base.performance_evaluator import BasePerformanceEvaluator
from kncompanyscraper.analysis.ranking_performance import (
    PortfolioReturn,
    RankingPerformanceEvaluator,
)


@dataclass(frozen=True)
class RankCorrelation:
    value: float | None
    company_count: int
    observed_count: int
    missing_company_ids: tuple[int, ...]


@dataclass(frozen=True)
class DecileSpread:
    value: float | None
    member_count: int
    top: PortfolioReturn
    bottom: PortfolioReturn


@dataclass(frozen=True)
class MembershipAttribution:
    value: float | None
    entrant_company_ids: tuple[int, ...]
    exit_company_ids: tuple[int, ...]
    entrants: PortfolioReturn
    exits: PortfolioReturn


@dataclass(frozen=True)
class RankingModelPerformance:
    company_count: int
    production_rank_correlation: RankCorrelation
    challenger_rank_correlation: RankCorrelation
    production_decile_spread: DecileSpread
    challenger_decile_spread: DecileSpread


@dataclass(frozen=True)
class RankingChallengerPerformanceEvaluation:
    challenger_snapshot_id: int
    horizon_months: int
    status: str
    start_date: str
    target_date: str
    production_top_30: PortfolioReturn
    challenger_top_30: PortfolioReturn
    production_rank_correlation: RankCorrelation
    challenger_rank_correlation: RankCorrelation
    production_decile_spread: DecileSpread
    challenger_decile_spread: DecileSpread
    membership_attribution: MembershipAttribution
    ranking_model_performance: dict[str, RankingModelPerformance]
    benchmark_return: float | None
    challenger_value_added: float | None
    production_excess_vs_benchmark: float | None
    challenger_excess_vs_benchmark: float | None
    stock_return_basis: str
    benchmark_code: str
    benchmark_return_basis: str
    comparison_basis: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class RankingChallengerPerformanceEvaluator(BasePerformanceEvaluator):
    POLICY_VERSION = "ranking-challenger-performance-v3-model-attribution"

    def __init__(self, valuation_repository, benchmark_repository, dividend_repository):
        super().__init__(valuation_repository, benchmark_repository, dividend_repository)
        self.base_evaluator = RankingPerformanceEvaluator(
            valuation_repository,
            benchmark_repository,
            dividend_repository,
        )

    def evaluate(
        self,
        snapshot: dict,
        horizon_months: int,
        *,
        as_of: date,
        benchmark_code: str = "OMXS30GI",
    ) -> RankingChallengerPerformanceEvaluation:
        if horizon_months <= 0:
            raise ValueError("horizon_months must be positive")
        start_date = date.fromisoformat(snapshot["source_as_of"])
        target_date = RankingPerformanceEvaluator._add_months(
            start_date, horizon_months
        )
        production_ids = tuple(snapshot["production_top_company_ids"])
        challenger_ids = tuple(snapshot["challenger_top_company_ids"])
        eligible_scores = [
            score
            for score in snapshot.get("scores", [])
            if score.get("rank_eligible", True)
        ]
        if len(eligible_scores) < 2:
            raise ValueError("challenger snapshot needs at least two eligible scores")
        eligible_ids = tuple(int(score["company_id"]) for score in eligible_scores)
        production_order = self._score_order(
            eligible_scores, "production_total_score"
        )
        challenger_order = self._score_order(
            eligible_scores, "challenger_total_score"
        )
        decile_count = max(1, len(eligible_scores) // 10)
        benchmark_basis = self.benchmark_repository.get_return_basis(benchmark_code)
        warnings = []

        observations = {}
        if target_date <= as_of:
            observations = {
                company_id: self.base_evaluator._company_total_return(
                    company_id, start_date, target_date
                )
                for company_id in eligible_ids
            }
            benchmark_return = (
                self.base_evaluator._benchmark_return(
                    benchmark_code, start_date, target_date
                )
                if benchmark_basis == "gross_total_return"
                else None
            )
        else:
            benchmark_return = None

        production_return = self._portfolio_return(production_ids, observations)
        challenger_return = self._portfolio_return(challenger_ids, observations)
        production_correlation = self._rank_correlation(
            eligible_scores,
            "production_total_score",
            observations,
        )
        challenger_correlation = self._rank_correlation(
            eligible_scores,
            "challenger_total_score",
            observations,
        )
        production_decile = self._decile_spread(
            production_order, decile_count, observations
        )
        challenger_decile = self._decile_spread(
            challenger_order, decile_count, observations
        )
        attribution = self._membership_attribution(
            production_ids, challenger_ids, observations
        )
        model_performance = self._ranking_model_performance(
            eligible_scores,
            observations,
        )

        if target_date > as_of:
            status = "pending"
            warnings.append("target date has not been reached")
        elif (
            production_return.value is None
            or challenger_return.value is None
            or production_correlation.value is None
            or challenger_correlation.value is None
            or production_decile.value is None
            or challenger_decile.value is None
            or benchmark_return is None
        ):
            status = "pending"
            warnings.append(
                "complete full-universe price, dividend, currency, and benchmark "
                "coverage is not yet available"
            )
        else:
            status = "complete"

        if benchmark_basis != "gross_total_return":
            warnings.append("OMXS30GI gross-total-return data is unavailable")
        return RankingChallengerPerformanceEvaluation(
            challenger_snapshot_id=snapshot["id"],
            horizon_months=horizon_months,
            status=status,
            start_date=start_date.isoformat(),
            target_date=target_date.isoformat(),
            production_top_30=production_return,
            challenger_top_30=challenger_return,
            production_rank_correlation=production_correlation,
            challenger_rank_correlation=challenger_correlation,
            production_decile_spread=production_decile,
            challenger_decile_spread=challenger_decile,
            membership_attribution=attribution,
            ranking_model_performance=model_performance,
            benchmark_return=benchmark_return,
            challenger_value_added=self._difference(
                challenger_return.value, production_return.value
            ),
            production_excess_vs_benchmark=self._difference(
                production_return.value, benchmark_return
            ),
            challenger_excess_vs_benchmark=self._difference(
                challenger_return.value, benchmark_return
            ),
            stock_return_basis="gross_total_return_reinvested_on_ex_date",
            benchmark_code=benchmark_code,
            benchmark_return_basis=benchmark_basis or "unavailable",
            comparison_basis=(
                f"gross_total_return_vs_{benchmark_basis or 'unavailable'}"
            ),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _score_order(scores: list[dict], field: str) -> tuple[int, ...]:
        return tuple(
            int(score["company_id"])
            for score in sorted(
                scores,
                key=lambda score: (
                    -float(score[field]),
                    int(score["company_id"]),
                ),
            )
        )

    def _rank_correlation(
        self,
        scores: list[dict],
        field: str,
        observations: dict[int, dict],
    ) -> RankCorrelation:
        missing = tuple(
            int(score["company_id"])
            for score in scores
            if observations.get(int(score["company_id"]), {}).get("total_return")
            is None
        )
        if missing:
            return RankCorrelation(
                None, len(scores), len(scores) - len(missing), missing
            )
        score_values = [float(score[field]) for score in scores]
        return_values = [
            float(observations[int(score["company_id"])]["total_return"])
            for score in scores
        ]
        value = self._pearson(
            self._average_ranks(score_values),
            self._average_ranks(return_values),
        )
        return RankCorrelation(value, len(scores), len(scores), ())

    def _decile_spread(
        self,
        order: tuple[int, ...],
        member_count: int,
        observations: dict[int, dict],
    ) -> DecileSpread:
        top = self._portfolio_return(order[:member_count], observations)
        bottom = self._portfolio_return(order[-member_count:], observations)
        return DecileSpread(
            self._difference(top.value, bottom.value),
            member_count,
            top,
            bottom,
        )

    def _membership_attribution(
        self,
        production_ids: tuple[int, ...],
        challenger_ids: tuple[int, ...],
        observations: dict[int, dict],
    ) -> MembershipAttribution:
        entrants = tuple(sorted(set(challenger_ids) - set(production_ids)))
        exits = tuple(sorted(set(production_ids) - set(challenger_ids)))
        entrant_return = self._portfolio_return(entrants, observations)
        exit_return = self._portfolio_return(exits, observations)
        return MembershipAttribution(
            self._difference(entrant_return.value, exit_return.value),
            entrants,
            exits,
            entrant_return,
            exit_return,
        )

    def _ranking_model_performance(
        self,
        scores: list[dict],
        observations: dict[int, dict],
    ) -> dict[str, RankingModelPerformance]:
        result = {}
        models = sorted(
            {score.get("ranking_model", "general") for score in scores}
        )
        for model in models:
            model_scores = [
                score
                for score in scores
                if score.get("ranking_model", "general") == model
            ]
            production_order = self._score_order(
                model_scores, "production_total_score"
            )
            challenger_order = self._score_order(
                model_scores, "challenger_total_score"
            )
            decile_count = max(1, len(model_scores) // 10)
            result[model] = RankingModelPerformance(
                company_count=len(model_scores),
                production_rank_correlation=self._rank_correlation(
                    model_scores,
                    "production_total_score",
                    observations,
                ),
                challenger_rank_correlation=self._rank_correlation(
                    model_scores,
                    "challenger_total_score",
                    observations,
                ),
                production_decile_spread=self._decile_spread(
                    production_order,
                    decile_count,
                    observations,
                ),
                challenger_decile_spread=self._decile_spread(
                    challenger_order,
                    decile_count,
                    observations,
                ),
            )
        return result

    @staticmethod
    def _portfolio_return(
        company_ids: tuple[int, ...], observations: dict[int, dict]
    ) -> PortfolioReturn:
        total_returns = []
        price_returns = []
        missing_price = []
        incomplete_dividends = []
        currency_mismatches = []
        dividend_reviews = []
        for company_id in company_ids:
            observation = observations.get(company_id, {})
            if observation.get("price_return") is not None:
                price_returns.append(observation["price_return"])
            if observation.get("total_return") is not None:
                total_returns.append(observation["total_return"])
            issue = observation.get("issue", "missing_price")
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
        return PortfolioReturn(
            mean(total_returns) if company_ids and not missing else None,
            len(company_ids),
            len(total_returns),
            missing,
            mean(price_returns)
            if company_ids and len(price_returns) == len(company_ids)
            else None,
            len(price_returns),
            tuple(missing_price),
            tuple(incomplete_dividends),
            tuple(currency_mismatches),
            tuple(dividend_reviews),
        )

    @staticmethod
    def _average_ranks(values: list[float]) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda item: item[1])
        ranks = [0.0] * len(values)
        start = 0
        while start < len(indexed):
            end = start + 1
            while end < len(indexed) and indexed[end][1] == indexed[start][1]:
                end += 1
            average_rank = (start + 1 + end) / 2
            for position in range(start, end):
                ranks[indexed[position][0]] = average_rank
            start = end
        return ranks

    @staticmethod
    def _pearson(left: list[float], right: list[float]) -> float | None:
        left_mean = mean(left)
        right_mean = mean(right)
        numerator = sum(
            (left_value - left_mean) * (right_value - right_mean)
            for left_value, right_value in zip(left, right)
        )
        left_variance = sum((value - left_mean) ** 2 for value in left)
        right_variance = sum((value - right_mean) ** 2 for value in right)
        denominator = sqrt(left_variance * right_variance)
        return numerator / denominator if denominator else None

