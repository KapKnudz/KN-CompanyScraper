from dataclasses import dataclass
from datetime import date

from kncompanyscraper.analysis.ranking_performance import RankingPerformanceEvaluator


@dataclass(frozen=True)
class RankingPerformanceJobResult:
    evaluated_count: int
    complete_count: int
    pending_count: int


class RankingPerformanceJob:
    def __init__(self, ranking_repository, evaluator):
        self.ranking_repository = ranking_repository
        self.evaluator = evaluator

    def run(
        self,
        *,
        as_of: date | None = None,
        max_horizon_months: int = 48,
    ) -> RankingPerformanceJobResult:
        as_of = as_of or date.today()
        evaluated = 0
        complete = 0
        pending = 0
        for ranking_run in self.ranking_repository.list_monthly_runs():
            inputs = ranking_run.get("inputs_summary") or {}
            if not inputs.get("as_of"):
                continue
            start_date = date.fromisoformat(inputs["as_of"])
            for horizon in range(1, max_horizon_months + 1):
                target_date = RankingPerformanceEvaluator._add_months(
                    start_date, horizon
                )
                if target_date > as_of:
                    break
                result = self.evaluator.evaluate(
                    ranking_run,
                    horizon,
                    as_of=as_of,
                )
                self.ranking_repository.save_performance_evaluation(
                    result,
                    RankingPerformanceEvaluator.POLICY_VERSION,
                )
                evaluated += 1
                if result.status == "complete":
                    complete += 1
                else:
                    pending += 1
        return RankingPerformanceJobResult(evaluated, complete, pending)
