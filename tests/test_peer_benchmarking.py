from datetime import date
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.peer_benchmarking import PeerComparisonBuilder
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.models.company import Company


def report(year, revenue, ebit, net_debt=50.0):
    return Report(
        revenue=revenue,
        operating_profit=ebit,
        ebit=ebit,
        ebitda=None,
        net_income=50.0,
        free_cash_flow=30.0,
        equity=500.0,
        total_assets=800.0,
        total_debt=net_debt,
        shares_outstanding=100.0,
        year=year,
        period_end=date(year, 12, 31),
        currency="SEK",
    )


def company(company_id, ticker, *, branch_id=10, sector_id=1, currency="SEK"):
    return Company(
        id=company_id,
        name=ticker,
        ticker=ticker,
        mfn_slug=None,
        borsdata_id=company_id,
        last_updated=None,
        currency=currency,
        sector_id=sector_id,
        branch_id=branch_id,
    )


def test_peer_comparison_selects_comparable_companies_and_preserves_provenance():
    target = company(1, "TARGET")
    included = company(2, "PEER")
    other_branch = company(3, "OTHER", branch_id=11)
    other_currency = company(4, "EURO", currency="EUR")
    overflow = company(5, "PEER2")
    target_reports = {1: report(2025, 1_000.0, 100.0)}
    peer_reports = {
        2: report(2025, 1_100.0, 110.0),
        3: report(2025, 1_100.0, 110.0),
        4: report(2025, 1_100.0, 110.0),
        5: report(2025, 1_200.0, 120.0),
    }
    prior_reports = {
        1: report(2024, 900.0, 90.0),
        2: report(2024, 1_000.0, 100.0),
        3: report(2024, 1_000.0, 100.0),
        4: report(2024, 1_000.0, 100.0),
        5: report(2024, 1_100.0, 110.0),
    }

    class Companies:
        def get_by_id(self, company_id):
            return {
                1: target,
                2: included,
                3: other_branch,
                4: other_currency,
                5: overflow,
            }[company_id]

        def get_active_companies(self):
            return [target, included, other_branch, other_currency, overflow]

    class Financials:
        def get_latest_report_as_of(self, company_id, period_type, as_of):
            return target_reports.get(company_id) or peer_reports.get(company_id)

        def get_historical_reports(self, company_id, period_type):
            return [prior_reports[company_id]]

    class Valuations:
        def get_stock_price_on_date(self, company_id, target_date, max_age_days=None):
            return SimpleNamespace(
                date=date(2026, 8, 20),
                close=10.0 if company_id == 1 else 12.0,
            )

    comparison = PeerComparisonBuilder(
        Companies(), Financials(), Valuations(), max_peers=1
    ).build(1, as_of=date(2026, 8, 24), target_terminal_ev_ebit=(8.0, 12.0))

    assert comparison.status == "available"
    assert comparison.selection_basis == "same_branch_id_and_currency"
    assert [peer.ticker for peer in comparison.included_peers] == ["PEER"]
    assert comparison.peer_ranges["current_ev_ebit"].median == pytest.approx(
        (12 * 100 + 50) / 110
    )
    assert comparison.target_terminal_ev_ebit["low"].source_ids == (
        "full_results.valuation.ev_ebit_guardrail_low",
    )
    assert comparison.included_peers[0].metrics["revenue_growth"].source_ids == (
        "peer:financial:2:2025-12-31",
        "peer:financial:2:2024-12-31",
    )
    assert {(item.ticker, item.reason) for item in comparison.excluded_peers} == {
        ("OTHER", "different branch_id"),
        ("EURO", "reporting currencies differ"),
        ("PEER2", "peer set limit reached"),
    }


def test_peer_comparison_degrades_when_target_has_no_selection_identity():
    target = company(1, "TARGET", branch_id=None, sector_id=None)

    class Companies:
        def get_by_id(self, company_id):
            return target

        def get_active_companies(self):
            return [target]

    comparison = PeerComparisonBuilder(
        Companies(), SimpleNamespace(), SimpleNamespace()
    ).build(1, as_of=date(2026, 8, 24))

    assert comparison.status == "insufficient_evidence"
    assert comparison.included_peers == ()
    assert comparison.limitations == (
        "target has no branch or sector identity for peer selection",
    )
