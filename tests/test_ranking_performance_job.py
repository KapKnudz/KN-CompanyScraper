from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.jobs.ranking_performance_job import RankingPerformanceJob


def test_job_evaluates_each_completed_month_once_per_snapshot():
    rankings = MagicMock()
    rankings.list_monthly_runs.return_value = [
        {"id": 12, "inputs_summary": {"as_of": "2026-01-31"}}
    ]
    evaluator = MagicMock()
    evaluator.evaluate.side_effect = [
        MagicMock(status="complete"),
        MagicMock(status="pending"),
    ]

    result = RankingPerformanceJob(rankings, evaluator).run(
        as_of=date(2026, 3, 31), max_horizon_months=4
    )

    assert result.evaluated_count == 2
    assert result.complete_count == 1
    assert result.pending_count == 1
    assert evaluator.evaluate.call_count == 2
    assert rankings.save_performance_evaluation.call_count == 2
