import json
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.analysis.agent.agent_analysis_service import AgentAnalysisService
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.context_provenance import deterministic_context_sha256
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.analysis.agent.readiness import (
    AgentReadinessError,
    AgentReadinessGate,
)
from kncompanyscraper.analysis.agent.result_parser import StockAnalysisValidationError
from tests.test_agent_result_boundary import valid_response


def ready_candidate():
    return AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        full_results={
            "reverse_dcf": {"status": "available"},
            "valuation": {
                "ev_ebit_guardrail_low": 5.0,
                "ev_ebit_guardrail_high": 15.0,
            },
        },
        research_evidence={
            "documents": [{"source_id": "document:1"}],
            "ownership_liquidity": {
                "source_ids": ["liquidity:borsdata:42:2026-08-31:20d"]
            },
        },
    )


def qualitative_response() -> str:
    payload = json.loads(valid_response())
    payload.pop("scenario_bundles")
    payload.pop("forward_scenario_analysis")
    return json.dumps(payload)


def test_agent_analysis_service_routes_model_output_through_persistence_boundary():
    candidate = ready_candidate()
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
        output_text=qualitative_response(),
        usage={"total_tokens": 150},
    )
    boundary = MagicMock()
    boundary.validate_qualitative_response.return_value = "qualitative"
    boundary.persist_validated_result.return_value = "persisted"

    results = AgentAnalysisService(model_adapter, boundary, prompt_builder).analyze([candidate])

    assert results == ["persisted"]
    model_adapter.generate.assert_called_once_with(prompt)
    boundary.validate_qualitative_response.assert_called_once_with(
        qualitative_response(),
        candidate,
    )
    boundary.persist_validated_result.assert_called_once_with(
        "qualitative",
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
            "evidence_source_ids": [
                "document:1",
                "liquidity:borsdata:42:2026-08-31:20d",
            ],
            "deterministic_context_sha256": deterministic_context_sha256(candidate),
            "qualitative_raw_analysis_id": None,
            "qualitative_raw_analysis_ids": [],
            "qualitative_attempts": 1,
            "qualitative_validation_errors": [],
        },
    )


def test_agent_analysis_service_preserves_raw_response_before_validation():
    candidate = ready_candidate()
    prompt = AgentPrompt(system="policy", user="candidate")
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = prompt
    model_adapter = MagicMock()
    model_adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_123",
        model="gpt-5.6-sol",
        output_text=qualitative_response(),
        usage={},
    )
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = StockAnalysisValidationError(
        "invalid citation"
    )
    model_adapter.repair = None
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
    raw_metadata = raw_repository.save_stock_analysis_raw.call_args.kwargs["metadata"]
    assert raw_metadata["analysis_mode"] == "initial"
    assert raw_metadata["artifact_type"] == "model_response"
    raw_repository.update_raw_validation.assert_called_once_with(
        77,
        "rejected",
        "invalid citation",
    )


def test_agent_analysis_service_prepares_provenance_before_model_call():
    candidate = ready_candidate()
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = AgentPrompt(system="policy", user="candidate")
    model_adapter = MagicMock()

    with patch(
        "kncompanyscraper.analysis.agent.agent_analysis_service.deterministic_context_sha256",
        side_effect=TypeError("bad deterministic context"),
    ), pytest.raises(TypeError, match="bad deterministic context"):
        AgentAnalysisService(
            model_adapter,
            MagicMock(),
            prompt_builder,
        ).analyze([candidate])

    model_adapter.generate.assert_not_called()


def test_agent_analysis_service_revalidates_stored_initial_response_without_model_call():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    model_adapter = MagicMock()
    boundary = MagicMock()
    boundary.persist_response.return_value = "persisted"
    raw_repository = MagicMock()
    raw_repository.get_latest_rejected_initial_analyses.return_value = {
        42: {
            "id": 77,
            "content": valid_response(),
            "created_by": "deepseek/deepseek-v4-pro",
            "metadata": {
                "analysis_mode": "initial",
                "validation_status": "rejected",
                "validation_error": "old error",
                "usage": {"total_tokens": 150},
            },
        }
    }

    results = AgentAnalysisService(
        model_adapter,
        boundary,
        MagicMock(),
        raw_response_repository=raw_repository,
    ).revalidate_rejected([candidate])

    assert results == ["persisted"]
    model_adapter.generate.assert_not_called()
    boundary.persist_response.assert_called_once_with(
        valid_response(),
        candidate,
        created_by="deepseek/deepseek-v4-pro",
        metadata={"usage": {"total_tokens": 150}, "raw_analysis_id": 77},
    )
    raw_repository.update_raw_validation.assert_called_once_with(77, "accepted")


def test_readiness_gate_exposes_stable_blockers_for_incomplete_packet():
    candidate = AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "unavailable",
                "missing_information": ["stock price is older than 7 days"],
            },
            "valuation": {},
        },
    )

    assessment = AgentReadinessGate().assess(candidate)

    assert assessment.status == "evidence_blocked"
    assert [blocker.code for blocker in assessment.blockers] == [
        "primary_evidence_missing",
    ]
    assert [limitation.code for limitation in assessment.limitations] == [
        "stock_price_stale",
        "historical_terminal_multiple_range_unavailable",
    ]


def test_agent_analysis_service_blocks_entire_batch_before_prompt_or_model_call():
    blocked = AgentCandidate(1, 42, "TEST", "Testbolaget")
    prompt_builder = MagicMock()
    model_adapter = MagicMock()

    with pytest.raises(AgentReadinessError, match="primary_evidence_missing"):
        AgentAnalysisService(
            model_adapter,
            MagicMock(),
            prompt_builder,
        ).analyze([ready_candidate(), blocked])

    prompt_builder.build.assert_not_called()
    model_adapter.generate.assert_not_called()


def test_agent_analysis_service_skips_scenarios_when_inputs_are_limited():
    candidate = ready_candidate()
    prompt = AgentPrompt(system="policy", user="candidate")
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = prompt
    model_adapter = MagicMock()
    model_adapter.generate.return_value = OpenAIModelResponse(
        response_id="local-1",
        model="codex-exec/gpt-5.6-luna",
        output_text=qualitative_response(),
        usage={},
    )
    boundary = MagicMock()
    boundary.validate_qualitative_response.return_value = "qualitative"
    boundary.persist_validated_result.return_value = "persisted"
    scenario_authoring = MagicMock()

    result = AgentAnalysisService(
        model_adapter,
        boundary,
        prompt_builder,
        scenario_authoring_service=scenario_authoring,
    ).analyze([candidate])

    assert result == ["persisted"]
    scenario_authoring.author.assert_not_called()
    boundary.persist_validated_result.assert_called_once()


def test_local_adapter_repairs_semantic_boundary_rejection():
    candidate = ready_candidate()
    prompt = AgentPrompt(system="policy", user="candidate")
    first = OpenAIModelResponse("local-1", "local-model", "first", {})
    repaired = OpenAIModelResponse("local-2", "local-model", "repaired", {})
    model_adapter = MagicMock(max_repair_attempts=1)
    model_adapter.generate.return_value = first
    model_adapter.repair.return_value = repaired
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = [
        StockAnalysisValidationError("unknown source"),
        "qualitative",
    ]
    boundary.persist_validated_result.return_value = "persisted"
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.side_effect = [71, 72]

    result = AgentAnalysisService(
        model_adapter,
        boundary,
        MagicMock(build=MagicMock(return_value=prompt)),
        raw_response_repository=raw_repository,
    ).analyze([candidate])

    assert result == ["persisted"]
    model_adapter.repair.assert_called_once_with(prompt, "first", "unknown source")
    assert raw_repository.update_raw_validation.call_args_list[0].args == (
        71,
        "rejected",
        "unknown source",
    )
    assert raw_repository.update_raw_validation.call_args_list[-1].args == (
        72,
        "accepted",
    )


def test_local_adapter_repairs_latest_stored_rejection():
    candidate = ready_candidate()
    prompt = AgentPrompt(system="policy", user="candidate")
    repaired = OpenAIModelResponse("local-2", "local-model", "repaired", {})
    model_adapter = MagicMock(max_repair_attempts=1)
    model_adapter.repair.return_value = repaired
    boundary = MagicMock()
    boundary.validate_qualitative_response.return_value = "qualitative"
    boundary.persist_validated_result.return_value = "persisted"
    raw_repository = MagicMock()
    raw_repository.get_latest_rejected_initial_analyses.return_value = {
        candidate.company_id: {
            "id": 71,
            "content": "first",
            "metadata": {"validation_error": "unknown source"},
        }
    }
    raw_repository.save_stock_analysis_raw.return_value = 72
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = prompt

    result = AgentAnalysisService(
        model_adapter,
        boundary,
        prompt_builder,
        raw_response_repository=raw_repository,
    ).repair_rejected([candidate])

    assert result == ["persisted"]
    model_adapter.repair.assert_called_once_with(prompt, "first", "unknown source")
    metadata = boundary.persist_validated_result.call_args.kwargs["metadata"]
    assert metadata["repaired_from_raw_analysis_id"] == 71
    assert metadata["raw_analysis_id"] == 72


def test_readiness_gate_marks_property_method_unsupported():
    candidate = ready_candidate()
    candidate.ranking_model = "property"

    assessment = AgentReadinessGate().assess(candidate)

    assert assessment.status == "method_unsupported"
    assert assessment.blockers[0].code == "forward_method_unsupported"


@pytest.mark.parametrize(
    ("missing_information", "expected_code"),
    [
        (["latest stock price unavailable"], "stock_price_missing"),
        (
            ["stock price and report currencies differ"],
            "valuation_currency_mismatch",
        ),
        (["latest report unavailable"], "reverse_dcf_unavailable"),
    ],
)
def test_readiness_gate_classifies_reverse_dcf_blockers(
    missing_information,
    expected_code,
):
    candidate = ready_candidate()
    candidate.full_results["reverse_dcf"] = {
        "status": "unavailable",
        "missing_information": missing_information,
    }

    assessment = AgentReadinessGate().assess(candidate)

    assert assessment.status == "ready"
    assert expected_code in [item.code for item in assessment.limitations]


def test_readiness_gate_allows_analysis_without_terminal_multiple_history():
    candidate = ready_candidate()
    candidate.full_results["valuation"] = {
        "ev_ebit_guardrail_low": None,
        "ev_ebit_guardrail_high": None,
    }

    assessment = AgentReadinessGate().assess(candidate)

    assert assessment.status == "ready"
    assert not assessment.blockers
    assert [item.code for item in assessment.limitations] == [
        "historical_terminal_multiple_range_unavailable"
    ]


def test_readiness_gate_reports_ownership_and_liquidity_subsection_statuses():
    candidate = ready_candidate()
    candidate.research_evidence["ownership_liquidity"] = {
        "liquidity": {"status": "available"},
        "ownership": {"status": "stale"},
    }

    assessment = AgentReadinessGate().assess(candidate)

    assert assessment.liquidity_status == "available"
    assert assessment.ownership_status == "stale"


def test_ownership_evidence_does_not_rescue_missing_fundamental_evidence():
    candidate = AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        research_evidence={
            "ownership_liquidity": {
                "source_ids": ["liquidity:borsdata:42:2026-08-31:20d"],
                "liquidity": {"status": "available"},
                "ownership": {"status": "unavailable"},
            }
        },
    )

    assessment = AgentReadinessGate().assess(candidate)

    assert assessment.status == "evidence_blocked"
    assert assessment.blockers[0].code == "primary_evidence_missing"
