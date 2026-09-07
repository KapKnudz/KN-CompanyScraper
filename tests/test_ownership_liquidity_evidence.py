from datetime import date, timedelta

from kncompanyscraper.analysis.agent.ownership_liquidity_evidence import (
    OwnershipLiquidityEvidenceBuilder,
)
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.models.ownership_flow import (
    StoredBuybackEvent,
    StoredShortInterestSnapshot,
)


class CompanyRepository:
    def get_listing_identity(self, company_id):
        return {
            "market_id": 4,
            "venue": "Nasdaq Stockholm",
            "listing_date": date(2020, 2, 3),
        }


class PartialListingCompanyRepository(CompanyRepository):
    def get_listing_identity(self, company_id):
        return {
            "market_id": None,
            "venue": None,
            "listing_date": date(2020, 2, 3),
        }


class ValuationRepository:
    def __init__(self, prices):
        self.prices = prices

    def get_liquidity_prices_as_of(self, company_id, as_of, limit=120):
        return [price for price in self.prices if price.date <= as_of][:limit]


class FlowRepository:
    def __init__(self, events=(), snapshot=None, coverage=None):
        self.events = events
        self.snapshot = snapshot
        self.coverage = coverage or {}

    def list_buybacks_as_of(self, company_id, as_of):
        return tuple(event for event in self.events if event.event_date <= as_of)

    def get_latest_short_as_of(self, company_id, as_of):
        if self.snapshot and self.snapshot.observation_date <= as_of:
            return self.snapshot
        return None

    def get_latest_sync_coverage(self, company_id):
        return self.coverage


def _prices(count=120):
    as_of = date(2026, 8, 31)
    return [
        StockPrice(as_of - timedelta(days=index), 10.0, "SEK", index + 1)
        for index in range(count)
    ]


def test_builds_deterministic_adtv_windows_and_listing_packet():
    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(), ValuationRepository(_prices())
    ).build(42, date(2026, 8, 31))

    assert evidence.status == "partial"
    assert evidence.listing == {
        "status": "available",
        "market_id": 4,
        "venue": "Nasdaq Stockholm",
        "listing_date": "2020-02-03",
    }
    assert evidence.liquidity.adtv_20 == 105.0
    assert evidence.liquidity.status == "available"
    assert evidence.ownership == {"status": "unavailable", "source_ids": []}
    assert evidence.liquidity.adtv_60 == 305.0
    assert evidence.liquidity.adtv_120 == 605.0
    assert evidence.liquidity.observed_days_120 == 120
    assert evidence.liquidity.calculation_method == "close_times_volume_proxy"
    assert evidence.source_ids == [
        "liquidity:borsdata:42:2026-08-31:20d",
        "liquidity:borsdata:42:2026-08-31:60d",
        "liquidity:borsdata:42:2026-08-31:120d",
        "listing:borsdata:42",
    ]
    assert evidence.source_ids_by_measure["adtv_20"] == [
        "liquidity:borsdata:42:2026-08-31:20d"
    ]
    assert evidence.source_ids_by_measure["listing_date"] == [
        "listing:borsdata:42"
    ]


def test_rejects_incomplete_windows_and_excludes_future_prices():
    prices = [
        StockPrice(date(2026, 9, 1), 1_000.0, "SEK", 1_000_000),
        *_prices(20),
    ]
    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(), ValuationRepository(prices)
    ).build(42, date(2026, 8, 31))

    assert evidence.liquidity.adtv_20 == 105.0
    assert evidence.liquidity.adtv_60 is None
    assert evidence.liquidity.adtv_120 is None
    assert evidence.liquidity.status == "partial"
    assert evidence.liquidity.observed_days_60 == 20
    assert any("60-day proxy requires 60 observations" in item for item in evidence.limitations)


def test_binds_listing_date_without_market_id():
    evidence = OwnershipLiquidityEvidenceBuilder(
        PartialListingCompanyRepository(), ValuationRepository(_prices())
    ).build(42, date(2026, 8, 31))

    assert evidence.listing == {
        "status": "available",
        "market_id": None,
        "venue": None,
        "listing_date": "2020-02-03",
    }
    assert evidence.source_ids_by_measure["listing_date"] == [
        "listing:borsdata:42"
    ]
    assert "market_id" not in evidence.source_ids_by_measure


def test_filtered_zero_volume_measure_is_unavailable_without_binding():
    filter_ids = {
        "liquidity:borsdata:42:2026-08-31:20d",
        "liquidity:borsdata:42:2026-08-31:60d",
        "listing:borsdata:42",
    }
    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(), ValuationRepository(_prices())
    ).build(42, date(2026, 8, 31), filter_ids=filter_ids)

    assert evidence.liquidity.zero_volume_days_120 is None
    assert "zero_volume_days_120" not in evidence.source_ids_by_measure


def _buyback(event_date, change_shares, treasury_shares):
    return StoredBuybackEvent(
        42, event_date, change_shares, -0.25, 42.5, "SEK",
        treasury_shares, 1.25, "borsdata", {},
    )


def _short(observation_date):
    return StoredShortInterestSnapshot(
        42, observation_date, -1.5, 2.0, -1.0, 12.0, 10.0,
        observation_date, 3.0, 1.5, -0.1, 0.2, 0.3, 0.4,
        "borsdata", {},
    )


def test_builds_as_of_safe_buyback_totals_and_raw_short_snapshot():
    flow = FlowRepository(
        events=(
            _buyback(date(2026, 8, 20), -100, 500),
            _buyback(date(2026, 6, 1), -200, 400),
            _buyback(date(2025, 10, 1), -300, 200),
            _buyback(date(2025, 1, 1), -999, 100),
            _buyback(date(2026, 9, 1), -9999, 0),
        ),
        snapshot=_short(date(2026, 8, 30)),
    )

    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(), ValuationRepository(_prices()), flow
    ).build(42, date(2026, 8, 31))

    assert evidence.flow_signals["buybacks"] == {
        "status": "available",
        "latest_event_date": "2026-08-20",
        "trailing_3_month_change_shares_raw": -300,
        "trailing_12_month_change_shares_raw": -600,
        "latest_treasury_shares": 500,
        "latest_treasury_shares_pct_raw": 1.25,
        "source_ids": [
            "buyback:borsdata:42:2026-08-20",
            "buyback:borsdata:42:2026-06-01",
            "buyback:borsdata:42:2025-10-01",
        ],
    }
    shorts = evidence.flow_signals["shorts"]
    assert shorts["status"] == "available"
    assert shorts["snapshot_age_days"] == 1
    assert shorts["short_pct_raw"] == -1.5
    assert shorts["trend_1w_raw"] == -0.1
    assert shorts["source_ids"] == ["short:borsdata:42:2026-08-30"]
    assert "buyback:borsdata:42:2026-09-01" not in evidence.source_ids


def test_excludes_future_short_snapshot_and_surfaces_failed_coverage():
    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(),
        ValuationRepository(_prices()),
        FlowRepository(
            snapshot=_short(date(2026, 9, 1)),
            coverage={"buybacks": "failed", "shorts": "failed"},
        ),
    ).build(42, date(2026, 8, 31))

    assert evidence.flow_signals["buybacks"]["status"] == "failed"
    assert evidence.flow_signals["shorts"]["status"] == "failed"
    assert any("Short-interest evidence is failed" in item for item in evidence.limitations)


def test_labels_stale_short_snapshot_and_keeps_trends_on_that_observation():
    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(),
        ValuationRepository(_prices()),
        FlowRepository(snapshot=_short(date(2026, 8, 20))),
        short_stale_after_days=7,
    ).build(42, date(2026, 8, 31))

    shorts = evidence.flow_signals["shorts"]
    assert shorts["status"] == "stale"
    assert shorts["observation_date"] == "2026-08-20"
    assert shorts["trend_6m_raw"] == 0.4
    assert any("snapshot is stale at 11 days old" in item for item in evidence.limitations)


def test_original_filter_recalculates_buybacks_from_exact_source_ids():
    evidence = OwnershipLiquidityEvidenceBuilder(
        CompanyRepository(),
        ValuationRepository(_prices()),
        FlowRepository(
            events=(
                _buyback(date(2026, 8, 20), -100, 500),
                _buyback(date(2026, 6, 1), -200, 400),
            ),
            snapshot=_short(date(2026, 8, 30)),
        ),
    ).build(
        42,
        date(2026, 8, 31),
        filter_ids={"buyback:borsdata:42:2026-06-01"},
    )

    assert evidence.flow_signals["buybacks"]["trailing_3_month_change_shares_raw"] == -200
    assert evidence.flow_signals["buybacks"]["source_ids"] == [
        "buyback:borsdata:42:2026-06-01"
    ]
    assert evidence.flow_signals["shorts"]["source_ids"] == []
    assert evidence.source_ids_by_measure["trailing_3_month_change_shares_raw"] == [
        "buyback:borsdata:42:2026-06-01"
    ]
