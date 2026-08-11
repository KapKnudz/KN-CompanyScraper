from datetime import date

import pytest

from kncompanyscraper.analysis.valuation.dcf_assumption_policy import (
    DcfAssumptionPolicy,
)
from kncompanyscraper.borsdata.report import Report


def _report(revenue, ebit, fcf, year=2025, *, ocf=None, investing=None):
    return Report(
        revenue=revenue,
        operating_profit=ebit,
        ebit=ebit,
        ebitda=None,
        net_income=None,
        free_cash_flow=fcf,
        operating_cash_flow=ocf,
        investing_cash_flow=investing,
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

    decision = policy.build(current, latest_annual, history, roic=20.0)

    assert decision.available
    assert decision.assumptions.projection_years == 5
    assert decision.assumptions.discount_rate == pytest.approx(0.118)
    assert decision.required_return.risk_free_rate_date == "2026-07-24"
    assert decision.assumptions.tax_rate == 0.21
    assert decision.assumptions.terminal_growth == 0.02
    assert decision.assumptions.revenue_growth == pytest.approx(
        (1_100.0 / 800.0) ** (1 / 3) - 1
    )
    assert decision.assumptions.ebit_margin == pytest.approx(
        (115.0 + 135.0 + 154.0) / (900.0 + 1_000.0 + 1_100.0)
    )
    assert decision.assumption_sources["ebit_margin"] == (
        "revenue-weighted EBIT margin over annual years 2023-2025"
    )
    assert any("five-year operating-margin history unavailable" in item for item in decision.warnings)
    assert decision.assumptions.net_reinvestment_rate == pytest.approx(
        decision.assumptions.ebit_margin
        * 0.79
        * (decision.assumptions.revenue_growth / 0.20)
    )
    assert decision.reinvestment_roic == pytest.approx(0.20)
    assert decision.assumptions.reinvestment_return == pytest.approx(0.20)
    assert decision.normalized_fcf_margin == pytest.approx(0.09)
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


def test_uses_five_year_revenue_weighted_ebit_margin_when_available():
    current = _report(1_300.0, 260.0, 120.0, 2026)
    latest = _report(1_200.0, 240.0, 110.0, 2025)
    history = [
        _report(800.0, 80.0, 60.0, 2021),
        _report(900.0, 108.0, 70.0, 2022),
        _report(1_000.0, 150.0, 80.0, 2023),
        _report(1_100.0, 198.0, 90.0, 2024),
    ]

    decision = DcfAssumptionPolicy().build(current, latest, history, roic=20.0)

    assert decision.assumptions.ebit_margin == pytest.approx(
        (80.0 + 108.0 + 150.0 + 198.0 + 240.0)
        / (800.0 + 900.0 + 1_000.0 + 1_100.0 + 1_200.0)
    )
    assert decision.assumption_sources["ebit_margin"] == (
        "revenue-weighted EBIT margin over annual years 2021-2025"
    )
    assert decision.normalization.confidence == "medium"
    assert decision.normalization.three_year.years == 3
    assert decision.normalization.five_year.years == 5
    assert not any("EBIT margin history unavailable" in item for item in decision.warnings)


def test_falls_back_to_latest_annual_margin_when_three_year_history_is_unavailable():
    current = _report(1_200.0, 240.0, 110.0, 2026)
    latest = _report(1_000.0, 150.0, 90.0, 2025)
    history = [_report(900.0, 90.0, 70.0, 2024)]

    decision = DcfAssumptionPolicy().build(current, latest, history, roic=20.0)

    assert decision.assumptions.ebit_margin == pytest.approx(0.15)
    assert decision.assumption_sources["ebit_margin"] == (
        "revenue-weighted EBIT margin over annual year 2025"
    )
    assert any("three-year operating-margin history unavailable" in item for item in decision.warnings)


def test_falls_back_to_r12_margin_when_annual_margin_is_unavailable():
    current = _report(1_200.0, 240.0, 110.0, 2026)

    decision = DcfAssumptionPolicy().build(current, None, [], roic=20.0)

    assert decision.available
    assert decision.assumptions.ebit_margin == pytest.approx(0.20)
    assert decision.assumption_sources["ebit_margin"] == (
        "current R12 EBIT margin fallback"
    )
    assert any("annual operating economics unavailable" in item for item in decision.warnings)


def test_current_loss_does_not_block_positive_historical_margin_normalization():
    current = _report(1_200.0, -20.0, 30.0, 2026)
    latest = _report(1_100.0, 110.0, 80.0, 2025)
    history = [
        _report(900.0, 90.0, 60.0, 2023),
        _report(1_000.0, 100.0, 70.0, 2024),
    ]

    decision = DcfAssumptionPolicy().build(current, latest, history)

    assert decision.available
    assert decision.assumptions.ebit_margin == pytest.approx(0.10)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("revenue", None, "current revenue"),
        ("ebit", None, "normalized EBIT"),
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


def test_clamps_growth_and_roic_derived_reinvestment_and_discloses_both_adjustments():
    current = _report(1_000.0, 500.0, 500.0, 2025)
    old = _report(100.0, 50.0, 5.0, 2022)

    decision = DcfAssumptionPolicy().build(current, current, [old], roic=1.0)

    assert decision.assumptions.revenue_growth == 0.15
    assert decision.assumptions.net_reinvestment_rate == 0.15
    assert any("revenue growth clamped" in warning for warning in decision.warnings)
    assert any("net reinvestment rate clamped" in warning for warning in decision.warnings)


def test_negative_normalized_fcf_is_preserved_as_low_confidence_diagnostic():
    current = _report(1_000.0, 100.0, -20.0, 2025)

    decision = DcfAssumptionPolicy().build(current, current, [], roic=20.0)

    assert decision.available
    assert decision.normalized_fcf_margin == pytest.approx(-0.02)
    assert decision.normalization.confidence == "low"
    assert decision.normalization.negative_fcf_years == 1
    assert any("non-positive" in item for item in decision.normalization.reasons)


def test_missing_reported_fcf_does_not_block_roic_based_reinvestment():
    current = _report(1_000.0, 100.0, None)

    decision = DcfAssumptionPolicy().build(current, current, [], roic=20.0)

    assert decision.available
    assert decision.normalized_fcf_margin is None
    assert decision.assumptions.net_reinvestment_rate == 0.0


def test_exposes_three_and_five_year_windows_and_flags_instability():
    reports = [
        _report(100.0, 10.0, -50.0, 2021, ocf=10.0, investing=-60.0),
        _report(100.0, 10.0, 10.0, 2022, ocf=20.0, investing=-10.0),
        _report(100.0, 10.0, -40.0, 2023, ocf=10.0, investing=-50.0),
        _report(100.0, 30.0, 20.0, 2024, ocf=30.0, investing=-10.0),
        _report(100.0, 30.0, 30.0, 2025, ocf=40.0, investing=-10.0),
    ]

    decision = DcfAssumptionPolicy().build(
        reports[-1], reports[-1], reports[:-1], roic=20.0
    )

    assert decision.normalization.three_year.ebit_margin == pytest.approx(0.70 / 3)
    assert decision.normalization.five_year.ebit_margin == pytest.approx(0.18)
    assert decision.normalization.three_year.reported_fcf_margin == pytest.approx(0.10 / 3)
    assert decision.normalization.five_year.reported_fcf_margin == pytest.approx(-0.06)
    assert decision.normalization.highly_volatile_fcf
    assert decision.normalization.material_window_disagreement
    assert decision.normalization.material_aggregate_investing
    assert decision.normalization.confidence == "low"


def test_positive_roic_is_required_for_nonzero_reinvestment():
    current = _report(1_000.0, 100.0, 60.0)
    old = _report(800.0, 80.0, 50.0, 2022)

    decision = DcfAssumptionPolicy().build(current, current, [old], roic=-5.0)

    assert decision.assumptions.net_reinvestment_rate == 0.0
    assert decision.normalization.confidence == "low"
    assert any("positive Börsdata ROIC" in item for item in decision.normalization.reasons)
