from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.analysis.ranking_challenger import RankingChallenger
from kncompanyscraper.analysis.ranking_challenger_performance import (
    RankingChallengerPerformanceEvaluator,
)
from kncompanyscraper.repositories.ranking_challenger_repository import (
    RankingChallengerRepository,
)


def _category(components, weight):
    return {
        "production_score": 0.0,
        "total_category_weight": weight,
        "components": [
            {
                "name": name,
                "normalized_score": score,
                "configured_weight": component_weight,
                "available": available,
            }
            for name, score, component_weight, available in components
        ],
    }


def _general_score(company_id=1, total_score=50.0):
    return {
        "company_id": company_id,
        "ticker": f"C{company_id}",
        "name": f"Company {company_id}",
        "ranking_model": "general",
        "rank_eligible": True,
        "quality_score": 50.0,
        "growth_score": 50.0,
        "valuation_score": 50.0,
        "balance_sheet_score": 50.0,
        "total_score": total_score,
        "scoring_audit": {
            "quality": _category(
                [("roe", 80.0, 1.0, True), ("net_margin", 20.0, 1.0, True)],
                0.30,
            ),
            "growth": _category([("growth", 60.0, 1.0, True)], 0.25),
            "valuation": _category(
                [
                    ("fcf_yield", 70.0, 1.0, True),
                    ("ev_ebit_percentile", 10.0, 1.0, True),
                    ("missing", None, 5.0, False),
                ],
                0.30,
            ),
            "balance_sheet": _category([("leverage", 40.0, 1.0, True)], 0.15),
        },
    }


def test_challenger_reweights_remaining_metrics_and_does_not_mutate_source():
    run = {
        "id": 7,
        "run_at": "2026-08-18T09:00:00+02:00",
        "scores": [
            _general_score(),
            {
                "company_id": 2,
                "ticker": "BANK",
                "name": "Bank",
                "ranking_model": "bank",
                "rank_eligible": True,
                "total_score": 70.0,
                "quality_score": 70.0,
                "growth_score": 70.0,
                "valuation_score": 70.0,
                "balance_sheet_score": 70.0,
                "scoring_audit": {},
            },
        ],
    }
    original = deepcopy(run)

    snapshot = RankingChallenger().build(
        run, snapshot_month=date(2026, 8, 1), top_n=1
    )

    general = next(score for score in snapshot.scores if score["company_id"] == 1)
    bank = next(score for score in snapshot.scores if score["company_id"] == 2)
    assert general["quality_score"] == 80.0
    assert general["valuation_score"] == 70.0
    assert general["total_score"] == 66.0
    assert general["production_total_score"] == 50.0
    assert bank["total_score"] == 70.0
    assert bank["challenger_affected"] is False
    assert snapshot.production_top_company_ids == [1]
    assert snapshot.challenger_top_company_ids == [2]
    assert snapshot.status == "evaluation_only"
    assert run == original


def test_challenger_permits_tied_ranks_with_deterministic_membership_cutoff():
    first = _general_score(company_id=2)
    second = _general_score(company_id=1)
    snapshot = RankingChallenger().build(
        {
            "id": 8,
            "run_at": "2026-08-18T09:00:00+02:00",
            "scores": [first, second],
        },
        snapshot_month=date(2026, 8, 1),
        top_n=1,
    )

    assert [score["company_id"] for score in snapshot.scores] == [1, 2]
    assert [score["challenger_rank"] for score in snapshot.scores] == [1, 1]
    assert snapshot.challenger_top_company_ids == [1]


def test_challenger_rejects_general_score_without_complete_audit():
    score = _general_score()
    del score["scoring_audit"]["valuation"]
    with pytest.raises(ValueError, match="rerun rank-watchlist"):
        RankingChallenger().build(
            {
                "id": 9,
                "run_at": "2026-08-18T09:00:00+02:00",
                "scores": [score],
            },
            snapshot_month=date(2026, 8, 1),
        )


def test_challenger_repository_save_is_idempotent():
    repository = RankingChallengerRepository()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, [42]]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    snapshot = RankingChallenger().build(
        {
            "id": 7,
            "run_at": "2026-08-18T09:00:00+02:00",
            "scores": [_general_score()],
        },
        snapshot_month=date(2026, 8, 1),
    )

    with patch(
        "kncompanyscraper.repositories.ranking_challenger_repository.get_connection",
        return_value=conn,
    ):
        snapshot_id, created = repository.save(snapshot)

    assert snapshot_id == 42
    assert created is False
    assert cursor.execute.call_count == 2


def _performance_snapshot():
    return {
        "id": 12,
        "source_as_of": "2025-08-18",
        "production_top_company_ids": [1, 2],
        "challenger_top_company_ids": [2, 3],
        "scores": [
            {
                "company_id": company_id,
                "rank_eligible": True,
                "production_total_score": 11 - company_id,
                "challenger_total_score": company_id,
            }
            for company_id in range(1, 11)
        ],
    }


def test_challenger_performance_calculates_rank_decile_and_membership_metrics():
    benchmark_repository = MagicMock()
    benchmark_repository.get_return_basis.return_value = "gross_total_return"
    evaluator = RankingChallengerPerformanceEvaluator(
        MagicMock(), benchmark_repository, MagicMock()
    )
    evaluator.base_evaluator._company_total_return = MagicMock(
        side_effect=lambda company_id, *_: {
            "price_return": company_id / 100,
            "total_return": company_id / 100,
            "issue": None,
        }
    )
    evaluator.base_evaluator._benchmark_return = MagicMock(return_value=0.0)

    result = evaluator.evaluate(
        _performance_snapshot(),
        12,
        as_of=date(2026, 8, 18),
    )

    assert result.status == "complete"
    assert result.challenger_value_added == pytest.approx(0.01)
    assert result.production_rank_correlation.value == pytest.approx(-1.0)
    assert result.challenger_rank_correlation.value == pytest.approx(1.0)
    assert result.production_decile_spread.value == pytest.approx(-0.09)
    assert result.challenger_decile_spread.value == pytest.approx(0.09)
    assert result.membership_attribution.entrant_company_ids == (3,)
    assert result.membership_attribution.exit_company_ids == (1,)
    assert result.membership_attribution.value == pytest.approx(0.02)
    assert result.ranking_model_performance["general"].company_count == 10
    assert result.ranking_model_performance[
        "general"
    ].challenger_rank_correlation.value == pytest.approx(1.0)
    assert evaluator.base_evaluator._company_total_return.call_count == 10


def test_challenger_performance_requires_complete_full_universe_coverage():
    benchmark_repository = MagicMock()
    benchmark_repository.get_return_basis.return_value = "gross_total_return"
    evaluator = RankingChallengerPerformanceEvaluator(
        MagicMock(), benchmark_repository, MagicMock()
    )
    evaluator.base_evaluator._company_total_return = MagicMock(
        side_effect=lambda company_id, *_: {
            "price_return": None if company_id == 5 else company_id / 100,
            "total_return": None if company_id == 5 else company_id / 100,
            "issue": "missing_price" if company_id == 5 else None,
        }
    )
    evaluator.base_evaluator._benchmark_return = MagicMock(return_value=0.0)

    result = evaluator.evaluate(
        _performance_snapshot(),
        12,
        as_of=date(2026, 8, 18),
    )

    assert result.status == "pending"
    assert result.production_rank_correlation.missing_company_ids == (5,)
    assert result.challenger_rank_correlation.observed_count == 9
    assert result.production_decile_spread.value == pytest.approx(-0.09)


def test_challenger_performance_stays_pending_before_target_date():
    benchmark_repository = MagicMock()
    benchmark_repository.get_return_basis.return_value = "gross_total_return"
    evaluator = RankingChallengerPerformanceEvaluator(
        MagicMock(), benchmark_repository, MagicMock()
    )
    evaluator.base_evaluator._company_total_return = MagicMock()

    result = evaluator.evaluate(
        {**_performance_snapshot(), "source_as_of": "2026-08-18"},
        1,
        as_of=date(2026, 8, 18),
    )

    assert result.status == "pending"
    assert "target date has not been reached" in result.warnings
    evaluator.base_evaluator._company_total_return.assert_not_called()
