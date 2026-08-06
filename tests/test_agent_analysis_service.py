from unittest.mock import MagicMock

from kncompanyscraper.analysis.agent.agent_analysis_service import AgentAnalysisService
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from tests.test_agent_result_boundary import valid_response


def test_agent_analysis_service_routes_model_output_through_persistence_boundary():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    prompt = AgentPrompt(system="policy", user="candidate")
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
            "openai_response_id": "resp_123",
            "usage": {"total_tokens": 150},
        },
    )
