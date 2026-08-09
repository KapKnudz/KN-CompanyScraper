import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.output_schema import (
    EvidenceCitation,
    ManagementClaimAssessment,
    StockAnalysisResult,
    ValuationScenario,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)


def valid_result() -> StockAnalysisResult:
    return StockAnalysisResult(
        company_id=42,
        ticker="TEST",
        company_name="Testbolaget",
        verdict="watch",
        confidence="medium",
        one_sentence_thesis="Evidence is incomplete.",
        expected_return_components={
            "revenue_growth": None,
            "margin_change": None,
            "multiple_change": None,
            "balance_sheet_change": None,
            "dilution": None,
        },
        valuation_scenarios=[
            ValuationScenario(
                label="base",
                implied_value_per_share=None,
                expected_return=None,
                assumptions=["Current evidence is insufficient"],
            )
        ],
        management_credibility_ledger=[
            ManagementClaimAssessment(
                date="2026-Q2",
                claim="Margins will improve.",
                expected_timing=None,
                observed_outcome=None,
                result="unverifiable",
                source_ids=["news:21"],
            )
        ],
        citations=[],
    )


def valid_response() -> str:
    return json.dumps(valid_result().to_dict())


def supplied_scenario(label, value_per_share, expected_return):
    return {
        "source_id": f"valuation:forward_dcf:{label}",
        "assumptions": {
            "projection_years": 5,
            "revenue_growth": 0.05,
            "ebit_margin": 0.15,
            "tax_rate": 0.21,
            "discount_rate": 0.10,
            "terminal_growth": 0.02,
            "net_reinvestment_rate": 0.0,
        },
        "assumption_sources": {
            "projection_years": "fixed policy horizon",
            "revenue_growth": "company history",
            "ebit_margin": "company history",
            "tax_rate": "fixed tax policy",
            "discount_rate": "fixed return policy",
            "terminal_growth": "fixed mature growth policy",
            "net_reinvestment_rate": "normalized company-implied rate",
        },
        "value_per_share": value_per_share,
        "expected_return": expected_return,
        "terminal_value_share": 0.70,
    }


def test_parser_builds_nested_result_dataclasses():
    result = parse_stock_analysis_result(valid_response())

    assert result.verdict == "watch"
    assert result.valuation_scenarios[0].label == "base"
    assert result.management_credibility_ledger[0].result == "unverifiable"


def test_parser_rejects_missing_and_unexpected_fields():
    payload = valid_result().to_dict()
    del payload["confidence"]
    payload["extra"] = True

    with pytest.raises(StockAnalysisValidationError, match="missing fields: confidence"):
        parse_stock_analysis_result(json.dumps(payload))


def test_parser_rejects_invalid_enum_and_non_finite_number():
    payload = valid_result().to_dict()
    payload["verdict"] = "buy"

    with pytest.raises(StockAnalysisValidationError, match="result.verdict"):
        parse_stock_analysis_result(json.dumps(payload))

    payload = valid_result().to_dict()
    payload["current_ebit_margin"] = float("nan")
    with pytest.raises(StockAnalysisValidationError, match="result.current_ebit_margin"):
        parse_stock_analysis_result(json.dumps(payload))


def test_execution_boundary_validates_identity_before_persisting():
    repository = MagicMock()
    candidate = AgentCandidate(rank=1, company_id=7, ticker="OTHER", name="Other")

    with pytest.raises(StockAnalysisValidationError, match="company_id"):
        AgentExecutionBoundary(repository).persist_response(
            valid_response(), candidate, created_by="test-model"
        )

    repository.save_stock_analysis.assert_not_called()


def test_execution_boundary_persists_valid_response():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 99
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="test",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        valid_response(),
        candidate,
        created_by="test-model",
        metadata={"prompt_version": 1},
    )

    assert persisted.analysis_id == 99
    repository.save_stock_analysis.assert_called_once_with(
        persisted.result,
        created_by="test-model",
        metadata={
            "prompt_version": 1,
            "validation_version": "agent-boundary-v6",
            "validation_status": "accepted",
            "deterministic_value_checks": [
                "scenario values are null because deterministic forward DCF is unavailable",
                "model-owned expected return components are null",
            ],
            "insider_checks": ["no-data insider assessment normalized"],
            "warnings": ["model insider assessment replaced because no events were supplied"],
        },
    )
    assert persisted.result.insider_assessment == (
        "No insider transactions are available for the selected period. "
        "No inference can be made from their absence."
    )


def test_execution_boundary_rejects_unknown_citation_source():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [EvidenceCitation("news:999", "Unsupported claim")]

    with pytest.raises(StockAnalysisValidationError, match="unknown evidence source"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )

    repository.save_stock_analysis.assert_not_called()


def test_execution_boundary_rejects_model_generated_valuation_arithmetic():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.valuation_scenarios[0].implied_value_per_share = 28.0
    payload.valuation_scenarios[0].expected_return = 0.41

    with pytest.raises(StockAnalysisValidationError, match="valuation scenario values"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )

    repository.save_stock_analysis.assert_not_called()


def test_execution_boundary_rejects_model_generated_return_components():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.expected_return_components["revenue_growth"] = 0.10

    with pytest.raises(StockAnalysisValidationError, match="expected return components"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_requires_insider_citation_when_events_are_supplied():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "insider_transactions": [{"source_id": "insider:1"}],
        },
    )

    with pytest.raises(StockAnalysisValidationError, match="must cite at least one"):
        AgentExecutionBoundary(repository).persist_response(
            valid_response(), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_cited_insider_events():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 101
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "insider_transactions": [{"source_id": "insider:1"}],
        },
    )
    payload = valid_result()
    payload.citations = [EvidenceCitation("insider:1", "The CEO purchased shares.")]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 101
    saved_metadata = repository.save_stock_analysis.call_args.kwargs["metadata"]
    assert saved_metadata["insider_checks"] == [
        "insider assessment references supplied events (1 available)"
    ]


def test_execution_boundary_requires_sources_for_management_ledger():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_credibility_ledger[0].source_ids = []

    with pytest.raises(StockAnalysisValidationError, match="require document source_ids"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_activated_case_without_deterministic_valuation():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"reverse_dcf": {"status": "unavailable"}},
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.verdict = "activated_case"

    with pytest.raises(StockAnalysisValidationError, match="forward valuation scenarios"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_activated_case_with_available_reverse_dcf():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 102
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "policy_version": "reverse-dcf-v2",
                "forward_policy_version": "forward-dcf-scenarios-v1",
                "price_date": "2026-08-09",
                "current_price": 10.0,
                "warnings": ["terminal value is material"],
                "forward_scenarios": {
                    "bear": supplied_scenario("bear", 8.0, -0.2),
                    "base": supplied_scenario("base", 12.0, 0.2),
                    "bull": supplied_scenario("bull", 16.0, 0.6),
                },
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.verdict = "activated_case"
    payload.valuation_scenarios = [
        ValuationScenario("bear", 8.0, -0.2, ["Historical downside"]),
        ValuationScenario("base", 12.0, 0.2, ["Current operations"]),
        ValuationScenario("bull", 16.0, 0.6, ["Historical upside"]),
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 102
    assert all(
        "source:" in assumption
        for scenario in persisted.result.valuation_scenarios
        for assumption in scenario.assumptions
    )
    saved_metadata = repository.save_stock_analysis.call_args.kwargs["metadata"]
    assert saved_metadata["validation_version"] == "agent-boundary-v6"
    assert saved_metadata["valuation_provenance"] == {
        "status": "available",
        "reverse_dcf_policy_version": "reverse-dcf-v2",
        "forward_dcf_policy_version": "forward-dcf-scenarios-v1",
        "price_date": "2026-08-09",
        "current_price": 10.0,
        "scenarios": {
            label: supplied_scenario(label, value, expected)
            for label, value, expected in (
                ("bear", 8.0, -0.2),
                ("base", 12.0, 0.2),
                ("bull", 16.0, 0.6),
            )
        },
        "warnings": ["terminal value is material"],
    }


def test_execution_boundary_rejects_prose_upside_not_in_forward_dcf():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "forward_scenarios": {
                    "base": supplied_scenario("base", 12.0, 0.2)
                },
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.valuation_scenarios[0] = ValuationScenario(
        "base", 12.0, 0.2, ["Current operations"]
    )
    payload.one_sentence_thesis = "The setup offers potential 50%+ upside."

    with pytest.raises(StockAnalysisValidationError, match="prose upside"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_reasonably_rounded_deterministic_upside():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 104
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "forward_scenarios": {
                    "base": supplied_scenario("base", 91.296192, 3.610919)
                },
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.valuation_scenarios[0] = ValuationScenario(
        "base", 91.296192, 3.610919, ["Current operations"]
    )
    payload.one_sentence_thesis = "The setup offers approximately 350% upside."

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 104


def test_execution_boundary_normalizes_deterministic_valuation_path_citations():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 103
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "forward_scenarios": {
                    "base": supplied_scenario("base", 12.0, 0.2)
                },
                "implied_expectations": {
                    "ebit_margin": {
                        "source_id": "valuation:reverse_dcf:ebit_margin"
                    }
                },
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.valuation_scenarios[0] = ValuationScenario(
        "base", 12.0, 0.2, ["Current operations"]
    )
    payload.citations = [
        EvidenceCitation(
            "full_results.reverse_dcf.forward_scenarios.base",
            "The base scenario value is deterministic.",
        ),
        EvidenceCitation(
            "full_results.reverse_dcf.implied_expectations.ebit_margin",
            "The market-implied margin is deterministic.",
        ),
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert [citation.source_id for citation in persisted.result.citations] == [
        "valuation:forward_dcf:base",
        "valuation:reverse_dcf:ebit_margin",
    ]


def test_execution_boundary_normalizes_resolvable_deterministic_metric_path():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 105
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"financial": {"gross_margin": 0.48}},
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "full_results.financial.gross_margin",
            "The deterministic gross margin is 48%.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == (
        "deterministic:financial:gross_margin"
    )


def test_execution_boundary_rejects_nonexistent_deterministic_metric_path():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"financial": {"gross_margin": 0.48}},
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "full_results.financial.invented_margin",
            "Unsupported metric.",
        )
    ]

    with pytest.raises(StockAnalysisValidationError, match="unknown evidence source"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


@pytest.mark.parametrize(
    "thesis",
    [
        "The conservative base case indicates value.",
        "The realistic base-case supports activation.",
        "The company requires no net reinvestment.",
        "No reinvestment is required in this business.",
    ],
)
def test_execution_boundary_rejects_misleading_scenario_characterization(thesis):
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.one_sentence_thesis = thesis

    with pytest.raises(StockAnalysisValidationError, match="scenario labels|reinvestment"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_buyback_as_unsupported_per_share_effect():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.valuation_scenarios[0].assumptions = [
        "The synthetic buyback reduces share count and lifts EPS."
    ]

    with pytest.raises(StockAnalysisValidationError, match="unsupported per-share effect"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )
