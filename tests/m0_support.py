"""Synthetic support objects for the M0 behavioral baselines."""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

from kncompanyscraper.analysis.agent.codex_exec import CodexExecAdapter
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt


@dataclass(frozen=True)
class ModelCall:
    operation: str
    stage: str
    schema_name: str
    adapter_input: str
    previous_output: str | None = None
    validation_error: str | None = None


class ModelSpy:
    """A deterministic adapter double that counts calls by operation and stage."""

    max_repair_attempts = 1

    def __init__(self, responses: dict[str, Iterable[str]] | None = None):
        self._responses = {
            schema: deque(values) for schema, values in (responses or {}).items()
        }
        self.calls: list[ModelCall] = []

    def generate(self, prompt):
        return self._respond(prompt, operation="generate")

    def repair(self, prompt, previous_output, validation_error):
        repair_prompt = AgentPrompt(
            system=prompt.system,
            user=(
                f"{prompt.user}\n\n"
                "# Repair request\n\n"
                "The previous JSON response failed the local deterministic "
                f"boundary with this exact error:\n{validation_error}\n\n"
                "Return the complete corrected JSON object. Change only what "
                "is necessary to satisfy the error and the original policy. "
                "Do not invent evidence.\n\n"
                f"Previous JSON response:\n{previous_output}"
            ),
            policy_name=prompt.policy_name,
            policy_version=prompt.policy_version,
            policy_sha256=prompt.policy_sha256,
            output_schema=prompt.output_schema,
            schema_name=prompt.schema_name,
            packet_measurement=prompt.packet_measurement,
            contract_version=prompt.contract_version,
        )
        return self._respond(
            repair_prompt,
            operation="repair",
            previous_output=previous_output,
            validation_error=validation_error,
        )

    def queue(self, schema_name: str, *outputs: str) -> None:
        self._responses.setdefault(schema_name, deque()).extend(outputs)

    def count(self, *, stage: str | None = None, schema_name: str | None = None) -> int:
        return sum(
            (stage is None or call.stage == stage)
            and (schema_name is None or call.schema_name == schema_name)
            for call in self.calls
        )

    def counts_by_stage(self) -> dict[str, int]:
        counts = defaultdict(int)
        for call in self.calls:
            counts[call.stage] += 1
        return dict(counts)

    def counts_by_schema(self) -> dict[str, int]:
        counts = defaultdict(int)
        for call in self.calls:
            counts[call.schema_name] += 1
        return dict(counts)

    def _respond(
        self,
        prompt,
        *,
        operation: str,
        previous_output: str | None = None,
        validation_error: str | None = None,
    ) -> OpenAIModelResponse:
        schema_name = prompt.schema_name
        try:
            output_text = self._responses[schema_name].popleft()
        except (KeyError, IndexError) as exc:
            raise AssertionError(
                f"model spy has no queued response for schema {schema_name!r}"
            ) from exc
        stage = {
            "stock_analysis": "qualitative",
            "scenario_authoring": "scenario",
        }.get(schema_name, schema_name)
        self.calls.append(
            ModelCall(
                operation=operation,
                stage=stage,
                schema_name=schema_name,
                adapter_input=CodexExecAdapter._input(prompt),
                previous_output=previous_output,
                validation_error=validation_error,
            )
        )
        call_number = len(self.calls)
        return OpenAIModelResponse(
            response_id=f"m0-spy-{call_number}",
            model="model-spy",
            output_text=output_text,
            usage={"total_tokens": 1},
        )


def synthetic_msab_catalog_shape() -> dict:
    """Return private-text-free deterministic data with the live alias count."""
    return {
        "financial_history": {
            "annual": {
                year: {
                    "revenue": float(year),
                    "ebit": float(year) / 10,
                    "margins": [0.1, 0.2],
                }
                for year in range(1725, 2025)
            },
            "half_year_comparison": {"revenue_growth": 0.1, "ebit_growth": 0.2},
            "scenario_history": [
                {"revenue": 100.0, "ebit": 10.0},
                {"revenue": 110.0, "ebit": 12.0},
            ],
        },
        "peer_comparison": {
            company_id: {
                "name": f"Synthetic peer {company_id}",
                "metrics": [1.0, 2.0, 3.0, 4.0],
            }
            for company_id in range(1, 216)
        },
    }
