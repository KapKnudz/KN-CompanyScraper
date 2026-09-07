import json
from types import SimpleNamespace
from unittest.mock import patch

from kncompanyscraper.cli.ranking import _cmd_rank_analyzed_candidates, _verdict_label
from tests.test_agent_result_boundary import _v3_qualitative_response, valid_result


def test_rank_analyzed_candidates_runs_canonical_job_and_exports(tmp_path, capsys):
    output = tmp_path / "comparative-ranking.json"
    stored_run = {
        "id": 88,
        "scores": [
            {
                "rank": 1,
                "ticker": "TEST",
                "tier": "A",
                "base_band": [0.12, 0.18],
                "bear_lower_bound": -0.20,
                "evidence_confidence": "high",
            }
        ],
    }

    with (
        patch(
            "kncompanyscraper.jobs.comparative_ranking_job.ComparativeRankingJob"
        ) as job,
        patch(
            "kncompanyscraper.repositories.agent_cohort_repository.AgentCohortRepository"
        ) as cohorts,
        patch(
            "kncompanyscraper.repositories.analysis_repository.AnalysisRepository"
        ) as analyses,
        patch(
            "kncompanyscraper.repositories.ranking_repository.RankingRepository"
        ) as rankings,
        patch(
            "kncompanyscraper.repositories.thesis_challenge_repository.ThesisChallengeRepository"
        ) as challenges,
    ):
        job.return_value.run.return_value = SimpleNamespace(
            status="created",
            run_id=88,
        )
        rankings.return_value.get_run.return_value = stored_run

        _cmd_rank_analyzed_candidates(SimpleNamespace(output=output))

    job.assert_called_once_with(
        analyses.return_value,
        challenges.return_value,
        rankings.return_value,
        cohorts.return_value,
    )
    job.return_value.run.assert_called_once_with()
    rankings.return_value.get_run.assert_called_once_with(88)
    assert '"id": 88' in output.read_text()
    stdout = capsys.readouterr().out
    assert "Comparative ranking (Run 88)" in stdout
    assert "base=12.0%–18.0%" in stdout


def test_rank_analyzed_candidates_reports_missing_analyses(capsys):
    with patch(
        "kncompanyscraper.jobs.comparative_ranking_job.ComparativeRankingJob"
    ) as job:
        job.return_value.run.return_value = SimpleNamespace(
            status="no_analyses",
            run_id=None,
        )

        _cmd_rank_analyzed_candidates(SimpleNamespace(output=None))

    assert "No accepted individual theses found" in capsys.readouterr().out


def test_verdict_label_projects_v3_latent_case_type():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["verdict"] = "latent_case"
    payload["structured_conclusions"]["trigger"] = {
        "claim_id": "operating_trigger",
        "trigger_type": "operating",
        "unresolved_claim_code": "margin_recovery",
        "observable_metric_code": "ebit_margin",
        "threshold_code": "above_10_percent",
        "evidence_window": "0_12m",
        "single_observation_sufficient": True,
        "observation_requirement": "single_observation",
        "source_ids": ["news:21"],
        "limitation_codes": [],
    }

    assert _verdict_label({"content": payload, "metadata": {}}) == "operating-latent"
