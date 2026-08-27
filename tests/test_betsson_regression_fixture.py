import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures/stock_analysis/003-37-BETS-B-response.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_betsson_fixture_is_the_raw_stage_with_no_persisted_forward_result():
    fixture = load_fixture()

    assert fixture["artifact_stage"] == "raw_model_response"
    assert fixture["lifecycle_evidence"] == {
        "artifact_type_field": None,
        "validation_metadata": None,
        "persisted_content": None,
        "forward_methodology_flags": None,
    }
    assert fixture["forward_scenario_analysis"] is None
    assert fixture["valuation_scenarios"] == []
    assert all(value is None for value in fixture["expected_return_components"].values())


def test_betsson_fixture_preserves_all_eight_scenario_inputs_and_guardrail_sources():
    fixture = load_fixture()
    endpoints = fixture["forward_scenario_assumptions"]

    assert len(endpoints) == 8
    assert {(endpoint["kind"], endpoint["side"]) for endpoint in endpoints} == {
        ("base", "low"),
        ("base", "high"),
        ("bull", "low"),
        ("bull", "high"),
        ("bear_multiple_compression", "low"),
        ("bear_multiple_compression", "high"),
        ("bear_fundamental_impairment", "low"),
        ("bear_fundamental_impairment", "high"),
    }
    assert all(endpoint["horizon_months"] == 36 for endpoint in endpoints)
    assert all(
        endpoint["source_ids"]["terminal_ev_ebit"]
        for endpoint in endpoints
    )
    assert fixture["risk_profile_confidence"] == "high"
    assert fixture["risk_profile_evidence"] == []
