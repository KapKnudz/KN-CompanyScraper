from datetime import date
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.ranking_performance import RankingPerformanceEvaluator
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.borsdata.dividend import CashDividend
from kncompanyscraper.repositories.dividend_repository import (
    DividendCoverage,
    DividendRepository,
)


def ranking_run():
    return {
        "id": 12,
        "inputs_summary": {
            "as_of": "2026-01-31",
            "final_actionable_company_ids": [1, 2],
            "comparative_final_actionable_company_ids": [1, 2],
            "deterministic_shortlist_company_ids": [2, 3],
            "agent_cohort_company_ids": [1, 2],
            "recall_universe_company_ids": [1, 2, 3],
        },
    }


def dividend_repository(*, covered_through=date(2026, 12, 31)):
    repository = MagicMock()
    repository.get_coverage.return_value = DividendCoverage(
        date(2020, 1, 1), covered_through, "borsdata:dividend_calendar"
    )
    repository.get_dividends.return_value = []
    repository.get_reviews.return_value = {}
    repository.review_key.side_effect = DividendRepository.review_key
    return repository


def test_evaluator_compares_frozen_equal_weight_memberships():
    starts = {1: 100.0, 2: 200.0, 3: 50.0}
    ends = {1: 120.0, 2: 220.0, 3: 45.0}
    valuations = MagicMock()
    valuations.get_stock_price_on_or_after.side_effect = lambda company_id, *_args, **_kwargs: StockPrice(
        date(2026, 2, 2), starts[company_id], "SEK"
    )
    valuations.get_stock_price_on_date.side_effect = lambda company_id, *_args, **_kwargs: StockPrice(
        date(2026, 2, 27), ends[company_id], "SEK"
    )
    benchmarks = MagicMock()
    benchmarks.get_return_basis.return_value = "gross_total_return"
    benchmarks.get_value_on_or_after.return_value = (date(2026, 2, 2), 500.0)
    benchmarks.get_value_on_or_before.return_value = (date(2026, 2, 27), 525.0)

    result = RankingPerformanceEvaluator(
        valuations, benchmarks, dividend_repository()
    ).evaluate(
        ranking_run(), 1, as_of=date(2026, 3, 1)
    )

    assert result.status == "complete"
    assert result.final_ranking.value == pytest.approx(0.15)
    assert result.deterministic_shortlist.value == pytest.approx(0.0)
    assert result.agent_value_added == pytest.approx(0.15)
    assert result.comparative_agent_value_added == pytest.approx(0.0)
    assert result.benchmark_return == pytest.approx(0.05)
    assert result.excess_vs_benchmark == pytest.approx(0.10)
    assert result.cohort_recall_at_30.value == pytest.approx(2 / 3)
    assert result.cohort_recall_at_30.captured_winner_count == 2
    assert result.final_ranking.price_value == pytest.approx(0.15)
    assert result.comparison_basis == "gross_total_return_vs_gross_total_return"


def test_evaluator_requires_complete_constituent_coverage():
    valuations = MagicMock()
    valuations.get_stock_price_on_or_after.return_value = StockPrice(
        date(2026, 2, 2), 100.0, "SEK"
    )
    valuations.get_stock_price_on_date.side_effect = (
        lambda company_id, *_args, **_kwargs: None
        if company_id == 2
        else StockPrice(date(2026, 2, 27), 110.0, "SEK")
    )
    benchmarks = MagicMock()
    benchmarks.get_return_basis.return_value = "gross_total_return"
    benchmarks.get_value_on_or_after.return_value = (date(2026, 2, 2), 500.0)
    benchmarks.get_value_on_or_before.return_value = (date(2026, 2, 27), 525.0)

    result = RankingPerformanceEvaluator(
        valuations, benchmarks, dividend_repository()
    ).evaluate(
        ranking_run(), 1, as_of=date(2026, 3, 1)
    )

    assert result.status == "pending"
    assert result.final_ranking.value is None
    assert result.final_ranking.missing_company_ids == (2,)
    assert result.cohort_recall_at_30.value is None
    assert result.cohort_recall_at_30.missing_company_ids == (2,)


def test_evaluator_does_not_emit_returns_before_target_date():
    valuations = MagicMock()
    benchmarks = MagicMock()
    benchmarks.get_return_basis.return_value = "gross_total_return"

    result = RankingPerformanceEvaluator(
        valuations, benchmarks, dividend_repository()
    ).evaluate(
        ranking_run(), 2, as_of=date(2026, 2, 15)
    )

    assert result.status == "pending"
    assert result.final_ranking.value is None
    valuations.get_stock_price_on_or_after.assert_not_called()
    benchmarks.get_value_on_or_after.assert_not_called()


def test_evaluator_reinvests_same_day_dividends_once_at_ex_date_close():
    valuations = MagicMock()

    def on_or_after(company_id, target_date, **_kwargs):
        if target_date == date(2026, 1, 31):
            return StockPrice(date(2026, 2, 2), 100.0, "SEK")
        return StockPrice(target_date, 95.0, "SEK")

    valuations.get_stock_price_on_or_after.side_effect = on_or_after
    valuations.get_stock_price_on_date.return_value = StockPrice(
        date(2026, 2, 27), 110.0, "SEK"
    )
    dividends = dividend_repository()
    dividends.get_dividends.return_value = [
        CashDividend(date(2026, 2, 16), 4.0, "SEK", 0),
        CashDividend(date(2026, 2, 16), 1.0, "SEK", 1),
    ]
    benchmarks = MagicMock()
    benchmarks.get_return_basis.return_value = "gross_total_return"
    benchmarks.get_value_on_or_after.return_value = (date(2026, 2, 2), 500.0)
    benchmarks.get_value_on_or_before.return_value = (date(2026, 2, 27), 525.0)

    result = RankingPerformanceEvaluator(valuations, benchmarks, dividends).evaluate(
        ranking_run(), 1, as_of=date(2026, 3, 1)
    )

    expected = (1 + 5 / 95) * 110 / 100 - 1
    assert result.status == "complete"
    assert result.final_ranking.value == pytest.approx(expected)
    assert result.final_ranking.price_value == pytest.approx(0.10)


def test_evaluator_exposes_incomplete_dividend_coverage_without_zero_fill():
    valuations = MagicMock()
    valuations.get_stock_price_on_or_after.return_value = StockPrice(
        date(2026, 2, 2), 100.0, "SEK"
    )
    valuations.get_stock_price_on_date.return_value = StockPrice(
        date(2026, 2, 27), 110.0, "SEK"
    )
    benchmarks = MagicMock()
    benchmarks.get_return_basis.return_value = "gross_total_return"
    benchmarks.get_value_on_or_after.return_value = (date(2026, 2, 2), 500.0)
    benchmarks.get_value_on_or_before.return_value = (date(2026, 2, 27), 525.0)

    result = RankingPerformanceEvaluator(
        valuations,
        benchmarks,
        dividend_repository(covered_through=date(2026, 2, 20)),
    ).evaluate(ranking_run(), 1, as_of=date(2026, 3, 1))

    assert result.status == "pending"
    assert result.final_ranking.value is None
    assert result.final_ranking.price_value == pytest.approx(0.10)
    assert result.final_ranking.incomplete_dividend_company_ids == (1, 2)


def test_evaluator_exposes_dividend_review_as_coverage_blocker():
    valuations = MagicMock()
    valuations.get_stock_price_on_or_after.return_value = StockPrice(
        date(2026, 2, 2), 100.0, "SEK"
    )
    valuations.get_stock_price_on_date.return_value = StockPrice(
        date(2026, 2, 27), 110.0, "SEK"
    )
    dividends = dividend_repository()
    dividends.get_dividends.return_value = [
        CashDividend(date(2026, 2, 16), 100.0, "SEK", 3)
    ]
    benchmarks = MagicMock()
    benchmarks.get_return_basis.return_value = "gross_total_return"
    benchmarks.get_value_on_or_after.return_value = (date(2026, 2, 2), 500.0)
    benchmarks.get_value_on_or_before.return_value = (date(2026, 2, 27), 525.0)

    result = RankingPerformanceEvaluator(
        valuations, benchmarks, dividends
    ).evaluate(ranking_run(), 1, as_of=date(2026, 3, 1))

    assert result.status == "pending"
    assert result.final_ranking.value is None
    assert result.final_ranking.dividend_review_company_ids == (1, 2)
