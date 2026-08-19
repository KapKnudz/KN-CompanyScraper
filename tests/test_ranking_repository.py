import json
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.analysis.ranking.company_score import CompanyScore
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
from kncompanyscraper.repositories.ranking_repository import RankingRepository


def test_company_score_to_dict():
    cs = CompanyScore(
        company_id=1,
        ticker="TST",
        name="Test",
        quality_score=75.5,
        growth_score=60.0,
        valuation_score=80.2,
        balance_sheet_score=45.0,
        total_score=68.7,
        positives=["Strong ROE", "Attractive FCF yield"],
        negatives=["High leverage"],
        missing_data=["ROIC not available"],
        flags=["cheap_quality"],
        data_quality="high",
        candidate_reason="High-quality company with attractive valuation.",
        ranking_model="general",
        rank_eligible=True,
        eligibility_reasons=[],
    )
    d = cs.to_dict()

    assert d["company_id"] == 1
    assert d["ticker"] == "TST"
    assert d["quality_score"] == 75.5
    assert d["total_score"] == 68.7
    assert d["positives"] == ["Strong ROE", "Attractive FCF yield"]
    assert d["flags"] == ["cheap_quality"]
    assert d["data_quality"] == "high"
    assert d["rank_eligible"] is True
    assert d["ranking_model"] == "general"


def test_company_score_to_dict_is_json_serializable():
    cs = CompanyScore(
        company_id=1,
        ticker="TST",
        name="Test",
        total_score=50.0,
        positives=["Good"],
        negatives=[],
        missing_data=[],
        flags=[],
        eligibility_reasons=[],
    )
    # Should not raise
    json.dumps(cs.to_dict())


def test_save_ranking_run_inserts_row():
    repository = RankingRepository()
    cursor = MagicMock()
    cursor.fetchone.return_value = [42]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("kncompanyscraper.repositories.ranking_repository.get_connection", return_value=conn):
        run_id = repository.save_ranking_run(
            model_version="2026-08-09",
            company_count=10,
            eligible_count=8,
            scores=[{"company_id": 1, "total_score": 75.0}],
            inputs_summary={"total": 10},
        )

    assert run_id == 42
    assert cursor.execute.called


def test_save_monthly_ranking_run_is_idempotent():
    from datetime import date

    repository = RankingRepository()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, [42]]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("kncompanyscraper.repositories.ranking_repository.get_connection", return_value=conn):
        run_id, created = repository.save_monthly_ranking_run(
            snapshot_month=date(2026, 8, 1),
            model_version="combined-v1",
            company_count=2,
            eligible_count=1,
            scores=[],
            inputs_summary={},
        )

    assert run_id == 42
    assert created is False
    assert cursor.execute.call_count == 2


def test_get_recent_runs_returns_list():
    from datetime import datetime, timezone

    repository = RankingRepository()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "id": 1,
            "run_at": datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc),
            "model_version": "2026-08-09",
            "company_count": 10,
            "eligible_count": 7,
            "scores": {"scores": []},
            "inputs_summary": {},
        }
    ]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("kncompanyscraper.repositories.ranking_repository.get_connection", return_value=conn):
        runs = repository.get_recent_runs(limit=5)

    assert len(runs) == 1
    assert runs[0]["id"] == 1
    assert runs[0]["model_version"] == "2026-08-09"


def test_get_run_returns_none_for_missing_id():
    repository = RankingRepository()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("kncompanyscraper.repositories.ranking_repository.get_connection", return_value=conn):
        result = repository.get_run(999)

    assert result is None


def test_get_latest_deterministic_run_returns_frozen_scores():
    from datetime import date, datetime, timezone

    repository = RankingRepository()
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "id": 7,
        "run_at": datetime(2026, 8, 16, tzinfo=timezone.utc),
        "model_version": "deterministic-v1",
        "company_count": 2,
        "eligible_count": 1,
        "scores": [{"company_id": 1, "rank_eligible": True}],
        "inputs_summary": {"ranking_type": "deterministic_watchlist"},
    }
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch(
        "kncompanyscraper.repositories.ranking_repository.get_connection",
        return_value=conn,
    ):
        result = repository.get_latest_deterministic_run(date(2026, 8, 16))

    assert result["id"] == 7
    assert result["scores"][0]["company_id"] == 1
    assert "combined_forward_scenario" in cursor.execute.call_args.args[0]


def test_complete_performance_evaluation_is_not_overwritten():
    repository = RankingRepository()
    evaluation = MagicMock(
        ranking_run_id=12,
        horizon_months=1,
        target_date="2026-02-28",
        status="complete",
    )
    evaluation.to_dict.return_value = {"status": "complete"}
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, [91]]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch(
        "kncompanyscraper.repositories.ranking_repository.get_connection",
        return_value=conn,
    ):
        evaluation_id, changed = repository.save_performance_evaluation(
            evaluation, "ranking-performance-v1"
        )

    assert evaluation_id == 91
    assert changed is False
    assert "status <> 'complete'" in cursor.execute.call_args_list[0].args[0]


def test_list_performance_evaluations_returns_snapshot_provenance():
    from datetime import date, datetime, timezone

    repository = RankingRepository()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "id": 91,
            "ranking_run_id": 12,
            "horizon_months": 6,
            "target_date": date(2027, 2, 1),
            "status": "complete",
            "policy_version": "ranking-performance-v2-gross-total-return",
            "result": {"agent_value_added": 0.03},
            "evaluated_at": datetime(2027, 2, 2, tzinfo=timezone.utc),
            "snapshot_month": date(2026, 8, 1),
        }
    ]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch(
        "kncompanyscraper.repositories.ranking_repository.get_connection",
        return_value=conn,
    ):
        rows = repository.list_performance_evaluations(
            ranking_run_id=12,
            limit=5,
        )

    assert rows == [
        {
            "id": 91,
            "ranking_run_id": 12,
            "snapshot_month": "2026-08-01",
            "horizon_months": 6,
            "target_date": "2027-02-01",
            "status": "complete",
            "policy_version": "ranking-performance-v2-gross-total-return",
            "result": {"agent_value_added": 0.03},
            "evaluated_at": "2027-02-02T00:00:00+00:00",
        }
    ]
    assert "evaluation.ranking_run_id = %s" in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1] == (12, 5)


def test_ranking_engine_has_model_version():
    engine = RankingEngine()
    assert engine.RANKING_MODEL_VERSION == "2026-08-12-reverse-dcf-v10"


def test_ranking_engine_persists_when_repository_provided():
    repository = MagicMock()
    repository.save_ranking_run.return_value = 1
    engine = RankingEngine(ranking_repository=repository)

    from kncompanyscraper.analysis.financial.financial_result import FinancialResult
    from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
    from kncompanyscraper.models.company import Company

    company = Company(1, "TST", "TST", None, None, None)
    results = {
        1: {
            "financial": FinancialResult(
                operating_margin=0.15,
                net_margin=0.10,
                fcf_margin=0.08,
                revenue_growth=0.10,
                ebit_growth=0.12,
                net_income_growth=0.14,
                roe=0.20,
                roa=0.10,
                debt_to_equity=0.5,
            ),
            "valuation": ValuationResult(
                pe=12.0,
                ev_ebit=10.0,
                ev_ebitda=None,
                pb=None,
                ps=None,
                pfcf=None,
                peg=None,
                earnings_yield=0.08,
                free_cash_flow_yield=0.07,
                pe_vs_5y_avg=None,
                ev_ebit_vs_5y_avg=None,
                pb_vs_5y_avg=None,
                pe_percentile=20.0,
                ev_ebit_percentile=25.0,
            ),
        }
    }

    engine.rank([company], results)

    repository.save_ranking_run.assert_called_once()
    call_args = repository.save_ranking_run.call_args
    assert call_args.kwargs["model_version"] == "2026-08-12-reverse-dcf-v10"
    assert call_args.kwargs["company_count"] == 1
    assert call_args.kwargs["eligible_count"] == 1
    assert len(call_args.kwargs["scores"]) == 1
    assert call_args.kwargs["scores"][0]["ticker"] == "TST"


def test_ranking_engine_does_not_persist_when_repository_absent():
    engine = RankingEngine(ranking_repository=None)

    from kncompanyscraper.analysis.financial.financial_result import FinancialResult
    from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
    from kncompanyscraper.models.company import Company

    company = Company(1, "TST", "TST", None, None, None)
    results = {
        1: {
            "financial": FinancialResult(
                operating_margin=0.15,
                net_margin=0.10,
                fcf_margin=0.08,
                revenue_growth=0.10,
                ebit_growth=0.12,
                net_income_growth=0.14,
                roe=0.20,
                roa=0.10,
                debt_to_equity=0.5,
            ),
            "valuation": ValuationResult(
                pe=12.0,
                ev_ebit=10.0,
                ev_ebitda=None,
                pb=None,
                ps=None,
                pfcf=None,
                peg=None,
                earnings_yield=0.08,
                free_cash_flow_yield=0.07,
                pe_vs_5y_avg=None,
                ev_ebit_vs_5y_avg=None,
                pb_vs_5y_avg=None,
                pe_percentile=20.0,
                ev_ebit_percentile=25.0,
            ),
        }
    }

    ranking = engine.rank([company], results)
    assert len(ranking.scores) == 1
    # Should not raise — repository is optional
