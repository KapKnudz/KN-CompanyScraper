import json
from dataclasses import asdict

import pytest

from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.agent.output_schema import (
    stock_analysis_json_schema,
    thesis_update_json_schema,
)
from tests.test_agent_result_boundary import valid_result
from tests.test_forward_scenario import valid_inputs


ASSUMPTION_NAMES = (
    "revenue_cagr",
    "ebit_margin",
    "terminal_ev_ebit",
    "net_debt",
    "net_debt_change",
    "share_count_growth",
    "distributions_per_share",
)


def compact_response():
    payload = valid_result().to_dict()
    expanded = [asdict(endpoint) for endpoint in valid_inputs().endpoints]
    by_key = {
        f"{endpoint['kind']}_{endpoint['side']}": endpoint for endpoint in expanded
    }
    compact = []
    for endpoint in expanded:
        key = f"{endpoint['kind']}_{endpoint['side']}"
        base_key = None if endpoint["kind"] == "base" else f"base_{endpoint['side']}"
        if base_key is None:
            base_assumptions = {
                name: endpoint[name] for name in ASSUMPTION_NAMES
            }
            overrides = []
        else:
            base_assumptions = None
            base = by_key[base_key]
            overrides = [
                {"field": name, "assumption": endpoint[name]}
                for name in ASSUMPTION_NAMES
                if endpoint[name] != base[name]
            ]
        compact.append(
            {
                "kind": endpoint["kind"],
                "side": endpoint["side"],
                "horizon_months": endpoint["horizon_months"],
                "base_endpoint": base_key,
                "base_assumptions": base_assumptions,
                "overrides": overrides,
            }
        )
    payload["forward_scenario_assumptions"] = compact
    return payload, expanded


def test_parser_expands_compact_endpoints_without_changing_assumptions():
    payload, expanded = compact_response()

    result = parse_stock_analysis_result(json.dumps(payload))

    assert [asdict(endpoint) for endpoint in result.forward_scenario_assumptions] == expanded


def test_compact_authoring_is_smaller_than_the_expanded_bundle():
    compact, expanded = compact_response()
    expanded_payload = valid_result().to_dict()
    expanded_payload["forward_scenario_assumptions"] = expanded

    assert len(json.dumps(compact)) < len(json.dumps(expanded_payload))


def test_parser_rejects_missing_compact_inheritance_base():
    payload, _ = compact_response()
    inherited = next(
        endpoint
        for endpoint in payload["forward_scenario_assumptions"]
        if endpoint["kind"] == "bull"
    )
    inherited["base_endpoint"] = "base_missing"

    with pytest.raises(
        StockAnalysisValidationError, match="references missing endpoint"
    ):
        parse_stock_analysis_result(json.dumps(payload))


def test_parser_rejects_cyclic_compact_inheritance():
    payload, _ = compact_response()
    base_low = next(
        endpoint
        for endpoint in payload["forward_scenario_assumptions"]
        if endpoint["kind"] == "base" and endpoint["side"] == "low"
    )
    base_high = next(
        endpoint
        for endpoint in payload["forward_scenario_assumptions"]
        if endpoint["kind"] == "base" and endpoint["side"] == "high"
    )
    base_low["base_endpoint"] = "base_high"
    base_low["base_assumptions"] = None
    base_high["base_endpoint"] = "base_low"
    base_high["base_assumptions"] = None

    with pytest.raises(
        StockAnalysisValidationError, match="cyclic compact scenario inheritance"
    ):
        parse_stock_analysis_result(json.dumps(payload))


def test_parser_rejects_non_multiple_override_on_compression_endpoint():
    payload, _ = compact_response()
    compression = next(
        endpoint
        for endpoint in payload["forward_scenario_assumptions"]
        if endpoint["kind"] == "bear_multiple_compression"
    )
    compression["overrides"].append(
        {
            "field": "revenue_cagr",
            "assumption": compression["overrides"][0]["assumption"],
        }
    )

    with pytest.raises(
        StockAnalysisValidationError, match="may override only terminal_ev_ebit"
    ):
        parse_stock_analysis_result(json.dumps(payload))


def test_output_schema_accepts_expanded_or_compact_endpoint_items():
    schema = stock_analysis_json_schema()
    items = schema["properties"]["forward_scenario_assumptions"]["items"]

    assert len(items["oneOf"]) == 2
    assert items["oneOf"][1]["properties"]["base_endpoint"]["type"] == [
        "string",
        "null",
    ]
    update_schema = thesis_update_json_schema()
    update_items = update_schema["properties"]["thesis"]["properties"][
        "forward_scenario_assumptions"
    ]["items"]
    assert len(update_items["oneOf"]) == 2
