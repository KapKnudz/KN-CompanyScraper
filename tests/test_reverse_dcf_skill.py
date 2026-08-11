from datetime import date

import pytest

from kncompanyscraper.analysis.valuation.dcf_assumption_policy import DcfAssumptionPolicy
from kncompanyscraper.analysis.valuation.reverse_dcf import (
    DcfAssumptions,
    ReverseDcfEngine,
    ReverseDcfInputs,
)
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
    def __init__(self, price, roic=20.0):
        self.price = price
        self.roic = roic

    def get_latest_stock_price(self, company_id):
        return self.price

    def get_general_fundamentals(self, company_id):
        return {37: self.roic}


def _company(branch_id=None):
    return Company(1, "Test", "TEST", None, 42, None, currency="SEK", branch_id=branch_id)


def test_skill_wires_policy_and_all_three_solvers_into_analysis_result():
    annual = _report(2025, 1_000.0, 150.0, 100.0)
    history = [_report(2022, 800.0, 100.0, 70.0)]
    policy = DcfAssumptionPolicy()
    decision = policy.build(
        annual, annual, history, market_cap=1_000.0, roic=20.0
    )
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
    assert result.policy_version == "reverse-dcf-v8"
    assert result.analysis_date == date.today().isoformat()
    assert result.baseline_valuation.value_per_share == pytest.approx(target)
    assert result.reinvestment_roic == pytest.approx(0.20)
    assert result.assumptions.reinvestment_return == pytest.approx(0.20)
    assert result.normalization.confidence == "low"
    assert set(result.implied_expectations) == {
        "revenue_growth",
        "ebit_margin",
        "terminal_growth",
    }
    assert set(result.discount_rate_sensitivities) == {
        "noncyclical_recurring",
        "slightly_cyclical",
        "cyclical_or_other_risk",
    }
    assert [point.revenue_growth for point in result.expectation_curve] == list(
        ReverseDcfSkill.EXPECTATION_CURVE_GROWTH_RATES
    )
    assert all(
        point.ebit_margin_expectation.source_id.startswith(
            "valuation:reverse_dcf:curve:"
        )
        for point in result.expectation_curve
    )
    assert result.discount_rate_sensitivities[
        "noncyclical_recurring"
    ].discount_rate == pytest.approx(0.118)
    assert result.discount_rate_sensitivities[
        "slightly_cyclical"
    ].discount_rate == pytest.approx(0.138)
    assert result.discount_rate_sensitivities[
        "cyclical_or_other_risk"
    ].discount_rate == pytest.approx(0.168)
    for profile, sensitivity in result.discount_rate_sensitivities.items():
        assert set(sensitivity.implied_expectations) == set(result.implied_expectations)
        assert len(sensitivity.expectation_curve) == len(result.expectation_curve)
        assert all(
            point.ebit_margin_expectation.source_id.startswith(
                f"valuation:reverse_dcf:{profile}:curve:"
            )
            for point in sensitivity.expectation_curve
        )
        for assumption, expectation in sensitivity.implied_expectations.items():
            assert expectation.source_id == (
                f"valuation:reverse_dcf:{profile}:{assumption}"
            )
    for expectation in result.implied_expectations.values():
        assert expectation.status == "solved"
        assert expectation.price_difference == pytest.approx(0.0, abs=1e-6)
        assert expectation.source_id.startswith("valuation:reverse_dcf:")
    assert not hasattr(result, "forward_policy_version")
    assert not hasattr(result, "forward_scenarios")


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
    assert "current R12 or annual report unavailable" in result.missing_information
    assert "latest stock price unavailable" in result.missing_information


def test_skill_uses_r12_margin_fallback_when_annual_reports_are_unavailable():
    r12 = _report(2026, 1_000.0, 150.0, 100.0)
    price = StockPrice(date.today(), 10.0, "SEK")

    result = ReverseDcfSkill(
        ValuationRepository(price),
        FinancialRepository(None, [], r12=r12),
    ).run(_company())

    assert result.status == "available"
    assert result.assumptions.ebit_margin == pytest.approx(0.15)
    assert result.normalized_fcf_margin == pytest.approx(0.10)
    assert any("annual operating economics unavailable" in item for item in result.warnings)


def test_skill_converts_borsdata_share_millions_to_sek_market_cap():
    annual = _report(2025, 1_000.0, 150.0, 100.0)
    price = StockPrice(date.today(), 100.0, "SEK")

    result = ReverseDcfSkill(
        ValuationRepository(price),
        FinancialRepository(annual, []),
    ).run(_company())

    assert result.required_return.market_cap == pytest.approx(10_000_000_000.0)
    assert result.required_return.size_bucket == "lower_mid"
    assert result.required_return.size_adjustment == pytest.approx(0.01)


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


def test_skill_explains_which_side_of_a_solver_bound_the_price_requires():
    annual = _report(2025, 1_000.0, 150.0, 100.0)
    price = StockPrice(date.today(), 1_000.0, "SEK")

    result = ReverseDcfSkill(
        ValuationRepository(price),
        FinancialRepository(annual, []),
    ).run(_company())

    expectation = result.implied_expectations["revenue_growth"]
    assert expectation.status == "outside_bounds"
    assert expectation.outside_direction == "above_upper_bound"
    assert expectation.required_value_hint == "revenue_growth > 30.0%"


def test_curve_explains_when_growth_reinvestment_makes_margin_irrelevant():
    inputs = ReverseDcfInputs(
        current_price=100.0,
        shares_outstanding=100.0,
        current_revenue=1_000.0,
        net_debt=0.0,
        assumptions=DcfAssumptions(
            projection_years=5,
            revenue_growth=0.0,
            ebit_margin=0.15,
            tax_rate=0.21,
            discount_rate=0.12,
            terminal_growth=0.02,
            reinvestment_return=0.01,
        ),
    )

    point = ReverseDcfSkill(
        ValuationRepository(None),
        FinancialRepository(None, []),
    )._growth_margin_point(inputs, 0.05)

    expectation = point.ebit_margin_expectation
    assert expectation.status == "outside_bounds"
    assert expectation.outside_direction == "not_determined"
    assert "growth / ROIC consumes 100% of NOPAT" in expectation.required_value_hint
