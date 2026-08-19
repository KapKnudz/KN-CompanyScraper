from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.jobs.comparative_ranking_job import ComparativeRankingJob
from tests.test_comparative_ranking import stored_analysis
from tests.test_forward_scenario import analysis_with_returns


def test_monthly_job_persists_once_and_includes_challenge_blocks():
    analyses = MagicMock()
    analyses.get_latest_validated_stock_analyses.return_value = {
        1: stored_analysis(1, analysis_with_returns())
    }
    challenges = MagicMock()
    challenges.unresolved_high_company_ids.return_value = {1}
    rankings = MagicMock()
    rankings.get_latest_deterministic_run.return_value = {
        "id": 55,
        "scores": [
            {"company_id": 1, "rank_eligible": True},
            {"company_id": 2, "rank_eligible": False},
        ],
    }
    rankings.get_latest_monthly_run_before.return_value = None
    rankings.save_monthly_ranking_run.return_value = (88, True)
    cohorts = MagicMock()
    cohorts.get_for_month.return_value = None
    cohorts.get_latest_before.return_value = None
    cohorts.save.return_value = (66, True)

    result = ComparativeRankingJob(analyses, challenges, rankings, cohorts).run(
        as_of=date(2026, 8, 16)
    )

    assert result.status == "created"
    assert result.run_id == 88
    assert result.actionable_count == 0
    call = rankings.save_monthly_ranking_run.call_args.kwargs
    assert call["snapshot_month"] == date(2026, 8, 1)
    assert call["scores"][0]["tier"] == "RESEARCH"
    assert call["inputs_summary"]["deterministic_run_id"] == 55
    assert call["inputs_summary"]["deterministic_shortlist_company_ids"] == [1]
    assert call["inputs_summary"]["final_actionable_company_ids"] == []
    assert call["inputs_summary"]["agent_cohort_snapshot_id"] == 66
    assert call["inputs_summary"]["agent_cohort_company_ids"] == [1]
    assert call["inputs_summary"]["recall_universe_company_ids"] == [1]
    rankings.attach_cohort_provenance.assert_called_once_with(
        88,
        cohort_snapshot_id=66,
        cohort_company_ids=[1],
        recall_universe_company_ids=[1],
    )
    rankings.attach_tier_hysteresis_provenance.assert_called_once()
    assert call["inputs_summary"]["tier_hysteresis_policy_version"] == (
        "monthly-tier-hysteresis-v1"
    )


def test_monthly_job_retries_later_when_no_analyses_exist():
    analyses = MagicMock()
    analyses.get_latest_validated_stock_analyses.return_value = {}
    rankings = MagicMock()

    result = ComparativeRankingJob(analyses, MagicMock(), rankings).run(
        as_of=date(2026, 8, 16)
    )

    assert result.status == "no_analyses"
    rankings.save_monthly_ranking_run.assert_not_called()
