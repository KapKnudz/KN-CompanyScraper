from datetime import date

import pytest

from kncompanyscraper.analysis.valuation.required_return_policy import (
    RequiredReturnPolicy,
)


@pytest.mark.parametrize(
    ("market_cap", "bucket", "required_return"),
    [
        (499_999_999.0, "below_sek_1bn", 0.15),
        (1_000_000_000.0, "sek_1bn_to_below_5bn", 0.135),
        (4_999_999_999.0, "sek_1bn_to_below_5bn", 0.135),
        (5_000_000_000.0, "sek_5bn_to_below_30bn", 0.115),
        (29_999_999_999.0, "sek_5bn_to_below_30bn", 0.115),
        (30_000_000_000.0, "sek_30bn_and_above", 0.10),
    ],
)
def test_market_cap_bucket_selects_one_deterministic_hurdle(
    market_cap, bucket, required_return
):
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11), currency="SEK", market_cap=market_cap
    )

    assert decision.available
    assert decision.size_bucket == bucket
    assert decision.required_return == pytest.approx(required_return)
    assert decision.source_date == "2026-08-11"


@pytest.mark.parametrize("market_cap", [None, 0.0, -1.0, float("nan")])
def test_missing_or_invalid_market_cap_blocks_hurdle(market_cap):
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11), currency="SEK", market_cap=market_cap
    )

    assert not decision.available
    assert decision.required_return is None
    assert "market capitalization" in decision.missing_information[0]


def test_unsupported_currency_blocks_hurdle():
    decision = RequiredReturnPolicy().build(
        as_of=date(2026, 8, 11), currency="USD", market_cap=10_000_000_000.0
    )

    assert not decision.available
    assert decision.required_return is None
    assert "defined for SEK" in decision.missing_information[0]
