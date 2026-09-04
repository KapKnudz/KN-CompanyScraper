from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from kncompanyscraper import config
from kncompanyscraper.analysis.agent.packet_measurement import measure_adapter_input
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.logger import get_logger


logger = get_logger(__name__)


class CodexExecError(RuntimeError):
    def __init__(self, message: str, *, code: str, metadata: dict):
        self.code = code
        self.metadata = dict(metadata)
        super().__init__(message[:512])


@dataclass(frozen=True)
class CodexExecModelResponse:
    response_id: str
    model: str
    output_text: str
    usage: dict
    input_measurement: dict


class CodexExecAdapter:
    REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
    max_repair_attempts = 1

    def __init__(
        self,
        *,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str = "high",
        timeout_seconds: int = 900,
        codex_binary: str = "codex",
        run_func=None,
        working_directory: Path | None = None,
        provider_character_limit: int | None = None,
        warning_threshold_characters: int | None = None,
    ):
        if reasoning_effort not in self.REASONING_EFFORTS:
            raise ValueError(
                f"Unsupported Codex reasoning effort: {reasoning_effort!r}"
            )
        if timeout_seconds < 1:
            raise ValueError("Codex timeout must be at least 1 second")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.codex_binary = codex_binary
        self.run_func = run_func or subprocess.run
        self.working_directory = working_directory or Path.cwd()
        self.provider_character_limit = (
            config.CODEX_LOCAL_INPUT_CHARACTER_LIMIT
            if provider_character_limit is None
            else provider_character_limit
        )
        self.warning_threshold_characters = (
            config.CODEX_LOCAL_INPUT_WARNING_THRESHOLD
            if warning_threshold_characters is None
            else warning_threshold_characters
        )
        if self.provider_character_limit < 1:
            raise ValueError("Codex character limit must be at least 1")
        if self.warning_threshold_characters < 1:
            raise ValueError("Codex warning threshold must be at least 1")

    def generate(self, prompt) -> CodexExecModelResponse:
        if prompt.output_schema is None:
            raise ValueError("Codex local analysis requires an output schema")

        adapter_input = self._input(prompt)
        input_measurement = self._input_measurement(prompt, adapter_input)
        if prompt.packet_measurement is not None:
            measurement = prompt.packet_measurement
            logger.info(
                "Agent packet diagnostics: bytes=%s characters=%s documents=%s "
                "token_estimate=%s section_sizes=%s",
                measurement.get("byte_count"),
                measurement.get("character_count"),
                measurement.get("document_count"),
                measurement.get("token_estimate"),
                measurement.get("section_sizes", {}),
            )
        if input_measurement["character_count"] >= self.warning_threshold_characters:
            logger.warning(
                "Local Codex input is near its character limit: characters=%s "
                "warning_threshold=%s provider_limit=%s headroom=%s",
                input_measurement["character_count"],
                self.warning_threshold_characters,
                self.provider_character_limit,
                input_measurement["remaining_character_headroom"],
            )
        if input_measurement["character_count"] > self.provider_character_limit:
            raise CodexExecError(
                "input_too_large: local Codex adapter input exceeds the provider "
                f"character limit ({input_measurement['character_count']} > "
                f"{self.provider_character_limit})",
                code="input_too_large",
                metadata=input_measurement,
            )
        logger.info(
            "Running local Codex model %s (%s reasoning) for %s",
            self.model,
            self.reasoning_effort,
            prompt.schema_name,
        )
        with tempfile.TemporaryDirectory(prefix="kncompanyscraper-codex-") as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = temp_path / "output-schema.json"
            output_path = temp_path / "response.json"
            schema_path.write_text(
                json.dumps(prompt.output_schema, ensure_ascii=False),
                encoding="utf-8",
            )
            command = [
                self.codex_binary,
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--model",
                self.model,
                "--config",
                f'model_reasoning_effort="{self.reasoning_effort}"',
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--color",
                "never",
                "--json",
                "--cd",
                str(self.working_directory),
                "-",
            ]
            try:
                completed = self.run_func(
                    command,
                    input=adapter_input,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CodexExecError(
                    "timeout: local Codex execution exceeded its configured timeout",
                    code="timeout",
                    metadata=input_measurement,
                ) from exc
            except OSError as exc:
                raise CodexExecError(
                    "codex_execution_failed: local Codex process could not be started: "
                    + _bounded_detail(str(exc), adapter_input),
                    code="codex_execution_failed",
                    metadata=input_measurement,
                ) from exc

            if completed.returncode != 0:
                error_code = _event_code(completed) or "codex_execution_failed"
                raise CodexExecError(
                    f"{error_code}: local Codex exited {completed.returncode}: "
                    f"{_bounded_detail(_event_detail(completed), adapter_input)}",
                    code=error_code,
                    metadata={
                        **input_measurement,
                        **_event_identifiers(completed),
                    },
                )
            if not output_path.exists():
                raise CodexExecError(
                    "missing_response: Codex local execution produced no final response",
                    code="missing_response",
                    metadata=input_measurement,
                )
            output_text = output_path.read_text(encoding="utf-8").strip()
            if not output_text:
                raise CodexExecError(
                    "empty_response: Codex local execution produced an empty response",
                    code="empty_response",
                    metadata=input_measurement,
                )

        logger.info("Local Codex completed %s", prompt.schema_name)

        usage = _event_usage(completed)
        if not usage:
            usage = {
                "input_tokens_estimate": input_measurement["token_estimate"],
                "usage_source": "estimated",
            }

        return CodexExecModelResponse(
            response_id=(
                f"codex-exec-{_event_identifiers(completed).get('response_id')}"
                if _event_identifiers(completed).get("response_id")
                else f"codex-exec-{uuid4()}"
            ),
            model=f"codex-exec/{self.model}",
            output_text=output_text,
            usage=usage,
            input_measurement=input_measurement,
        )

    def repair(self, prompt, previous_output: str, validation_error: str):
        return self.generate(
            AgentPrompt(
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
        )

    def _input_measurement(self, prompt, adapter_input: str) -> dict:
        packet_measurement = prompt.packet_measurement or {}
        prefix = (
            "Analyze only the supplied packet. Do not inspect the filesystem or use tools. "
            "Return only the JSON object required by the supplied output schema.\n\n"
        )
        policy_heading = "# Analyst policy\n\n"
        packet_heading = "\n\n# Analysis packet\n\n"
        return measure_adapter_input(
            adapter_input,
            document_count=packet_measurement.get("document_count", 0),
            section_sizes={
                "adapter_instructions": len(prefix),
                "system": len(policy_heading) + len(prompt.system),
                "user": len(packet_heading) + len(prompt.user),
            },
            provider_character_limit=self.provider_character_limit,
            warning_threshold_characters=self.warning_threshold_characters,
        )

    @staticmethod
    def _input(prompt) -> str:
        return (
            "Analyze only the supplied packet. Do not inspect the filesystem or use tools. "
            "Return only the JSON object required by the supplied output schema.\n\n"
            "# Analyst policy\n\n"
            f"{prompt.system}\n\n"
            "# Analysis packet\n\n"
            f"{prompt.user}"
        )


def _json_events(stdout) -> list[dict]:
    events = []
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _event_usage(completed) -> dict:
    for event in _json_events(getattr(completed, "stdout", "")):
        usage = event.get("usage")
        if event.get("type") == "turn.completed" and isinstance(usage, dict):
            return usage
    return {}


def _event_identifiers(completed) -> dict:
    for event in _json_events(getattr(completed, "stdout", "")):
        identifier = (
            event.get("response_id")
            or event.get("turn_id")
            or event.get("thread_id")
            or event.get("session_id")
        )
        if identifier:
            return {"response_id": str(identifier)}
    return {}


def _event_code(completed) -> str | None:
    for event in _json_events(getattr(completed, "stdout", "")):
        if event.get("type") not in {"error", "turn.failed", "turn.completed"}:
            continue
        error = event.get("error") if isinstance(event.get("error"), dict) else event
        code = error.get("code") or error.get("codex_error_code")
        if code:
            return str(code)
    return None


def _event_detail(completed) -> str:
    for event in _json_events(getattr(completed, "stdout", "")):
        if event.get("type") not in {"error", "turn.failed"}:
            continue
        error = event.get("error") if isinstance(event.get("error"), dict) else event
        detail = error.get("message") or error.get("detail")
        if detail:
            return str(detail)
    return getattr(completed, "stderr", "") or getattr(completed, "stdout", "") or ""


def _bounded_detail(detail: str, adapter_input: str) -> str:
    detail = str(detail or "").splitlines()[0].strip()
    sensitive_values = [adapter_input]
    sensitive_values.extend(
        line.strip()
        for line in adapter_input.splitlines()
        if len(line.strip()) >= 8
    )
    for sensitive in sensitive_values:
        if sensitive:
            detail = detail.replace(sensitive, "[prompt omitted]")
    return " ".join(detail.split())[:240] or "provider returned no diagnostic detail"
