from unittest.mock import patch

from kncompanyscraper.main import _cmd_report_ranking_performance


def evaluation(status="complete"):
    return {
        "id": 91,
        "ranking_run_id": 12,
        "snapshot_month": "2026-08-01",
        "horizon_months": 6,
        "target_date": "2027-02-01",
        "status": status,
        "policy_version": "ranking-performance-v2-gross-total-return",
        "evaluated_at": "2027-02-02T00:00:00+00:00",
        "result": {
            "comparison_basis": "gross_total_return_vs_gross_total_return",
            "deterministic_shortlist": {
                "value": 0.08,
                "price_value": 0.06,
                "observed_count": 30,
                "company_count": 30,
            },
            "individual_thesis_ranking": {
                "value": 0.10,
                "price_value": 0.08,
                "observed_count": 8,
                "company_count": 8,
            },
            "final_ranking": {
                "value": 0.12,
                "price_value": 0.10,
                "observed_count": 6,
                "company_count": 6,
            },
            "benchmark_return": 0.07,
            "agent_value_added": 0.04,
            "comparative_agent_value_added": 0.02,
            "excess_vs_benchmark": 0.05,
            "cohort_recall_at_30": {
                "value": 0.70,
                "captured_winner_count": 21,
                "winner_count": 30,
            },
            "warnings": [],
        },
    }


def test_performance_report_shows_independent_stage_attribution(capsys):
    with patch(
        "kncompanyscraper.repositories.ranking_repository."
        "RankingRepository.list_performance_evaluations",
        return_value=[evaluation()],
    ):
        _cmd_report_ranking_performance(None, 24)

    output = capsys.readouterr().out
    assert "Snapshot 2026-08-01 · run 12 · 6m" in output
    assert "Deterministic shortlist          8.0%      6.0%   30/30" in output
    assert "Individual theses               10.0%      8.0%    8/8" in output
    assert "Comparative final               12.0%     10.0%    6/6" in output
    assert "Agent value added                 4.0%" in output
    assert "Comparative-agent increment       2.0%" in output
    assert "Cohort recall@30                 70.0%  (21/30)" in output


def test_performance_report_exposes_coverage_blockers(capsys):
    row = evaluation(status="pending")
    row["result"]["final_ranking"] = {
        "value": None,
        "price_value": 0.10,
        "observed_count": 4,
        "company_count": 6,
        "incomplete_dividend_company_ids": [4],
        "currency_mismatch_company_ids": [7],
    }
    row["result"]["warnings"] = ["complete coverage is not yet available"]

    with patch(
        "kncompanyscraper.repositories.ranking_repository."
        "RankingRepository.list_performance_evaluations",
        return_value=[row],
    ):
        _cmd_report_ranking_performance(12, 5)

    output = capsys.readouterr().out
    assert "Status: pending" in output
    assert "final: incomplete dividends [4]" in output
    assert "final: currency mismatch [7]" in output
    assert "Warning: complete coverage is not yet available" in output


def test_performance_report_handles_no_stored_evaluations(capsys):
    with patch(
        "kncompanyscraper.repositories.ranking_repository."
        "RankingRepository.list_performance_evaluations",
        return_value=[],
    ):
        _cmd_report_ranking_performance(60, 5)

    assert (
        capsys.readouterr().out
        == "No stored ranking-performance evaluations for ranking run 60.\n"
    )
