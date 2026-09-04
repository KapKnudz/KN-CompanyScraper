from datetime import date
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.peak_margin_bridge import (
    build_peak_margin_bridge,
)
from tests.test_forward_scenario import valid_inputs


def report(year, revenue, gross_income, ebit, *, r12=False):
    return SimpleNamespace(
        year=year,
        period_end=date(year, 12, 31),
        revenue=revenue,
        gross_income=gross_income,
        ebit=ebit,
        broken_fiscal_year=False,
        source_id=f"financial:{'r12' if r12 else 'annual'}:{year}-12-31",
    )


def test_bridge_calculates_historical_spread_and_margin_runway_without_forecast_gross_margin():
    annual = (
        report(2025, 120.0, 72.0, 18.0),
        report(2024, 100.0, 60.0, 20.0),
        report(2023, 80.0, 40.0, 8.0),
    )
    result = SimpleNamespace(
        scenario_bundles=valid_inputs().bundles,
        margin_expansion_case=SimpleNamespace(
            required_operating_changes=["Scale support capacity without matching opex growth."],
            source_ids=["report:2026-q2"],
        ),
    )
    candidate = SimpleNamespace(
        full_results={
            "financial_history": {
                "annual_reports": annual,
                "latest_r12": report(2025, 120.0, 72.0, 18.0, r12=True),
            }
        }
    )

    bridge = build_peak_margin_bridge(candidate, result)

    assert bridge["status"] == "available"
    assert bridge["current"]["ebit_margin"] == pytest.approx(0.15)
    assert bridge["current"]["gross_to_ebit_spread"] == pytest.approx(0.45)
    assert bridge["peak"]["period"] == 2024
    assert bridge["peak"]["ebit_margin"] == pytest.approx(0.20)
    assert bridge["peak"]["gross_margin"] == pytest.approx(0.60)
    assert bridge["bridge"]["margin_runway"] == pytest.approx(0.05)
    assert bridge["bridge"]["gross_to_ebit_spread_change"] == pytest.approx(-0.05)

    base = next(item for item in bridge["forecast"] if item["case"] == "base")
    assert base["gross_margin"] is None
    assert base["gross_to_ebit_spread"] is None
    assert base["gross_margin_status"] == "unavailable"
    assert bridge["qualitative_operating_changes"]
