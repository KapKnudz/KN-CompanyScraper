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


def test_ranking_engine_has_model_version():
    engine = RankingEngine()
    assert engine.RANKING_MODEL_VERSION == "2026-08-09"


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
    assert call_args.kwargs["model_version"] == "2026-08-09"
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
