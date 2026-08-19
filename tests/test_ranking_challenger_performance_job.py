from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.jobs.ranking_challenger_performance_job import (
    RankingChallengerPerformanceJob,
)


def test_job_only_evaluates_matured_named_horizons():
    repository = MagicMock()
    repository.list_snapshots.return_value = [
        {"id": 1, "source_as_of": "2026-01-31"}
    ]
    evaluator = MagicMock(POLICY_VERSION="performance-v2")
    evaluator.evaluate.side_effect = [
        MagicMock(status="complete"),
        MagicMock(status="pending"),
    ]

    result = RankingChallengerPerformanceJob(repository, evaluator).run(
        as_of=date(2026, 4, 30),
        max_horizon_months=12,
    )

    assert [call.args[1] for call in evaluator.evaluate.call_args_list] == [1, 3]
    assert result.evaluated_count == 2
    assert result.complete_count == 1
    assert result.pending_count == 1
    assert repository.save_performance_evaluation.call_count == 2


def test_job_honors_maximum_horizon():
    repository = MagicMock()
    repository.list_snapshots.return_value = [
        {"id": 1, "source_as_of": "2025-01-31"}
    ]
    evaluator = MagicMock(POLICY_VERSION="performance-v2")
    evaluator.evaluate.return_value = MagicMock(status="complete")

    RankingChallengerPerformanceJob(repository, evaluator).run(
        as_of=date(2026, 8, 18),
        max_horizon_months=5,
    )

    assert [call.args[1] for call in evaluator.evaluate.call_args_list] == [1, 3]
