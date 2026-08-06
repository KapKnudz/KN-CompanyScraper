import json

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.prompt_exporter import AgentPromptExporter


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
    assert "Three return engines" in payload["system"]
    assert '"company_id": 42' in payload["user"]
