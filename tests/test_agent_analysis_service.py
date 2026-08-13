from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_analysis_service import AgentAnalysisService
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from tests.test_agent_result_boundary import valid_response


def test_agent_analysis_service_routes_model_output_through_persistence_boundary():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    prompt = AgentPrompt(
        system="policy",
        user="candidate",
        policy_name="test-policy",
        policy_version="2.0.0",
        policy_sha256="abc123",
    )
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = prompt
    model_adapter = MagicMock()
    model_adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_123",
        model="gpt-5.6-sol",
        output_text=valid_response(),
        usage={"total_tokens": 150},
    )
    boundary = MagicMock()
    boundary.persist_response.return_value = "persisted"

    results = AgentAnalysisService(model_adapter, boundary, prompt_builder).analyze([candidate])

    assert results == ["persisted"]
    model_adapter.generate.assert_called_once_with(prompt)
    boundary.persist_response.assert_called_once_with(
        valid_response(),
        candidate,
        created_by="gpt-5.6-sol",
        metadata={
            "model_response_id": "resp_123",
            "usage": {"total_tokens": 150},
            "policy_name": "test-policy",
            "policy_version": "2.0.0",
            "policy_sha256": "abc123",
            "candidate_rank": 1,
            "evidence_as_of": None,
            "evidence_source_ids": [],
        },
    )


def test_agent_analysis_service_preserves_raw_response_before_validation():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    prompt = AgentPrompt(system="policy", user="candidate")
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = prompt
    model_adapter = MagicMock()
    model_adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_123",
        model="gpt-5.6-sol",
        output_text=valid_response(),
        usage={},
    )
    boundary = MagicMock()
    boundary.persist_response.side_effect = ValueError("invalid citation")
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.return_value = 77

    with pytest.raises(ValueError, match="invalid citation"):
        AgentAnalysisService(
            model_adapter,
            boundary,
            prompt_builder,
            raw_response_repository=raw_repository,
        ).analyze([candidate])

    raw_repository.save_stock_analysis_raw.assert_called_once()
    raw_repository.update_raw_validation.assert_called_once_with(
        77,
        "rejected",
        "invalid citation",
    )
