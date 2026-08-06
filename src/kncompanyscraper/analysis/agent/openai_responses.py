from dataclasses import dataclass

import requests

from kncompanyscraper import config
from kncompanyscraper.analysis.agent.output_schema import stock_analysis_json_schema


class OpenAIResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIModelResponse:
    response_id: str
    model: str
    output_text: str
    usage: dict


class OpenAIResponsesAdapter:
    BASE_URL = "https://api.openai.com/v1/responses"
    REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        request_func=None,
    ):
        self.api_key = api_key or config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for agent analysis")

        self.model = model or config.OPENAI_MODEL
        self.reasoning_effort = reasoning_effort or config.OPENAI_REASONING_EFFORT
        if self.reasoning_effort not in self.REASONING_EFFORTS:
            raise ValueError(f"Unsupported OpenAI reasoning effort: {self.reasoning_effort!r}")
        self.max_output_tokens = (
            max_output_tokens if max_output_tokens is not None else config.OPENAI_MAX_OUTPUT_TOKENS
        )
        if self.max_output_tokens < 1:
            raise ValueError("OpenAI max output tokens must be at least 1")
        self.request_func = request_func or requests.post

    def generate(self, prompt) -> OpenAIModelResponse:
        response = self.request_func(
            self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": [
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                "reasoning": {"effort": self.reasoning_effort},
                "max_output_tokens": self.max_output_tokens,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "stock_analysis",
                        "strict": True,
                        "schema": stock_analysis_json_schema(),
                    }
                },
                "store": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "completed":
            raise OpenAIResponseError(
                f"OpenAI response {payload.get('id', '<unknown>')} ended with status "
                f"{payload.get('status')!r}"
            )

        output_text = self._extract_output_text(payload)
        return OpenAIModelResponse(
            response_id=payload["id"],
            model=payload.get("model") or self.model,
            output_text=output_text,
            usage=payload.get("usage") or {},
        )

    @staticmethod
    def _extract_output_text(payload: dict) -> str:
        texts: list[str] = []
        for item in payload.get("output") or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if content.get("type") == "refusal":
                    raise OpenAIResponseError(
                        f"OpenAI refused the analysis: {content.get('refusal', 'unspecified refusal')}"
                    )
                if content.get("type") == "output_text":
                    texts.append(content.get("text") or "")

        output_text = "".join(texts)
        if not output_text:
            raise OpenAIResponseError("OpenAI response contained no output text")
        return output_text
