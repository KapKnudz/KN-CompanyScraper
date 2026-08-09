from dataclasses import dataclass

import requests

from kncompanyscraper import config


class DeepSeekResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepSeekModelResponse:
    response_id: str
    model: str
    output_text: str
    usage: dict


class DeepSeekChatAdapter:
    BASE_URL = "https://api.deepseek.com/chat/completions"
    REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        request_func=None,
    ):
        self.api_key = api_key or config.DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek agent analysis")

        self.model = model or config.DEEPSEEK_MODEL
        self.reasoning_effort = reasoning_effort or config.DEEPSEEK_REASONING_EFFORT
        if self.reasoning_effort not in self.REASONING_EFFORTS:
            raise ValueError(f"Unsupported DeepSeek reasoning effort: {self.reasoning_effort!r}")
        self.max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else config.DEEPSEEK_MAX_OUTPUT_TOKENS
        )
        if self.max_output_tokens < 1:
            raise ValueError("DeepSeek max output tokens must be at least 1")
        self.request_func = request_func or requests.post

    def generate(self, prompt) -> DeepSeekModelResponse:
        response = self.request_func(
            self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                "thinking": {"type": "enabled"},
                "reasoning_effort": self.reasoning_effort,
                "max_tokens": self.max_output_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=300,
        )
        response.raise_for_status()
        payload = response.json()

        choices = payload.get("choices") or []
        if not choices:
            raise DeepSeekResponseError("DeepSeek response contained no choices")
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            raise DeepSeekResponseError(
                f"DeepSeek response {payload.get('id', '<unknown>')} ended with finish reason "
                f"{choice.get('finish_reason')!r}"
            )
        output_text = (choice.get("message") or {}).get("content") or ""
        if not output_text.strip():
            raise DeepSeekResponseError("DeepSeek response contained no output text")

        model = payload.get("model") or self.model
        return DeepSeekModelResponse(
            response_id=payload["id"],
            model=f"deepseek/{model}",
            output_text=output_text,
            usage=payload.get("usage") or {},
        )
