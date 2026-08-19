from unittest.mock import patch

from kncompanyscraper.main import _cmd_report_ranking_challengers


def _evaluation(status="complete"):
    return {
        "id": 1,
        "challenger_snapshot_id": 12,
        "snapshot_month": "2026-08-01",
        "horizon_months": 6,
        "target_date": "2027-02-18",
        "status": status,
        "policy_version": "ranking-challenger-performance-v2-rank-sensitive",
        "evaluated_at": "2027-02-19T00:00:00+00:00",
        "result": {
            "comparison_basis": "gross_total_return_vs_gross_total_return",
            "production_top_30": {
                "value": 0.08,
                "observed_count": 30,
                "company_count": 30,
            },
            "challenger_top_30": {
                "value": 0.10,
                "observed_count": 30,
                "company_count": 30,
            },
            "challenger_value_added": 0.02,
            "benchmark_return": 0.07,
            "production_rank_correlation": {
                "value": 0.05,
                "observed_count": 120,
                "company_count": 120,
                "missing_company_ids": [],
            },
            "challenger_rank_correlation": {
                "value": 0.12,
                "observed_count": 120,
                "company_count": 120,
                "missing_company_ids": [],
            },
            "production_decile_spread": {"value": -0.01},
            "challenger_decile_spread": {"value": 0.04},
            "membership_attribution": {
                "value": 0.06,
                "entrant_company_ids": [126],
                "exit_company_ids": [41],
            },
            "warnings": [],
        },
    }


def test_challenger_report_shows_rank_sensitive_metrics(capsys):
    with patch(
        "kncompanyscraper.repositories.ranking_challenger_repository."
        "RankingChallengerRepository.list_performance_evaluations",
        return_value=[_evaluation()],
    ):
        _cmd_report_ranking_challengers(None, 24)

    output = capsys.readouterr().out
    assert "Snapshot 2026-08-01 · challenger 12 · 6m" in output
    assert "Production top-30 return           8.0%  (30/30)" in output
    assert "Challenger rank correlation       0.120  (120/120)" in output
    assert "Challenger decile spread           4.0%" in output
    assert "entries=[126] exits=[41]" in output


def test_challenger_report_exposes_full_universe_blockers(capsys):
    row = _evaluation(status="pending")
    row["result"]["production_rank_correlation"].update(
        value=None,
        observed_count=118,
        missing_company_ids=[4, 9],
    )
    row["result"]["challenger_rank_correlation"].update(
        value=None,
        observed_count=118,
        missing_company_ids=[4, 9],
    )
    row["result"]["warnings"] = ["complete full-universe coverage is unavailable"]

    with patch(
        "kncompanyscraper.repositories.ranking_challenger_repository."
        "RankingChallengerRepository.list_performance_evaluations",
        return_value=[row],
    ):
        _cmd_report_ranking_challengers(12, 5)

    output = capsys.readouterr().out
    assert "Coverage blockers: full-universe companies [4, 9]" in output
    assert "Warning: complete full-universe coverage is unavailable" in output


def test_challenger_report_handles_no_evaluations(capsys):
    with patch(
        "kncompanyscraper.repositories.ranking_challenger_repository."
        "RankingChallengerRepository.list_performance_evaluations",
        return_value=[],
    ):
        _cmd_report_ranking_challengers(12, 5)

    assert (
        capsys.readouterr().out
        == "No stored challenger-performance evaluations for challenger snapshot 12.\n"
    )
