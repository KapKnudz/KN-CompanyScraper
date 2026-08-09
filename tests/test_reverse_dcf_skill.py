from datetime import date

import pytest

from kncompanyscraper.analysis.valuation.dcf_assumption_policy import DcfAssumptionPolicy
from kncompanyscraper.analysis.valuation.reverse_dcf import ReverseDcfEngine, ReverseDcfInputs
from kncompanyscraper.analysis.valuation.reverse_dcf_skill import ReverseDcfSkill
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.models.company import Company


def _report(year, revenue, ebit, fcf):
    return Report(
        revenue=revenue,
        operating_profit=ebit,
        ebit=ebit,
        ebitda=None,
        net_income=80.0,
        free_cash_flow=fcf,
        equity=500.0,
        total_assets=800.0,
        total_debt=100.0,
        shares_outstanding=100.0,
        year=year,
        period_end=date(year, 12, 31),
        currency="SEK",
    )


class FinancialRepository:
    def __init__(self, annual, history, r12=None):
        self.annual = annual
        self.history = history
        self.r12 = r12

    def get_latest_report(self, company_id, period_type="year"):
        return self.r12 if period_type == "r12" else self.annual

    def get_historical_reports(self, company_id, period_type="year"):
        return self.history


class ValuationRepository:
    def __init__(self, price):
        self.price = price

    def get_latest_stock_price(self, company_id):
        return self.price


def _company(branch_id=None):
    return Company(1, "Test", "TEST", None, 42, None, currency="SEK", branch_id=branch_id)


def test_skill_wires_policy_and_all_three_solvers_into_analysis_result():
    annual = _report(2025, 1_000.0, 150.0, 100.0)
    history = [_report(2022, 800.0, 100.0, 70.0)]
    policy = DcfAssumptionPolicy()
    decision = policy.build(annual, annual, history)
    target = ReverseDcfEngine().value(
        ReverseDcfInputs(
            current_price=1.0,
            shares_outstanding=annual.shares_outstanding,
            current_revenue=annual.revenue,
            net_debt=annual.total_debt,
            assumptions=decision.assumptions,
        )
    ).value_per_share
    price = StockPrice(date.today(), target, "SEK")

    result = ReverseDcfSkill(
        ValuationRepository(price),
        FinancialRepository(annual, history),
        policy=policy,
    ).run(_company())

    assert result.status == "available"
    assert result.policy_version == "reverse-dcf-v2"
    assert result.analysis_date == date.today().isoformat()
    assert result.baseline_valuation.value_per_share == pytest.approx(target)
    assert set(result.implied_expectations) == {
        "revenue_growth",
        "ebit_margin",
        "terminal_growth",
    }
    for expectation in result.implied_expectations.values():
        assert expectation.status == "solved"
        assert expectation.price_difference == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    ("branch_id", "model"),
    [(68, "residual_income_or_dividend"), (75, "nav_or_ffo")],
)
def test_skill_routes_bank_and_property_companies_away_from_fcff(branch_id, model):
    result = ReverseDcfSkill(
        ValuationRepository(None),
        FinancialRepository(None, []),
    ).run(_company(branch_id))

    assert result.status == "unsupported_model"
    assert result.required_model == model


def test_skill_returns_reasons_instead_of_inventing_missing_inputs():
    result = ReverseDcfSkill(
        ValuationRepository(None),
        FinancialRepository(None, []),
    ).run(_company())

    assert result.status == "unavailable"
    assert "latest annual report unavailable" in result.missing_information
    assert "latest stock price unavailable" in result.missing_information


def test_skill_rejects_stale_or_currency_mismatched_price():
    annual = _report(2025, 1_000.0, 150.0, 100.0)
    stale = StockPrice(date(2026, 1, 1), 10.0, "EUR")

    result = ReverseDcfSkill(
        ValuationRepository(stale),
        FinancialRepository(annual, []),
        as_of=date(2026, 8, 9),
    ).run(_company())

    assert result.status == "unavailable"
    assert "stock price is older than 7 days" in result.missing_information
    assert "stock price and report currencies differ" in result.missing_information
