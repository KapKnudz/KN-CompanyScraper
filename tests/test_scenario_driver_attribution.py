from datetime import date
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.scenario_driver_attribution import (
    build_scenario_driver_attribution,
)
from tests.test_forward_scenario import valid_inputs


def test_shapley_attribution_reconciles_each_endpoint_to_holding_value_change():
    bundles = valid_inputs().bundles
    current_report = SimpleNamespace(
        year=2025,
        period_end=date(2025, 12, 31),
        revenue=100.0,
        ebit=10.0,
        broken_fiscal_year=False,
        source_id="financial:r12:2025-12-31",
    )
    candidate = SimpleNamespace(
        full_results={
            "financial_history": {"latest_r12": current_report},
            "reverse_dcf": {
                "current_revenue": 100.0,
                "current_shares": 10.0,
                "current_net_debt": 20.0,
            },
            "valuation": {"raw_ev_ebit": 8.0},
        }
    )
    result = SimpleNamespace(case_horizon_months=36, scenario_bundles=bundles)

    attribution = build_scenario_driver_attribution(candidate, result)

    assert attribution["status"] == "available"
    assert attribution["method"] == "shapley"
    assert attribution["reference"]["state"] == "no_change"
    assert attribution["reference"]["holding_value"] == pytest.approx(6.0)
    assert len(attribution["endpoints"]) == 6
    for endpoint in attribution["endpoints"]:
        assert endpoint["reconciles"] is True
        assert endpoint["contribution_sum"] == pytest.approx(
            endpoint["holding_value_change"]
        )
        assert set(endpoint["contributions"]) == {
            "revenue_cagr",
            "ebit_margin",
            "net_debt_change",
            "share_count_growth",
            "distributions_per_share",
            "terminal_ev_ebit",
        }
        assert set(endpoint["driver_source_ids"]) == set(endpoint["contributions"])
