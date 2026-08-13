from datetime import date

import pytest

from kncompanyscraper.analysis.valuation.required_return_policy import RequiredReturnPolicy


def test_builds_dated_large_cap_discount_rate_profiles():
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11),
        currency="SEK",
        market_cap=150_000_000_000.0,
    )

    assert decision.available
    assert decision.risk_free_rate == pytest.approx(0.028)
    assert decision.risk_free_rate_date == "2026-07-24"
    assert decision.equity_risk_premium == pytest.approx(0.05)
    assert decision.size_bucket == "large"
    assert decision.size_adjustment == 0.0
    assert decision.profiles["noncyclical_recurring"].discount_rate == pytest.approx(0.098)
    assert decision.profiles["slightly_cyclical"].discount_rate == pytest.approx(0.118)
    assert decision.profiles["cyclical_or_other_risk"].discount_rate == pytest.approx(0.148)


def test_adds_transparent_micro_cap_adjustment_to_every_profile():
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11),
        currency="SEK",
        market_cap=900_000_000.0,
    )

    assert decision.size_bucket == "micro"
    assert decision.size_adjustment == pytest.approx(0.02)
    assert decision.profiles["noncyclical_recurring"].discount_rate == pytest.approx(0.118)
    assert decision.profiles["slightly_cyclical"].discount_rate == pytest.approx(0.138)
    assert decision.profiles["cyclical_or_other_risk"].discount_rate == pytest.approx(0.168)


def test_historical_analysis_uses_only_rate_snapshots_available_as_of_date():
    decision = RequiredReturnPolicy().build(
        as_of=date(2025, 12, 31),
        currency="SEK",
        market_cap=150_000_000_000.0,
    )

    assert decision.risk_free_rate == pytest.approx(0.03)
    assert decision.risk_free_rate_date == "1900-01-01"
    assert decision.profiles["slightly_cyclical"].discount_rate == pytest.approx(0.12)
    assert "backtest proxy" in decision.warnings[0]


def test_rejects_currency_without_matching_risk_free_rate():
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11),
        currency="EUR",
        market_cap=1_000_000_000.0,
    )

    assert not decision.available
    assert "EUR" in decision.missing_information[0]


def test_missing_market_cap_uses_zero_size_adjustment_with_warning():
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11),
        currency="SEK",
        market_cap=None,
    )

    assert decision.available
    assert decision.size_bucket == "unknown"
    assert decision.size_adjustment == 0.0
    assert decision.warnings
