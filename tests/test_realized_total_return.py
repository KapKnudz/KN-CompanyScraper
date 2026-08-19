from datetime import date
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.realized_total_return import (
    RealizedTotalReturnCalculator,
)
from kncompanyscraper.borsdata.dividend import CashDividend
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.repositories.dividend_repository import (
    DividendCoverage,
    DividendEventReview,
    DividendRepository,
)


def price(value_date, close, currency="SEK"):
    return StockPrice(value_date, close, currency)


def calculator(dividends=None):
    valuations = MagicMock()
    valuations.get_stock_price_on_date.return_value = price(
        date(2026, 12, 31), 110.0
    )
    valuations.get_stock_price_on_or_after.return_value = price(
        date(2026, 6, 1), 95.0
    )
    repository = MagicMock()
    repository.get_coverage.return_value = DividendCoverage(
        date(2020, 1, 1), date(2026, 12, 31), "borsdata:dividend_calendar"
    )
    repository.get_dividends.return_value = dividends or []
    repository.get_reviews.return_value = {}
    repository.review_key.side_effect = DividendRepository.review_key
    return RealizedTotalReturnCalculator(valuations, repository), valuations, repository


def test_reinvests_aggregated_same_day_cash_dividends():
    engine, _, _ = calculator(
        [
            CashDividend(date(2026, 6, 1), 4.0, "SEK", 0),
            CashDividend(date(2026, 6, 1), 1.0, "SEK", 1),
        ]
    )

    result = engine.calculate(
        1,
        price(date(2026, 1, 2), 100.0),
        date(2026, 12, 31),
    )

    assert result.price_return == pytest.approx(0.10)
    assert result.total_return == pytest.approx((1 + 5 / 95) * 1.10 - 1)
    assert result.issue is None


def test_incomplete_dividend_coverage_keeps_price_return_only():
    engine, _, dividends = calculator()
    dividends.get_coverage.return_value = DividendCoverage(
        date(2020, 1, 1), date(2026, 6, 30), "borsdata:dividend_calendar"
    )

    result = engine.calculate(
        1,
        price(date(2026, 1, 2), 100.0),
        date(2026, 12, 31),
    )

    assert result.total_return is None
    assert result.price_return == pytest.approx(0.10)
    assert result.issue == "incomplete_dividends"


def test_currency_mismatch_is_visible():
    engine, valuations, _ = calculator()
    valuations.get_stock_price_on_date.return_value = price(
        date(2026, 12, 31), 110.0, "EUR"
    )

    result = engine.calculate(
        1,
        price(date(2026, 1, 2), 100.0, "SEK"),
        date(2026, 12, 31),
    )

    assert result.total_return is None
    assert result.issue == "currency_mismatch"


def test_excluded_dividend_is_not_applied():
    event = CashDividend(date(2026, 6, 1), 120.0, "SEK", 3)
    engine, _, dividends = calculator([event])
    key = DividendRepository.review_key(
        event.ex_date, event.amount, event.currency, event.dividend_type
    )
    dividends.get_reviews.return_value = {
        key: DividendEventReview("excluded", "wrong share class", "https://example.com")
    }

    result = engine.calculate(
        1, price(date(2026, 1, 2), 100.0), date(2026, 12, 31)
    )

    assert result.total_return == pytest.approx(0.10)
    assert result.issue is None


def test_pending_or_extreme_unreviewed_dividend_requires_review():
    event = CashDividend(date(2026, 6, 1), 100.0, "SEK", 3)
    engine, _, dividends = calculator([event])

    result = engine.calculate(
        1, price(date(2026, 1, 2), 100.0), date(2026, 12, 31)
    )

    assert result.total_return is None
    assert result.price_return == pytest.approx(0.10)
    assert result.issue == "dividend_review_required"

    key = DividendRepository.review_key(
        event.ex_date, event.amount, event.currency, event.dividend_type
    )
    dividends.get_reviews.return_value = {
        key: DividendEventReview("pending", "needs evidence", None)
    }
    assert engine.calculate(
        1, price(date(2026, 1, 2), 100.0), date(2026, 12, 31)
    ).issue == "dividend_review_required"


def test_approved_extreme_dividend_retains_return_arithmetic():
    event = CashDividend(date(2026, 6, 1), 100.0, "SEK", 3)
    engine, _, dividends = calculator([event])
    key = DividendRepository.review_key(
        event.ex_date, event.amount, event.currency, event.dividend_type
    )
    dividends.get_reviews.return_value = {
        key: DividendEventReview("approved", "verified cash distribution", None)
    }

    result = engine.calculate(
        1, price(date(2026, 1, 2), 100.0), date(2026, 12, 31)
    )

    assert result.total_return == pytest.approx((1 + 100 / 95) * 1.10 - 1)
    assert result.issue is None
