import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures/stock_analysis"
FIXTURE_NAMES = (
    "004-4-CLAS-B-validated-baseline.json",
    "114-MSAB-B-validated-baseline.json",
    "143-GENI-validated-baseline.json",
)


def load_fixtures() -> list[dict]:
    return [
        json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        for name in FIXTURE_NAMES
    ]


def test_critique_fixtures_capture_accepted_persisted_baseline_weaknesses():
    fixtures = load_fixtures()

    assert {fixture["company_id"] for fixture in fixtures} == {4, 114, 143}
    for fixture in fixtures:
        assert fixture["artifact_stage"] == "persisted_validated_analysis"
        assert fixture["validation_status"] == "accepted"
        assert fixture["current_output"]["risk_profile"]["evidence"] == []
        assert fixture["current_output"]["forward_scenario"]["status"] == "available"
        assert len(fixture["current_output"]["h1_facts"]) >= 1
        assert fixture["expected_output_note"]


def test_critique_fixtures_are_pre_regeneration_baselines():
    fixtures = load_fixtures()

    assert all(
        fixture["current_output"]["forward_scenario"]["policy_version"]
        == "forward-scenario-v5-three-bundles"
        for fixture in fixtures
    )
    assert all("revenue_resilience" not in fixture["current_output"] for fixture in fixtures)
