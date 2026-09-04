from datetime import date, datetime, timezone

from kncompanyscraper.analysis.ownership_liquidity_coverage import (
    OwnershipLiquidityCoverageReport,
)


class StubRepository:
    def get_operational_coverage(self, company_ids):
        assert company_ids == [1, 2, 3]
        return [
            {
                "company_id": 1,
                "name": "Available AB",
                "ticker": "AVA",
                "price_oldest": date(2026, 1, 2),
                "price_newest": date(2026, 8, 29),
                "price_collected_at": datetime(2026, 8, 29, tzinfo=timezone.utc),
                "liquidity_job_status": "success",
                "liquidity_error": None,
                "buyback_oldest": date(2026, 3, 1),
                "buyback_newest": date(2026, 8, 20),
                "buyback_collected_at": datetime(2026, 8, 30, tzinfo=timezone.utc),
                "short_oldest": date(2026, 8, 30),
                "short_newest": date(2026, 8, 30),
                "short_collected_at": datetime(2026, 8, 30, tzinfo=timezone.utc),
                "holdings_completed_at": datetime(2026, 8, 30, tzinfo=timezone.utc),
                "holdings_job_status": "success",
                "holdings_coverage": {"buybacks": "available", "shorts": "available"},
                "holdings_error": None,
            },
            {
                "company_id": 2,
                "name": "Empty AB",
                "ticker": "EMP",
                "price_oldest": date(2026, 4, 1),
                "price_newest": date(2026, 8, 1),
                "price_collected_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
                "liquidity_job_status": "success",
                "liquidity_error": None,
                "buyback_oldest": None,
                "buyback_newest": None,
                "buyback_collected_at": None,
                "short_oldest": None,
                "short_newest": None,
                "short_collected_at": None,
                "holdings_completed_at": datetime(2026, 8, 30, tzinfo=timezone.utc),
                "holdings_job_status": "success",
                "holdings_coverage": {"buybacks": "empty", "shorts": "unknown"},
                "holdings_error": None,
            },
            {
                "company_id": 3,
                "name": "Failed AB",
                "ticker": "FAIL",
                "price_oldest": None,
                "price_newest": None,
                "price_collected_at": None,
                "liquidity_job_status": "failed",
                "liquidity_error": "prices: timeout",
                "buyback_oldest": None,
                "buyback_newest": None,
                "buyback_collected_at": None,
                "short_oldest": None,
                "short_newest": None,
                "short_collected_at": None,
                "holdings_completed_at": datetime(2026, 8, 30, tzinfo=timezone.utc),
                "holdings_job_status": "failed",
                "holdings_coverage": {"buybacks": "omitted", "shorts": "failed"},
                "holdings_error": "buybacks: response omitted instrument; shorts: timeout",
            },
        ]


def test_report_preserves_domain_states_and_freshness():
    companies = [type("Company", (), {"id": value})() for value in (1, 2, 3)]

    report = OwnershipLiquidityCoverageReport(
        StubRepository(), stale_after_days=7
    ).build(companies, as_of=date(2026, 8, 31))

    assert report.counts["liquidity"] == {
        "requested": 3,
        "available": 1,
        "confirmed_empty": 0,
        "omitted": 0,
        "unknown": 0,
        "failed": 1,
        "stale": 1,
    }
    assert report.counts["buybacks"]["confirmed_empty"] == 1
    assert report.counts["buybacks"]["omitted"] == 1
    assert report.counts["shorts"]["available"] == 1
    assert report.counts["shorts"]["unknown"] == 1
    assert report.counts["shorts"]["failed"] == 1
    assert report.observation_ranges["buybacks"] == {
        "oldest": "2026-03-01",
        "newest": "2026-08-20",
    }
    assert report.companies[0]["shorts"]["snapshot_age_days"] == 1
    assert report.companies[1]["buybacks"]["status"] == "confirmed_empty"
    assert report.companies[2]["errors"] == [
        "liquidity: prices: timeout",
        "holdings: buybacks: response omitted instrument; shorts: timeout",
    ]


def test_report_does_not_treat_omitted_short_row_as_empty():
    class OmittedShortRepository(StubRepository):
        def get_operational_coverage(self, company_ids):
            row = super().get_operational_coverage(company_ids)[0]
            row["holdings_coverage"] = {"buybacks": "available", "shorts": "omitted"}
            row["short_oldest"] = row["short_newest"] = None
            row["short_collected_at"] = None
            return [row]

    companies = [type("Company", (), {"id": value})() for value in (1, 2, 3)]
    report = OwnershipLiquidityCoverageReport(OmittedShortRepository()).build(
        companies, as_of=date(2026, 8, 31)
    )

    assert report.companies[0]["shorts"]["status"] == "unknown"
