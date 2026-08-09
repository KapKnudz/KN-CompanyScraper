import pytest

from kncompanyscraper.analysis.valuation.forward_dcf_policy import ForwardDcfScenarioPolicy
from kncompanyscraper.analysis.valuation.reverse_dcf import DcfAssumptions
from tests.test_reverse_dcf_skill import _report


def test_scenarios_use_company_history_and_normalize_negative_reinvestment():
    base = DcfAssumptions(
        projection_years=5,
        revenue_growth=0.05,
        ebit_margin=0.15,
        tax_rate=0.21,
        discount_rate=0.10,
        terminal_growth=0.02,
        net_reinvestment_rate=-0.01,
    )
    latest = _report(2025, 1_000.0, 150.0, 100.0)
    history = [
        _report(2023, 800.0, 80.0, 70.0),
        _report(2024, 900.0, 108.0, 80.0),
    ]

    decision = ForwardDcfScenarioPolicy().build(base, latest, history)
    scenarios = {scenario.label: scenario.assumptions for scenario in decision.scenarios}

    assert decision.policy_version == "forward-dcf-scenarios-v1"
    assert scenarios["bear"].revenue_growth == pytest.approx(0.0)
    assert scenarios["base"].revenue_growth == pytest.approx(0.05)
    assert scenarios["bull"].revenue_growth == pytest.approx(0.125)
    assert scenarios["bear"].ebit_margin == pytest.approx(0.10)
    assert scenarios["base"].ebit_margin == pytest.approx(0.15)
    assert scenarios["bull"].ebit_margin == pytest.approx(0.18)
    assert scenarios["bear"].net_reinvestment_rate == pytest.approx(0.02)
    assert scenarios["base"].net_reinvestment_rate == pytest.approx(0.0)
    assert scenarios["bull"].net_reinvestment_rate == pytest.approx(0.0)
    assert any("negative reinvestment" in warning for warning in decision.warnings)


def test_scenarios_use_bounded_fallback_stress_without_history():
    base = DcfAssumptions(5, 0.03, 0.10, 0.21, 0.10, 0.02, 0.04)

    decision = ForwardDcfScenarioPolicy().build(base, None, [])
    scenarios = {scenario.label: scenario.assumptions for scenario in decision.scenarios}

    assert scenarios["bear"].revenue_growth == pytest.approx(-0.02)
    assert scenarios["bull"].revenue_growth == pytest.approx(0.08)
    assert scenarios["bear"].ebit_margin == pytest.approx(0.07)
    assert scenarios["bull"].ebit_margin == pytest.approx(0.13)
