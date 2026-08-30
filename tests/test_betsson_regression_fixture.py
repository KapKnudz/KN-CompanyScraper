import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures/stock_analysis/003-37-BETS-B-response.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_betsson_fixture_is_the_raw_stage_with_no_persisted_forward_result():
    fixture = load_fixture()

    assert fixture["historical_note"].startswith("Historical pre-v2 raw model response")
    assert fixture["artifact_contract_version"] == "individual-thesis-card-v1"
    assert fixture["artifact_stage"] == "raw_model_response"
    assert fixture["lifecycle_evidence"] == {
        "artifact_type_field": None,
        "validation_metadata": None,
        "persisted_content": None,
        "forward_methodology_flags": None,
    }
    assert fixture["forward_scenario_analysis"] is None
    assert fixture["risk_profile_confidence"] == "high"
    assert fixture["risk_profile_evidence"] == []
