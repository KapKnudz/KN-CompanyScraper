import pytest

from kncompanyscraper.analysis.agent.openai_responses import (
    OpenAIResponseError,
    OpenAIResponsesAdapter,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.analysis.agent.output_schema import stock_analysis_json_schema
from tests.test_agent_result_boundary import valid_response


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def completed_payload():
    return {
        "id": "resp_123",
        "status": "completed",
        "model": "gpt-5.6-sol",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": valid_response()}],
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    }


def test_json_schema_is_strict_and_requires_all_contract_fields():
    schema = stock_analysis_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["verdict"]["enum"] == [
        "reject",
        "watch",
        "latent_case",
        "activated_case",
    ]
    assert schema["properties"]["case_horizon_months"]["type"] == ["integer", "null"]


def test_adapter_requests_strict_structured_output_without_api_storage():
    captured = {}

    def request(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeHTTPResponse(completed_payload())

    adapter = OpenAIResponsesAdapter(
        api_key="test-key",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=4000,
        request_func=request,
    )
    result = adapter.generate(AgentPrompt(system="policy", user="candidate"))

    assert result.response_id == "resp_123"
    assert result.output_text == valid_response()
    assert captured["json"]["input"] == [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "candidate"},
    ]
    assert captured["json"]["reasoning"] == {"effort": "medium"}
    assert captured["json"]["max_output_tokens"] == 4000
    assert captured["json"]["text"]["format"]["strict"] is True
    assert captured["json"]["store"] is False
    assert captured["timeout"] == 120


def test_adapter_uses_prompt_specific_output_schema():
    captured = {}

    def request(url, **kwargs):
        captured.update(kwargs)
        return FakeHTTPResponse(completed_payload())

    adapter = OpenAIResponsesAdapter(api_key="test-key", request_func=request)
    custom_schema = {"type": "object", "properties": {}, "additionalProperties": False}
    adapter.generate(
        AgentPrompt(
            system="policy",
            user="candidate",
            output_schema=custom_schema,
            schema_name="thesis_update",
        )
    )

    assert captured["json"]["text"]["format"]["name"] == "thesis_update"
    assert captured["json"]["text"]["format"]["schema"] == custom_schema


def test_adapter_requires_api_key(monkeypatch):
    monkeypatch.setattr("kncompanyscraper.analysis.agent.openai_responses.config.OPENAI_API_KEY", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIResponsesAdapter(api_key=None)


def test_adapter_rejects_invalid_reasoning_effort():
    with pytest.raises(ValueError, match="reasoning effort"):
        OpenAIResponsesAdapter(api_key="test-key", reasoning_effort="extreme")

    with pytest.raises(ValueError, match="output tokens"):
        OpenAIResponsesAdapter(api_key="test-key", max_output_tokens=0)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"id": "resp_1", "status": "incomplete"}, "status 'incomplete'"),
        (
            {
                "id": "resp_2",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "Cannot comply"}],
                    }
                ],
            },
            "refused",
        ),
    ],
)
def test_adapter_rejects_incomplete_or_refused_responses(payload, message):
    adapter = OpenAIResponsesAdapter(
        api_key="test-key",
        request_func=lambda *args, **kwargs: FakeHTTPResponse(payload),
    )

    with pytest.raises(OpenAIResponseError, match=message):
        adapter.generate(AgentPrompt(system="policy", user="candidate"))
