from datetime import date
from types import SimpleNamespace

import pytest

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


def test_financial_evidence_frames_latest_h1_against_prior_year_and_history():
    annual = [report(year, 4, date(year, 12, 31)) for year in (2023, 2024, 2025)]
    quarterly = [
        report(2024, 1, date(2024, 3, 28)),
        report(2024, 2, date(2024, 6, 28)),
        report(2025, 1, date(2025, 3, 28)),
        report(2025, 2, date(2025, 6, 28)),
    ]
    quarterly[0].revenue = 100.0
    quarterly[1].revenue = 100.0
    quarterly[0].ebit = quarterly[0].operating_profit = 10.0
    quarterly[1].ebit = quarterly[1].operating_profit = 10.0
    quarterly[2].revenue = 120.0
    quarterly[3].revenue = 140.0
    quarterly[2].ebit = quarterly[2].operating_profit = 12.0
    quarterly[3].ebit = quarterly[3].operating_profit = 28.0

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            values = {
                "year": annual,
                "quarter": quarterly,
                "r12": [],
            }[period_type]
            return list(reversed(values))

    framing = StructuredFinancialEvidenceBuilder(Repository()).build(
        42, as_of=date(2026, 8, 18)
    ).half_year_comparison

    assert framing.observed_period_count == 2
    assert framing.latest_year == 2025
    assert framing.prior_year == 2024
    assert framing.latest_revenue == 260.0
    assert framing.prior_revenue == 200.0
    assert framing.revenue_change == pytest.approx(0.30)
    assert framing.latest_ebit_margin == pytest.approx(40 / 260)
    assert framing.prior_ebit_margin == pytest.approx(0.10)
    assert framing.ebit_margin_change == pytest.approx(40 / 260 - 0.10)
    assert framing.periods_below_historical_average == 1
    assert framing.latest_source_ids == (
        "financial:quarterly:2025-03-28",
        "financial:quarterly:2025-06-28",
    )


def test_financial_evidence_discloses_missing_complete_h1_pair():
    annual = [report(2025, 4, date(2025, 12, 31))]
    quarterly = [report(2025, 1, date(2025, 3, 28))]

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            return {"year": annual, "quarter": quarterly, "r12": []}[period_type]

    framing = StructuredFinancialEvidenceBuilder(Repository()).build(
        42, as_of=date(2026, 8, 18)
    ).half_year_comparison

    assert framing.observed_period_count == 0
    assert framing.latest_year is None
    assert framing.limitations == (
        "No complete Q1 and Q2 pair is available for H1 framing.",
    )
