from dataclasses import dataclass
from datetime import date

from kncompanyscraper.analysis.ranking_performance import RankingPerformanceEvaluator


@dataclass(frozen=True)
class RankingChallengerPerformanceJobResult:
    evaluated_count: int
    complete_count: int
    pending_count: int


class RankingChallengerPerformanceJob:
    EVALUATION_HORIZONS = (1, 3, 6, 12, 24, 36, 48)

    def __init__(self, repository, evaluator):
        self.repository = repository
        self.evaluator = evaluator

    def run(
        self,
        *,
        as_of: date | None = None,
        max_horizon_months: int = 48,
    ) -> RankingChallengerPerformanceJobResult:
        as_of = as_of or date.today()
        evaluated = complete = pending = 0
        for snapshot in self.repository.list_snapshots():
            start_date = date.fromisoformat(snapshot["source_as_of"])
            for horizon in self.EVALUATION_HORIZONS:
                if horizon > max_horizon_months:
                    continue
                target_date = RankingPerformanceEvaluator._add_months(
                    start_date, horizon
                )
                if target_date > as_of:
                    continue
                result = self.evaluator.evaluate(snapshot, horizon, as_of=as_of)
                self.repository.save_performance_evaluation(
                    result,
                    self.evaluator.POLICY_VERSION,
                )
                evaluated += 1
                if result.status == "complete":
                    complete += 1
                else:
                    pending += 1
        return RankingChallengerPerformanceJobResult(
            evaluated, complete, pending
        )
