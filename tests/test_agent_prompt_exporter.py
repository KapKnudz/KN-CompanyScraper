import json

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.prompt_exporter import AgentPromptExporter
from kncompanyscraper.analysis.agent.prompt_exporter import export_prompt
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt


def test_prompt_exporter_writes_inspectable_json(tmp_path):
    candidate = AgentCandidate(
        rank=2,
        company_id=42,
        ticker="TEST A/B",
        name="Testbolaget",
    )

    paths = AgentPromptExporter().export([candidate], tmp_path)

    assert paths == [tmp_path / "002-42-TEST-A-B.json"]
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["company_id"] == 42
    assert payload["ticker"] == "TEST A/B"
    assert payload["policy_name"] == "nordic-case-investing-policy"
    assert payload["policy_version"] == "1.29.0-ownership-source-contract"
    assert len(payload["policy_sha256"]) == 64
    assert payload["policy_sha256"] in payload["system"]
    assert "Three return engines" in payload["system"]
    assert '"company_id":42' in payload["user"]
    assert payload["schema_name"] == "stock_analysis"
    assert payload["output_schema"]["type"] == "object"
    assert payload["packet_measurement"]["section_sizes"]["research_evidence"] == 2


def test_export_prompt_preserves_exact_model_inputs(tmp_path):
    prompt = AgentPrompt(
        system="system",
        user="user",
        policy_name="policy",
        policy_version="v1",
        policy_sha256="abc",
        schema_name="strict_schema",
        output_schema={"type": "object"},
    )

    path = export_prompt(prompt, tmp_path / "prompt.json", stage="scenario")

    assert json.loads(path.read_text()) == {
        "stage": "scenario",
        "policy_name": "policy",
        "policy_version": "v1",
        "policy_sha256": "abc",
        "system": "system",
        "user": "user",
        "schema_name": "strict_schema",
        "output_schema": {"type": "object"},
    }
