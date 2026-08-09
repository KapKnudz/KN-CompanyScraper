import pytest

from kncompanyscraper.analysis.agent.deepseek_chat import (
    DeepSeekChatAdapter,
    DeepSeekResponseError,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
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
        "id": "chatcmpl_123",
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": valid_response()},
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


def test_adapter_requests_json_output_and_thinking_mode():
    captured = {}

    def request(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeHTTPResponse(completed_payload())

    adapter = DeepSeekChatAdapter(
        api_key="test-key",
        model="deepseek-v4-pro",
        reasoning_effort="high",
        max_output_tokens=4000,
        request_func=request,
    )
    result = adapter.generate(AgentPrompt(system="policy", user="return json"))

    assert result.response_id == "chatcmpl_123"
    assert result.model == "deepseek/deepseek-v4-pro"
    assert result.output_text == valid_response()
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "return json"},
    ]
    assert captured["json"]["thinking"] == {"type": "enabled"}
    assert captured["json"]["reasoning_effort"] == "high"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["max_tokens"] == 4000
    assert captured["timeout"] == 300


def test_adapter_requires_api_key(monkeypatch):
    monkeypatch.setattr("kncompanyscraper.analysis.agent.deepseek_chat.config.DEEPSEEK_API_KEY", None)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekChatAdapter(api_key=None)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"id": "one", "choices": []}, "no choices"),
        (
            {
                "id": "two",
                "choices": [{"finish_reason": "length", "message": {"content": "{}"}}],
            },
            "finish reason 'length'",
        ),
        (
            {
                "id": "three",
                "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
            },
            "no output text",
        ),
    ],
)
def test_adapter_rejects_unusable_responses(payload, message):
    adapter = DeepSeekChatAdapter(
        api_key="test-key",
        request_func=lambda *args, **kwargs: FakeHTTPResponse(payload),
    )

    with pytest.raises(DeepSeekResponseError, match=message):
        adapter.generate(AgentPrompt(system="policy", user="return json"))
