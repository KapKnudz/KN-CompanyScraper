import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.codex_exec import (
    CodexExecAdapter,
    CodexExecError,
)
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder
from tests.m0_support import synthetic_msab_catalog_shape


def test_codex_exec_uses_luna_high_read_only_and_structured_output(tmp_path):
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        schema_path = command[command.index("--output-schema") + 1]
        captured["schema"] = json.loads(open(schema_path, encoding="utf-8").read())
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    response = CodexExecAdapter(
        run_func=run,
        working_directory=tmp_path,
    ).generate(AgentPrompt(system="policy", user="packet", output_schema=schema))

    assert response.model == "codex-exec/gpt-5.6-luna"
    assert json.loads(response.output_text) == {"answer": "ok"}
    assert captured["command"][:2] == ["codex", "exec"]
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "read-only"
    assert captured["command"][captured["command"].index("--model") + 1] == "gpt-5.6-luna"
    assert 'model_reasoning_effort="high"' in captured["command"]
    assert captured["schema"] == schema
    assert "policy" in captured["input"]
    assert "packet" in captured["input"]
    assert response.input_measurement["input_sha256"] == sha256(
        captured["input"].encode("utf-8")
    ).hexdigest()


def test_codex_exec_logs_packet_measurement_before_call(tmp_path, caplog):
    captured = {}

    def run(command, **kwargs):
        captured.update(kwargs)
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with caplog.at_level("INFO"):
        CodexExecAdapter(run_func=run, working_directory=tmp_path).generate(
            AgentPrompt(
                system="policy",
                user="packet",
                output_schema={"type": "object"},
                packet_measurement={
                    "byte_count": 20,
                    "character_count": 18,
                    "document_count": 1,
                    "token_estimate": 5,
                    "section_sizes": {"research_evidence": 10},
                },
            )
        )

    assert "token_estimate=5" in caplog.text
    assert "section_sizes={'research_evidence': 10}" in caplog.text


def test_m0_model_spy_captures_exact_initial_and_repair_adapter_inputs(model_spy):
    prompt = AgentPrompt(
        system="synthetic policy",
        user="synthetic packet",
        output_schema={"type": "object"},
    )
    model_spy.queue("stock_analysis", '{"status":"rejected"}', '{"status":"ok"}')

    model_spy.generate(prompt)
    model_spy.repair(prompt, '{"status":"rejected"}', "synthetic validation error")

    initial, repair = model_spy.calls
    expected_repair_prompt = AgentPrompt(
        system=prompt.system,
        user=(
            f"{prompt.user}\n\n"
            "# Repair request\n\n"
            "The previous JSON response failed the local deterministic boundary "
            "with this exact error:\nsynthetic validation error\n\n"
            "Return the complete corrected JSON object. Change only what is "
            "necessary to satisfy the error and the original policy. Do not "
            "invent evidence.\n\n"
            'Previous JSON response:\n{"status":"rejected"}'
        ),
        output_schema=prompt.output_schema,
    )
    assert initial.adapter_input == CodexExecAdapter._input(prompt)
    assert repair.adapter_input == CodexExecAdapter._input(expected_repair_prompt)
    assert "# Repair request" in repair.adapter_input
    assert '{"status":"rejected"}' in repair.adapter_input
    assert "synthetic validation error" in repair.adapter_input
    assert repair.previous_output == '{"status":"rejected"}'
    assert repair.validation_error == "synthetic validation error"


def test_codex_exec_reports_nonzero_exit(tmp_path):
    adapter = CodexExecAdapter(
        run_func=lambda *args, **kwargs: SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="authentication required",
        ),
        working_directory=tmp_path,
    )

    with pytest.raises(CodexExecError, match="authentication required"):
        adapter.generate(
            AgentPrompt(
                system="policy",
                user="packet",
                output_schema={"type": "object"},
            )
        )


def test_codex_exec_preflights_oversized_input_before_subprocess_launch(tmp_path):
    launched = False
    marker = "PRIVATE DOCUMENT BODY " * 20

    def run(*args, **kwargs):
        nonlocal launched
        launched = True

    adapter = CodexExecAdapter(
        run_func=run,
        working_directory=tmp_path,
        provider_character_limit=100,
        warning_threshold_characters=80,
    )
    prompt = AgentPrompt(
        system="policy",
        user=marker,
        output_schema={"type": "object"},
    )

    with pytest.raises(CodexExecError, match="input_too_large") as raised:
        adapter.generate(prompt)

    assert launched is False
    assert raised.value.code == "input_too_large"
    assert raised.value.metadata["character_count"] > 100
    assert raised.value.metadata["character_count"] == len(
        CodexExecAdapter._input(prompt)
    )
    assert raised.value.metadata["provider_character_limit"] == 100
    assert marker not in str(raised.value)


def test_codex_exec_records_complete_input_measurements_for_initial_and_repair(
    tmp_path,
):
    def run(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    adapter = CodexExecAdapter(
        run_func=run,
        working_directory=tmp_path,
        provider_character_limit=10_000,
        warning_threshold_characters=9_000,
    )
    prompt = AgentPrompt(
        system="policy",
        user="packet",
        output_schema={"type": "object"},
        packet_measurement={"document_count": 3},
    )

    initial = adapter.generate(prompt)
    repaired = adapter.repair(prompt, "{\"answer\":\"bad\"}", "bad answer")

    assert initial.input_measurement["character_count"] == len(
        CodexExecAdapter._input(prompt)
    )
    assert initial.input_measurement["document_count"] == 3
    assert initial.input_measurement["provider_character_limit"] == 10_000
    assert repaired.input_measurement["character_count"] == len(
        CodexExecAdapter._input(
            AgentPrompt(
                system=prompt.system,
                user=(
                    f"{prompt.user}\n\n"
                    "# Repair request\n\n"
                    "The previous JSON response failed the local deterministic "
                    "boundary with this exact error:\nbad answer\n\n"
                    "Return the complete corrected JSON object. Change only what "
                    "is necessary to satisfy the error and the original policy. "
                    "Do not invent evidence.\n\n"
                    'Previous JSON response:\n{"answer":"bad"}'
                ),
                output_schema=prompt.output_schema,
                packet_measurement=prompt.packet_measurement,
            )
        )
    )
    assert repaired.input_measurement["character_count"] > initial.input_measurement[
        "character_count"
    ]


def test_codex_exec_preserves_exact_usage_event_and_uses_estimate_fallback(tmp_path):
    usage = {"input_tokens": 321, "output_tokens": 12, "total_tokens": 333}

    def run_with_usage(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "turn.completed", "usage": usage}) + "\n",
            stderr="",
        )

    prompt = AgentPrompt(system="policy", user="packet", output_schema={"type": "object"})
    exact = CodexExecAdapter(run_func=run_with_usage, working_directory=tmp_path).generate(prompt)
    assert exact.usage == usage

    def run_without_usage(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(returncode=0, stdout="not-json\n", stderr="")

    fallback = CodexExecAdapter(
        run_func=run_without_usage,
        working_directory=tmp_path,
    ).generate(prompt)
    assert fallback.usage == {
        "input_tokens_estimate": fallback.input_measurement["token_estimate"],
        "usage_source": "estimated",
    }


def test_codex_exec_error_does_not_echo_stdout_or_stderr_prompt_content(tmp_path):
    marker = "PRIVATE DOCUMENT BODY"

    adapter = CodexExecAdapter(
        run_func=lambda *args, **kwargs: SimpleNamespace(
            returncode=2,
            stdout=f"provider failed\n{marker}\n",
            stderr=f"provider failed\n{marker}\n",
        ),
        working_directory=tmp_path,
    )

    with pytest.raises(CodexExecError) as raised:
        adapter.generate(
            AgentPrompt(
                system="policy",
                user=marker,
                output_schema={"type": "object"},
            )
        )

    assert raised.value.code == "codex_execution_failed"
    assert len(str(raised.value)) <= 512
    assert marker not in str(raised.value)
    assert raised.value.metadata["character_count"] > 0


def test_codex_exec_retains_structured_error_code_and_session_id(tmp_path):
    adapter = CodexExecAdapter(
        run_func=lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=json.dumps(
                {
                    "type": "error",
                    "code": "provider_limit",
                    "message": "request rejected",
                    "thread_id": "thread_123",
                }
            ),
            stderr="",
        ),
        working_directory=tmp_path,
    )

    with pytest.raises(CodexExecError, match="provider_limit") as raised:
        adapter.generate(
            AgentPrompt(
                system="policy",
                user="packet",
                output_schema={"type": "object"},
            )
        )

    assert raised.value.code == "provider_limit"
    assert raised.value.metadata["response_id"] == "thread_123"


def test_codex_exec_warns_at_configured_threshold(tmp_path, caplog):
    def run(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with caplog.at_level("WARNING"):
        CodexExecAdapter(
            run_func=run,
            working_directory=tmp_path,
            provider_character_limit=10_000,
            warning_threshold_characters=1,
        ).generate(
            AgentPrompt(
                system="policy",
                user="packet",
                output_schema={"type": "object"},
            )
        )

    assert "near its character limit" in caplog.text


def test_codex_exec_msab_normal_prompt_reports_forty_percent_headroom(
    tmp_path,
):
    def run(command, **kwargs):
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"answer": "ok"}, output)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    candidate = AgentCandidate(
        rank=1,
        company_id=114,
        ticker="M0 B",
        name="Synthetic Software",
        full_results=synthetic_msab_catalog_shape(),
    )
    prompt = AgentPromptBuilder().build(candidate)
    response = CodexExecAdapter(
        run_func=run,
        working_directory=tmp_path,
    ).generate(prompt)

    measurement = response.input_measurement
    assert measurement["provider_character_limit"] == 1_048_576
    assert measurement["remaining_character_headroom"] >= 1_048_576 * 0.40


def test_codex_exec_validates_configuration():
    with pytest.raises(ValueError, match="reasoning effort"):
        CodexExecAdapter(reasoning_effort="extreme")
    with pytest.raises(ValueError, match="timeout"):
        CodexExecAdapter(timeout_seconds=0)
