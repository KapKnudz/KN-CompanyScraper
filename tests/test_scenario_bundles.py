import json

from kncompanyscraper.analysis.agent.output_schema import stock_analysis_json_schema
from kncompanyscraper.analysis.agent.result_parser import parse_stock_analysis_result
from tests.test_agent_result_boundary import valid_result
from tests.test_forward_scenario import valid_inputs


def test_parser_builds_three_scenario_bundles_without_calculated_values():
    payload = valid_result().to_dict()
    payload["scenario_bundles"] = [
        {
            **bundle.__dict__,
            **{
                field: (
                    {
                        **getattr(bundle, field).__dict__,
                        "source_ids": list(getattr(bundle, field).source_ids),
                    }
                    if field != "case" and field != "horizon_months" and field != "mechanism"
                    else getattr(bundle, field)
                )
                for field in (
                    "case",
                    "horizon_months",
                    "revenue_cagr",
                    "ebit_margin",
                    "terminal_ev_ebit_low",
                    "terminal_ev_ebit_high",
                    "net_debt_change",
                    "share_count_growth",
                    "distributions_per_share",
                    "mechanism",
                )
            },
        }
        for bundle in valid_inputs().bundles
    ]

    parsed = parse_stock_analysis_result(json.dumps(payload))

    assert [item.case for item in parsed.scenario_bundles] == ["bear", "base", "bull"]
    assert parsed.scenario_bundles[0].revenue_cagr.source_ids == ("report:2026-q2",)
    assert parsed.forward_scenario_analysis is None


def test_schema_exposes_only_the_v2_bundle_contract():
    properties = stock_analysis_json_schema()["properties"]

    assert "scenario_bundles" in properties
