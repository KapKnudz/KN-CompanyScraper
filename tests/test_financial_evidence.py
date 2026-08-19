from datetime import date
from types import SimpleNamespace

from kncompanyscraper.analysis.agent.financial_evidence import (
    StructuredFinancialEvidenceBuilder,
)


def report(year, period, period_end):
    return SimpleNamespace(
        year=year,
        period=period,
        period_end=period_end,
        currency="SEK",
        revenue=100.0,
        gross_income=60.0,
        operating_profit=12.0,
        ebit=12.0,
        ebitda=15.0,
        net_income=8.0,
        operating_cash_flow=11.0,
        investing_cash_flow=-2.0,
        free_cash_flow=9.0,
        total_assets=150.0,
        equity=80.0,
        total_debt=20.0,
        shares_outstanding=10.0,
    )


def test_financial_evidence_is_bounded_newest_first_and_source_identified():
    annual = [report(year, 4, date(year, 12, 31)) for year in range(2014, 2026)]
    quarterly = [report(2025, period, date(2025, period * 3, 28)) for period in range(1, 5)]
    latest_r12 = report(2025, 4, date(2025, 12, 31))

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            values = {
                "year": annual,
                "quarter": quarterly,
                "r12": [latest_r12],
            }[period_type]
            return list(reversed(values))

    evidence = StructuredFinancialEvidenceBuilder(Repository()).build(
        42, as_of=date(2026, 8, 18)
    )

    assert len(evidence.annual_reports) == 10
    assert [item.year for item in evidence.annual_reports[:2]] == [2025, 2024]
    assert [item.period for item in evidence.quarterly_reports] == [4, 3, 2, 1]
    assert evidence.annual_reports[0].source_id == "financial:annual:2025-12-31"
    assert evidence.latest_r12.source_id == "financial:r12:2025-12-31"
    assert evidence.as_of == "2026-08-18"
