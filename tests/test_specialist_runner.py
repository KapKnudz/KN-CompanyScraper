import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.prompt_artifact import serialize_prompt
from kncompanyscraper.analysis.agent.specialist_runner import (
    FIRST_WAVE_SPECIALISTS,
    ShadowSpecialistRunner,
    SpecialistPromptBuilder,
)


def packet():
    return AgentCandidatePacket(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Test Company",
        ranking_model="general",
        rank_eligible=True,
        eligibility_reasons=[],
        total_score=1.0,
        score_breakdown={},
        data_quality="medium",
        flags=[],
        candidate_reason=None,
        positives=[],
        negatives=[],
        missing_data=[],
        full_results={"financial_history": {"revenue": 10}},
        research_evidence={"as_of": "2026-08-16", "documents": []},
    )


def management_output(packet, run_id, *, valid=True):
    return json.dumps(
        {
            "schema_version": "specialist-output-v1",
            "run_id": run_id if valid else "wrong-run",
            "agent_name": "management_credibility",
            "company_id": packet.company_id,
            "ticker": packet.ticker,
            "evidence_as_of": "2026-08-16",
            "status": "complete",
            "confidence": "low",
            "confidence_cap": "low",
            "claims": [],
            "missing_information": [],
            "packet_hash": "placeholder",
            "management_credibility": {
                "coverage": {
                    "coverage_tier": "no_ledger",
                    "coverage_state": "insufficient_for_pattern_recognition",
                    "quarters_covered": 0,
                    "data_source_type": "none",
                    "eligible_claim_count": 0,
                    "assessed_claim_count": 0,
                    "pending_claim_count": 0,
                    "omitted_claim_count": 0,
                    "omission_reasons": [],
                    "confidence_cap": "low",
                },
                "pattern_state": "unassessable",
                "ledger": [],
                "claims": [],
            },
        }
    )


class Model:
    def __init__(self, response_factory):
        self.response_factory = response_factory
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return SimpleNamespace(
            output_text=self.response_factory(prompt),
            model="fake-model",
            response_id=f"response-{self.calls}",
            usage={"total_tokens": 1},
        )


class Artifacts:
    def __init__(self):
        self.saved = []
        self.validation = []

    def save_specialist_artifact(self, company_id, raw_response, created_by, **kwargs):
        artifact_id = len(self.saved) + 1
        metadata = {
            **kwargs.pop("metadata", {}),
            "analysis_mode": "specialist",
            "agent_name": kwargs["agent_name"],
            "run_id": kwargs["run_id"],
            "packet_hash": kwargs["packet_hash"],
            "validation_status": "pending",
        }
        self.saved.append(
            {
                "id": artifact_id,
                "company_id": company_id,
                "content": raw_response,
                "metadata": metadata,
                **kwargs,
            }
        )
        return artifact_id

    def update_raw_validation(self, artifact_id, status, error=None):
        self.validation.append((artifact_id, status, error))


def test_shadow_runner_uses_frozen_hash_and_persists_non_authoritative_metadata():
    artifacts = Artifacts()
    run_id = "company-analysis-7"
    model = Model(lambda prompt: "{}")
    runner = ShadowSpecialistRunner(
        model,
        artifacts,
        specialists=("management_credibility",),
    )
    frozen = packet()
    frozen_hash = sha256(serialize_packet(frozen).encode()).hexdigest()
    # The response factory needs the hash produced by the runner, so replace the
    # placeholder after the prompt is built by using a response-aware adapter.
    model.response_factory = lambda prompt: management_output(frozen, run_id).replace(
        '"placeholder"', json.dumps(frozen_hash)
    )

    result = runner.run(frozen, run_id=run_id)

    assert result.results[0].status == "accepted"
    assert artifacts.saved[0]["metadata"]["analysis_mode"] == "specialist"
    assert artifacts.saved[0]["metadata"]["agent_name"] == "management_credibility"
    assert artifacts.saved[0]["metadata"]["run_id"] == run_id
    assert artifacts.saved[0]["metadata"]["packet_hash"] == frozen_hash
    assert artifacts.saved[0]["metadata"]["analysis_attempt"] == 1
    assert artifacts.validation == [(1, "accepted", None)]
    prompt_artifact = artifacts.saved[0]["metadata"]["prompt_artifact"]
    assert artifacts.saved[0]["metadata"]["prompt_sha256"] == sha256(
        prompt_artifact.encode()
    ).hexdigest()
    assert json.loads(prompt_artifact)["prompt"]["schema_name"] == (
        "specialist_management_credibility"
    )


def test_first_wave_prompt_selection_targets_one_closed_domain_per_agent():
    expected = {
        "business_model": ("revenue mechanics", "activation decision"),
        "management_credibility": ("coverage_tier", "binary investability gate"),
        "margin": ("defensible peak EBIT margin", "fair value"),
        "insider_ownership": ("data_coverage", "rescue weak business fundamentals"),
        "growth_valuation": ("deterministic scenario engine", "target price"),
    }

    for agent_name in FIRST_WAVE_SPECIALISTS:
        prompt = SpecialistPromptBuilder().build(packet(), agent_name)
        domain = agent_name.value

        assert prompt.schema_name == f"specialist_{domain}"
        assert set(prompt.output_schema["properties"]) >= {
            "agent_name",
            domain,
        }
        assert prompt.output_schema["properties"][domain]["type"] == "object"
        assert f"Set agent_name exactly to {domain!r}" in prompt.system
        assert f"include only the {domain!r} domain payload" in prompt.system
        assert expected[domain][0] in prompt.system
        assert expected[domain][1] in prompt.system
        assert f"Agent name: {domain}" in prompt.user
        assert f"Domain payload: {domain}" in prompt.user


def test_prompt_builder_does_not_select_second_wave_sell_conditions():
    from kncompanyscraper.analysis.agent.output_schema import SpecialistAgentName

    with pytest.raises(ValueError, match="no first-wave specialist prompt"):
        SpecialistPromptBuilder().build(packet(), SpecialistAgentName.SELL_CONDITIONS)


def test_parse_failure_is_recorded_and_does_not_raise():
    artifacts = Artifacts()
    runner = ShadowSpecialistRunner(
        Model(lambda prompt: "not-json"),
        artifacts,
        specialists=("management_credibility",),
    )

    result = runner.run(packet(), run_id="company-analysis-8")

    assert result.results[0].status == "failed"
    assert result.results[0].artifact_ids == (1,)
    assert "Invalid specialist-output JSON" in result.results[0].validation_errors[0]
    assert artifacts.validation[0][1] == "rejected"


def test_accepted_specialist_artifact_is_reused_for_same_run_and_packet():
    artifacts = Artifacts()
    frozen = packet()
    run_id = "company-analysis-9"
    packet_hash = sha256(serialize_packet(frozen).encode()).hexdigest()
    raw = management_output(frozen, run_id).replace(
        '"placeholder"', json.dumps(packet_hash)
    )
    artifacts.saved.append(
        {
            "id": 91,
            "company_id": frozen.company_id,
            "content": raw,
            "metadata": {
                "analysis_mode": "specialist",
                "agent_name": "management_credibility",
                "run_id": run_id,
                "packet_hash": packet_hash,
                "validation_status": "accepted",
                "analysis_attempt": 1,
            },
        }
    )
    artifacts.get_specialist_artifacts_for_run = lambda company_id, run: artifacts.saved
    model = Model(lambda prompt: "not-called")
    result = ShadowSpecialistRunner(
        model, artifacts, specialists=("management_credibility",)
    ).run(frozen, run_id=run_id, packet_hash=packet_hash)

    assert result.results[0].artifact_ids == (91,)
    assert model.calls == 0
