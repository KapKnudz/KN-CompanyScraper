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
        cash=10.0,
        shares_outstanding=10.0,
        dividend_per_share=2.0,
        financing_cash_flow=-1.0,
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


def test_financial_evidence_adds_source_linked_h1_reconciliation_limitation():
    annual = [report(2025, 4, date(2025, 12, 31))]
    quarterly = [
        report(2025, 1, date(2025, 3, 28)),
        report(2025, 2, date(2025, 6, 28)),
    ]
    quarterly[0].revenue = 120.0
    quarterly[1].revenue = 140.0

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            return {
                "year": annual,
                "quarter": list(reversed(quarterly)),
                "r12": [],
            }[period_type]

    evidence = StructuredFinancialEvidenceBuilder(Repository()).build(42, date(2026, 8, 18))
    evidence = evidence.with_document_reconciliations(
        [
            {
                "source_id": "document:11",
                "structured_financial_values": [
                    {"metric": "revenue", "period": "2025-H1", "value": 250.0}
                ],
            }
        ]
    )

    limitations = evidence.half_year_comparison.limitations
    reconciliation = next(item for item in limitations if item.startswith("Report "))
    assert "document:11" in reconciliation
    assert "financial:quarterly:2025-03-28" in reconciliation
    assert "financial:quarterly:2025-06-28" in reconciliation
    assert "revenue=250" in reconciliation
    assert "revenue=260" in reconciliation


def test_financial_evidence_ignores_rounding_and_non_h1_document_values():
    annual = [report(2025, 4, date(2025, 12, 31))]
    quarterly = [
        report(2025, 1, date(2025, 3, 28)),
        report(2025, 2, date(2025, 6, 28)),
    ]

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            return {
                "year": annual,
                "quarter": list(reversed(quarterly)),
                "r12": [],
            }[period_type]

    evidence = StructuredFinancialEvidenceBuilder(Repository()).build(42, date(2026, 8, 18))
    evidence = evidence.with_document_reconciliations(
        [
            {
                "source_id": "document:11",
                "structured_financial_values": [
                    {"metric": "revenue", "period": "2025-H1", "value": 200.5},
                    {"metric": "revenue", "period": "2024-H1", "value": 199.0},
                ],
            }
        ]
    )

    assert evidence.half_year_comparison.limitations == (
        "No comparable prior-year H1 is available.",
    )


def test_scenario_history_uses_full_history_but_prompt_detail_stays_bounded():
    annual = [report(year, 4, date(year, 12, 31)) for year in range(2015, 2026)]
    quarterly = [
        report(2023 + (period - 1) // 4, ((period - 1) % 4) + 1, date(2023 + (period - 1) // 4, ((period - 1) % 4 + 1) * 3, 28))
        for period in range(1, 17)
    ]
    r12 = [report(year, 4, date(year, 12, 31)) for year in range(2022, 2026)]
    for item in r12:
        item.revenue = float(item.year * 10)
        item.ebit = item.operating_profit = item.revenue * (0.05 + (item.year - 2022) * 0.01)

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            return {
                "year": list(reversed(annual)),
                "quarter": list(reversed(quarterly)),
                "r12": list(reversed(r12)),
            }[period_type]

    evidence = StructuredFinancialEvidenceBuilder(Repository()).build(
        42, as_of=date(2026, 8, 18)
    )
    history = evidence.scenario_history

    assert len(evidence.annual_reports) == 10
    assert len(evidence.quarterly_reports) == 12
    assert history.annual_observation_count == 11
    assert history.quarterly_observation_count == 16
    assert history.r12_observation_count == 4
    assert history.revenue_cagr_10_year is not None
    assert history.r12_ebit_margin_peak == pytest.approx(0.08)
    assert history.source_ids["r12_ebit_margin"] == tuple(
        f"financial:r12:{year}-12-31" for year in range(2025, 2021, -1)
    )


def test_scenario_history_excludes_broken_periods_and_keeps_missing_values_null():
    annual = [
        report(2020, 4, date(2020, 12, 31)),
        report(2022, 4, date(2022, 12, 31)),
        report(2025, 4, date(2025, 12, 31)),
    ]
    annual[1].broken_fiscal_year = True
    annual[1].cash = None
    for item in annual:
        item.financing_cash_flow = None
    annual[2].financing_cash_flow = None
    quarterly = []
    r12 = []

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            return {"year": list(reversed(annual)), "quarter": quarterly, "r12": r12}[period_type]

    history = StructuredFinancialEvidenceBuilder(Repository()).build(
        42, as_of=date(2026, 8, 18)
    ).scenario_history

    assert history.revenue_cagr_3_year is None
    assert history.net_debt_change_3_year is None
    assert history.financing_cash_flow_observations == ()
    assert any("broken fiscal year" in item for item in history.exclusions)
    assert history.source_ids["revenue_cagr_3_year"] == ()
    assert history.dividend_consistency is True


def test_older_r12_observations_change_deterministic_margin_range():
    r12 = [report(year, 4, date(year, 12, 31)) for year in range(2010, 2026)]
    for item in r12:
        item.revenue = 100.0
        item.ebit = item.operating_profit = 10.0
    r12[0].ebit = r12[0].operating_profit = -20.0

    class Repository:
        def get_reports_as_of(self, company_id, period_type, as_of):
            return {"year": [], "quarter": [], "r12": list(reversed(r12))}[period_type]

    history = StructuredFinancialEvidenceBuilder(Repository()).build(
        42, as_of=date(2026, 8, 18)
    ).scenario_history

    assert history.r12_ebit_margin_trough == pytest.approx(-0.20)
    assert "financial:r12:2010-12-31" in history.source_ids["r12_ebit_margin"]
