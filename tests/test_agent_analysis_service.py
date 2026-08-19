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
            "cyclicality_consensus": {"status": "complete"},
        },
        research_evidence={"documents": [{"source_id": "document:1"}]},
    )


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
            "evidence_source_ids": ["document:1"],
            "deterministic_context_sha256": deterministic_context_sha256(candidate),
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
    assert raw_repository.save_stock_analysis_raw.call_args.kwargs["metadata"]["analysis_mode"] == "initial"
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
        "stock_price_stale",
        "terminal_multiple_guardrail_unavailable",
        "risk_profile_incomplete",
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

    assert expected_code in [blocker.code for blocker in assessment.blockers]
