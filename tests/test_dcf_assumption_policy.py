from datetime import date

import pytest

from kncompanyscraper.analysis.valuation.dcf_assumption_policy import (
    DcfAssumptionPolicy,
)
from kncompanyscraper.borsdata.report import Report


def _report(revenue, ebit, fcf, year=2025):
    return Report(
        revenue=revenue,
        operating_profit=ebit,
        ebit=ebit,
        ebitda=None,
        net_income=None,
        free_cash_flow=fcf,
        equity=None,
        total_assets=None,
        total_debt=100.0,
        shares_outstanding=100.0,
        year=year,
        period_end=date(year, 12, 31),
        currency="SEK",
    )


def test_builds_explicit_assumptions_from_current_and_historical_reports():
    policy = DcfAssumptionPolicy()
    current = _report(1_200.0, 180.0, 110.0, 2026)
    latest_annual = _report(1_100.0, 154.0, 100.0, 2025)
    history = [
        _report(800.0, 100.0, 70.0, 2022),
        _report(900.0, 115.0, 80.0, 2023),
        _report(1_000.0, 135.0, 90.0, 2024),
    ]

    decision = policy.build(current, latest_annual, history)

    assert decision.available
    assert decision.assumptions.projection_years == 5
    assert decision.assumptions.discount_rate == 0.10
    assert decision.assumptions.tax_rate == 0.21
    assert decision.assumptions.terminal_growth == 0.02
    assert decision.assumptions.revenue_growth == pytest.approx(
        (1_100.0 / 800.0) ** (1 / 3) - 1
    )
    assert decision.assumptions.ebit_margin == pytest.approx(0.15)
    assert decision.assumptions.net_reinvestment_rate == pytest.approx(
        (180.0 * 0.79 - 110.0) / 1_200.0
    )
    assert decision.solve_bounds == {
        "revenue_growth": (-0.10, 0.30),
        "ebit_margin": (0.0, 0.50),
        "terminal_growth": (-0.01, 0.04),
    }


def test_uses_disclosed_zero_growth_fallback_when_history_is_insufficient():
    current = _report(1_000.0, 100.0, 60.0)

    decision = DcfAssumptionPolicy().build(current, current, [])

    assert decision.available
    assert decision.assumptions.revenue_growth == 0.0
    assert "zero-growth fallback" in decision.assumption_sources["revenue_growth"]
    assert "historical revenue growth unavailable" in decision.warnings


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("revenue", None, "current revenue"),
        ("ebit", 0.0, "positive current EBIT"),
        ("free_cash_flow", -1.0, "positive current free cash flow"),
    ],
)
def test_marks_model_unavailable_when_core_operating_input_is_missing(
    field,
    value,
    reason,
):
    report = _report(1_000.0, 100.0, 60.0)
    setattr(report, field, value)

    decision = DcfAssumptionPolicy().build(report, report, [])

    assert not decision.available
    assert decision.assumptions is None
    assert any(reason in item for item in decision.missing_information)


def test_clamps_growth_and_reinvestment_and_discloses_both_adjustments():
    current = _report(1_000.0, 100.0, 500.0, 2025)
    old = _report(100.0, 10.0, 5.0, 2022)

    decision = DcfAssumptionPolicy().build(current, current, [old])

    assert decision.assumptions.revenue_growth == 0.15
    assert decision.assumptions.net_reinvestment_rate == -0.05
    assert any("revenue growth clamped" in warning for warning in decision.warnings)
    assert any("net reinvestment rate clamped" in warning for warning in decision.warnings)
