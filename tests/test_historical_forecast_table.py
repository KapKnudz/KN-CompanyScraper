from datetime import date
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.historical_forecast_table import (
    build_historical_forecast_table,
)
from tests.test_forward_scenario import valid_inputs


def report(year, revenue, gross_income, ebit, net_debt, shares):
    return SimpleNamespace(
        year=year,
        period_end=date(year, 12, 31),
        revenue=revenue,
        gross_income=gross_income,
        ebit=ebit,
        total_debt=net_debt,
        shares_outstanding=shares,
        broken_fiscal_year=False,
        source_id=f"financial:annual:{year}-12-31",
    )


def candidate():
    return SimpleNamespace(
        full_results={
            "financial_history": {
                "annual_reports": (
                    report(2025, 120.0, 72.0, 18.0, 25.0, 10.0),
                    report(2024, 100.0, 60.0, 12.0, 20.0, 9.5),
                    report(2023, 80.0, 40.0, 8.0, 15.0, 9.0),
                )
            },
            "reverse_dcf": {
                "current_revenue": 120.0,
                "current_net_debt": 25.0,
                "current_shares": 10.0,
            },
        }
    )


def test_table_combines_history_and_scenario_endpoints_without_inventing_gross_margin():
    inputs = valid_inputs()
    result = SimpleNamespace(
        case_horizon_months=36,
        scenario_bundles=inputs.bundles,
    )
    analysis = SimpleNamespace(status="available")

    table = build_historical_forecast_table(candidate(), result, analysis)

    assert table["columns"] == [
        "revenue",
        "gross_margin",
        "ebit_margin",
        "ebit",
        "net_debt",
        "share_count",
    ]
    assert len(table["rows"]) == 6
    historical = table["rows"][0]
    assert historical["gross_margin"] == pytest.approx(0.60)
    assert historical["ebit_margin"] == pytest.approx(0.15)
    assert historical["net_debt"] == 25.0

    base = next(row for row in table["rows"] if row["case"] == "base")
    base_bundle = next(bundle for bundle in inputs.bundles if bundle.case == "base")
    assert base["revenue"] == pytest.approx(
        120.0 * (1 + base_bundle.revenue_cagr.value) ** 3
    )
    assert base["ebit"] == pytest.approx(
        base["revenue"] * base_bundle.ebit_margin.value
    )
    assert base["net_debt"] == pytest.approx(
        25.0 + base_bundle.net_debt_change.value
    )
    assert base["share_count"] == pytest.approx(
        10.0 * (1 + base_bundle.share_count_growth.value)
    )
    assert base["gross_margin"] is None
    assert base["gross_margin_status"] == "unavailable"
    assert any("gross margin unavailable" in item for item in table["limitations"])
