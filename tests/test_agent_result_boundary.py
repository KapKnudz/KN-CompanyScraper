import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.output_schema import (
    BusinessModelProfile,
    CompanyFact,
    EvidenceCitation,
    ManagementClaimAssessment,
    StockAnalysisResult,
    ThesisCatalyst,
    TimingAssessment,
    ValuationScenario,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)
from tests.test_forward_scenario import valid_inputs


def valid_result() -> StockAnalysisResult:
    return StockAnalysisResult(
        company_id=42,
        ticker="TEST",
        company_name="Testbolaget",
        verdict="watch",
        confidence="medium",
        one_sentence_thesis="Evidence is incomplete.",
        reverse_dcf_expectation_assessment="unassessable",
        reverse_dcf_expectation_rationale="Reverse-DCF inputs are unavailable.",
        expected_return_components={
            "revenue_growth": None,
            "margin_change": None,
            "multiple_change": None,
            "balance_sheet_change": None,
            "dilution": None,
        },
        valuation_scenarios=[],
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


def test_parser_builds_nested_result_dataclasses():
    result = parse_stock_analysis_result(valid_response())

    assert result.verdict == "watch"
    assert result.valuation_scenarios == []
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
    repository.save_stock_analysis.assert_called_once()
    saved = repository.save_stock_analysis.call_args
    assert saved.args == (persisted.result,)
    assert saved.kwargs["created_by"] == "test-model"
    assert saved.kwargs["metadata"]["validation_version"] == (
        "agent-boundary-v15-readiness-status"
    )
    assert saved.kwargs["metadata"]["forward_scenario"]["status"] == (
        "insufficient_evidence"
    )
    assert persisted.result.insider_assessment == (
        "No insider transactions are available for the selected period. "
        "No inference can be made from their absence."
    )


def test_execution_boundary_normalizes_and_accepts_sourced_company_fact():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 103
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"financial": {"operating_margin": 0.08}},
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.company_fact_ledger.business_model = [
        CompanyFact(
            statement=" The company sells subscriptions. ",
            evidence_kind="fact",
            source_ids=["news:21"],
            source_date="2026-08-01",
            reporting_period="2026-Q2",
        )
    ]
    payload.company_fact_ledger.margins_and_operating_leverage = [
        CompanyFact(
            statement="Operating margin was 8%.",
            evidence_kind="fact",
            source_ids=["full_results.financial.operating_margin"],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.company_fact_ledger.business_model[0].statement == (
        "The company sells subscriptions."
    )
    assert persisted.result.company_fact_ledger.margins_and_operating_leverage[
        0
    ].source_ids == ["deterministic:financial:operating_margin"]


def test_execution_boundary_rejects_company_fact_without_evidence():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.company_fact_ledger.revenue_drivers = [
        CompanyFact("Growth will accelerate.", "analyst_inference", [])
    ]

    with pytest.raises(StockAnalysisValidationError, match="must cite evidence"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_caps_confidence_when_textual_evidence_is_absent():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 104
    candidate = AgentCandidate(rank=1, company_id=42, ticker="TEST", name="Testbolaget")
    payload = valid_result()
    payload.confidence = "high"
    payload.management_credibility_ledger = []

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.confidence == "low"
    assert persisted.result.confidence_limitations == [
        "No textual company reports or releases were supplied."
    ]


def test_execution_boundary_accepts_aggregate_operating_history_citation():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 100
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "operating_history": {
                    "three_year_revenue_cagr": 0.10,
                    "five_year_average_ebit_margin": 0.08,
                }
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            source_id="full_results.reverse_dcf.operating_history",
            claim="Three-year growth was 10% and the five-year margin averaged 8%.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == (
        "deterministic:reverse_dcf:operating_history"
    )


def test_execution_boundary_accepts_aggregate_normalization_citation():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 100
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "normalization": {
                    "confidence": "low",
                    "reasons": ["volatile cash flow"],
                }
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            source_id="full_results.reverse_dcf.normalization",
            claim="Normalization confidence is low.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == (
        "deterministic:reverse_dcf:normalization"
    )


def test_execution_boundary_accepts_aggregate_price_attribution_citation():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 102
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "price_fundamental_attribution": [
                    {"period": "3y", "price_cagr": 0.12}
                ]
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            source_id="full_results.reverse_dcf.price_fundamental_attribution",
            claim="The recent rerating exceeded fundamental growth.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == (
        "deterministic:reverse_dcf:price_fundamental_attribution"
    )


def test_execution_boundary_accepts_aggregate_reverse_dcf_missing_information():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 102
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "unavailable",
                "missing_information": ["latest stock price unavailable"],
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            source_id="full_results.reverse_dcf.missing_information",
            claim="The latest stock price is unavailable.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == (
        "deterministic:reverse_dcf:missing_information"
    )


def test_execution_boundary_accepts_supplied_insider_event_count_citation():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 101
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "insider_event_count": 0,
        },
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            source_id="research_evidence.insider_event_count",
            claim="No insider events were supplied.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == "research:insider_event_count"


def test_execution_boundary_accepts_supplied_insider_status_fact():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 101
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "insider_status": "unavailable",
        },
    )
    payload = valid_result()
    payload.company_fact_ledger.ownership_and_insiders = [
        CompanyFact(
            statement="Insider evidence is unavailable.",
            evidence_kind="fact",
            source_ids=["research_evidence.insider_status"],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.company_fact_ledger.ownership_and_insiders[0].source_ids == [
        "research:insider_status"
    ]


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


def test_execution_boundary_accepts_evidence_backed_thesis_card_sections():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 106
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "financial_history": {
                "annual_reports": [
                    {
                        "source_id": "financial:annual:2025-12-31",
                        "revenue": 100.0,
                    }
                ]
            }
        },
        research_evidence={
            "as_of": "2026-08-18",
            "documents": [{"source_id": "news:21"}],
        },
    )
    payload = valid_result()
    payload.evidence_as_of = "2026-08-18"
    payload.case_horizon_months = 36
    payload.business_model_profile = BusinessModelProfile(
        summary="The company combines product sales and service revenue.",
        revenue_model_types=["hybrid"],
        customer_types=["business"],
        recurring_revenue_profile="partial",
        pricing_power="unassessable",
        capital_intensity="moderate",
        operating_leverage="credible",
        circle_of_competence="inside",
        source_ids=["financial:annual:2025-12-31", "news:21"],
    )
    payload.timing_assessment = TimingAssessment(
        horizon_months=36,
        why_now="Management has started the stated efficiency program.",
        confidence="medium",
        source_ids=["news:21"],
        catalysts=[
            ThesisCatalyst(
                description="Efficiency program reaches the first milestone.",
                timing_window="0_12m",
                observable_confirmation="Reported operating costs grow slower than revenue.",
                status="in_progress",
                source_ids=["news:21"],
            )
        ],
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.business_model_profile.revenue_model_types == ["hybrid"]
    assert persisted.result.timing_assessment.catalysts[0].timing_window == "0_12m"


def test_execution_boundary_rejects_unsupported_business_model_source():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
    )
    payload = valid_result()
    payload.business_model_profile = BusinessModelProfile(
        summary="The company has recurring revenue.",
        revenue_model_types=["subscription"],
        recurring_revenue_profile="majority",
        source_ids=["future:99"],
    )

    with pytest.raises(StockAnalysisValidationError, match="thesis card cites unknown"):
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
    payload.valuation_scenarios = [
        ValuationScenario("base", 28.0, 0.41, ["Model-generated forward value"])
    ]

    with pytest.raises(StockAnalysisValidationError, match="valuation_scenarios must be empty"):
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


def test_execution_boundary_rejects_blocked_status_as_investment_verdict():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result().to_dict()
    payload["analysis_status"] = "evidence_blocked"

    with pytest.raises(StockAnalysisValidationError, match="analysis_status"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload), candidate, created_by="test-model"
        )


def test_execution_boundary_calculates_forward_scenarios_from_sourced_bundles():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 105
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "unavailable",
                "current_price": 10.0,
                "current_revenue": 100.0,
                "current_shares": 10.0,
                "current_net_debt": 0.0,
                "required_return": {
                    "baseline_profile": "slightly_cyclical",
                    "profiles": {
                        "slightly_cyclical": {"discount_rate": 0.12},
                    },
                },
            },
            "valuation": {
                "ev_ebit_guardrail_low": 5.0,
                "ev_ebit_guardrail_high": 15.0,
            },
        },
        research_evidence={
            "documents": [
                {"source_id": "news:21"},
                {"source_id": "report:2026-q2"},
            ]
        },
    )
    payload = valid_result()
    payload.forward_scenario_assumptions = list(valid_inputs().endpoints)

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.forward_scenario_analysis.status == "available"
    assert persisted.result.forward_scenario_analysis.result("base_low") is not None
    metadata = repository.save_stock_analysis.call_args.kwargs["metadata"]
    assert metadata["forward_scenario"]["required_return"] == 0.12
    assert metadata["forward_scenario"]["status"] == "available"


def test_execution_boundary_requires_unassessable_when_reverse_dcf_is_unavailable():
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
    payload.reverse_dcf_expectation_assessment = "plausible"

    with pytest.raises(StockAnalysisValidationError, match="must be assessed as unassessable"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_reverse_dcf_score_in_qualitative_rationale():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.reverse_dcf_expectation_rationale = "The reverse DCF score is 72/100."

    with pytest.raises(StockAnalysisValidationError, match="cannot use a numerical score"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_requires_activated_case_for_investable_output():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.portfolio_eligibility = "investable"
    payload.portfolio_reason_code = "investable"

    with pytest.raises(StockAnalysisValidationError, match="requires activated_case"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_allows_activated_case_excluded_from_portfolio():
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
                "expectation_curve": [{"revenue_growth": 0.10}],
                "implied_expectations": {"revenue_growth": {}},
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.verdict = "activated_case"
    payload.portfolio_reason_code = "liquidity"

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 104


def test_execution_boundary_requires_trigger_for_valuation_only_exclusion():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.portfolio_reason_code = "valuation_only"

    with pytest.raises(StockAnalysisValidationError, match="require a trigger"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_model_selected_risk_profile():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 103
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "discount_rate_sensitivities": {
                    "cyclical_or_other_risk": {
                        "implied_expectations": {
                            "revenue_growth": {
                                "source_id": (
                                    "valuation:reverse_dcf:cyclical_or_other_risk:"
                                    "revenue_growth"
                                )
                            }
                        },
                        "expectation_curve": [
                            {
                                "revenue_growth": 0.10,
                                "ebit_margin_expectation": {
                                    "status": "solved",
                                    "source_id": (
                                        "valuation:reverse_dcf:"
                                        "cyclical_or_other_risk:curve:"
                                        "+1000bp:ebit_margin"
                                    ),
                                    "implied_value": 0.22,
                                },
                            }
                        ],
                    }
                }
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.risk_profile = "cyclical_or_other_risk"
    payload.risk_profile_confidence = "medium"
    payload.risk_profile_evidence = ["news:21"]

    with pytest.raises(StockAnalysisValidationError, match="model-selected"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )

    repository.save_stock_analysis.assert_not_called()


def test_execution_boundary_accepts_completed_classifier_consensus():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 104
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "cyclicality_consensus": {
                "status": "complete",
                "risk_profile": "cyclical_or_other_risk",
                "consensus_strength": "majority",
                "evidence": [{"source_id": "news:21"}],
            },
            "reverse_dcf": {
                "status": "available",
                "expectation_curve": [{"revenue_growth": 0.10}],
                "discount_rate_sensitivities": {
                    "cyclical_or_other_risk": {"expectation_curve": []}
                },
            },
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.risk_profile = "cyclical_or_other_risk"
    payload.risk_profile_confidence = "medium"
    payload.risk_profile_evidence = ["news:21"]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.risk_profile == "cyclical_or_other_risk"


def test_completed_classifier_consensus_does_not_require_unavailable_dcf_sensitivity():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 105
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "cyclicality_consensus": {
                "status": "complete",
                "risk_profile": "cyclical_or_other_risk",
                "consensus_strength": "majority",
                "evidence": [{"source_id": "news:21"}],
            },
            "reverse_dcf": {
                "status": "unavailable",
                "discount_rate_sensitivities": {},
            },
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.risk_profile = "cyclical_or_other_risk"
    payload.risk_profile_confidence = "medium"
    payload.risk_profile_evidence = ["news:21"]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 105


def test_execution_boundary_rejects_unsupported_risk_profile_classification():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.risk_profile = "noncyclical_recurring"
    payload.risk_profile_evidence = ["news:21"]

    with pytest.raises(StockAnalysisValidationError, match="model-selected"):
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


def test_execution_boundary_accepts_insider_event_cited_in_fact_ledger():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 102
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
    payload.company_fact_ledger.ownership_and_insiders = [
        CompanyFact(
            statement="The CEO purchased shares.",
            evidence_kind="fact",
            source_ids=["insider:1"],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 102


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
    payload.portfolio_eligibility = "investable"
    payload.portfolio_reason_code = "investable"

    with pytest.raises(StockAnalysisValidationError, match="reverse-DCF expectations"):
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
                "price_date": "2026-08-09",
                "current_price": 10.0,
                "assumptions": {
                    "projection_years": 5,
                    "revenue_growth": 0.05,
                    "ebit_margin": 0.15,
                    "tax_rate": 0.21,
                    "discount_rate": 0.10,
                    "terminal_growth": 0.02,
                    "net_reinvestment_rate": 0.01,
                },
                "assumption_sources": {"discount_rate": "fixed return policy"},
                "implied_expectations": {
                    "revenue_growth": {
                        "status": "solved",
                        "source_id": "valuation:reverse_dcf:revenue_growth",
                        "lower_bound": -0.10,
                        "upper_bound": 0.30,
                        "implied_value": 0.08,
                        "modeled_price": 10.0,
                        "modeled_price_range": None,
                        "reason": None,
                    }
                },
                "warnings": ["terminal value is material"],
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.verdict = "activated_case"
    payload.portfolio_eligibility = "investable"
    payload.portfolio_reason_code = "investable"

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 102
    saved_metadata = repository.save_stock_analysis.call_args.kwargs["metadata"]
    assert saved_metadata["validation_version"] == "agent-boundary-v15-readiness-status"
    assert saved_metadata["valuation_provenance"] == {
        "status": "available",
        "reverse_dcf_policy_version": "reverse-dcf-v2",
        "price_date": "2026-08-09",
        "current_price": 10.0,
        "current_revenue": None,
        "current_shares": None,
        "current_net_debt": None,
        "assumptions": {
            "projection_years": 5,
            "revenue_growth": 0.05,
            "ebit_margin": 0.15,
            "tax_rate": 0.21,
            "discount_rate": 0.10,
            "terminal_growth": 0.02,
                "net_reinvestment_rate": 0.01,
                "reinvestment_return": None,
                "revenue_growth_fade_to": None,
                "ebit_margin_start": None,
        },
        "assumption_sources": {"discount_rate": "fixed return policy"},
        "normalized_fcf_margin": None,
        "normalization": None,
            "operating_history": None,
            "price_fundamental_attribution": [],
            "reinvestment_roic": None,
        "required_return": {
            "policy_version": None,
            "risk_free_rate": None,
            "risk_free_rate_date": None,
            "risk_free_rate_source": None,
            "equity_risk_premium": None,
            "market_cap": None,
            "size_bucket": None,
            "size_adjustment": None,
            "baseline_profile": None,
        },
        "discount_rate_profiles": {},
        "implied_expectations": {
            "revenue_growth": {
                "status": "solved",
                "source_id": "valuation:reverse_dcf:revenue_growth",
                "lower_bound": -0.10,
                "upper_bound": 0.30,
                "implied_value": 0.08,
                "modeled_price": 10.0,
                "modeled_price_range": None,
                "outside_direction": None,
                "required_value_hint": None,
                "reason": None,
            }
        },
        "expectation_curve": [],
        "discount_rate_sensitivities": {},
        "warnings": ["terminal value is material"],
    }


def test_execution_boundary_rejects_prose_upside_in_reverse_only_policy():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.one_sentence_thesis = "The setup offers potential 50%+ upside."

    with pytest.raises(StockAnalysisValidationError, match="prose upside"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


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
    payload.citations = [
        EvidenceCitation(
            "full_results.reverse_dcf.implied_expectations.ebit_margin",
            "The market-implied margin is deterministic.",
        ),
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert [citation.source_id for citation in persisted.result.citations] == [
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


def test_execution_boundary_normalizes_supplied_aggregate_and_insider_aliases():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 106
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"cyclicality_consensus": {"status": "incomplete"}},
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "insider_status": "unavailable",
        },
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "full_results.cyclicality_consensus",
            "The supplied classifier consensus is incomplete.",
        ),
        EvidenceCitation(
            "full_results.insider_status",
            "Insider evidence is unavailable.",
        ),
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert [citation.source_id for citation in persisted.result.citations] == [
        "deterministic:cyclicality_consensus",
        "research:insider_status",
    ]


def test_execution_boundary_normalizes_supplied_missing_information_alias():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 107
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "missing_information": ["No textual company reports are stored"],
        },
    )
    payload = valid_result()
    payload.company_fact_ledger.risks_and_disconfirming_evidence = [
        CompanyFact(
            statement="No textual company reports are stored.",
            evidence_kind="fact",
            source_ids=["research_evidence.missing_information"],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert (
        persisted.result.company_fact_ledger.risks_and_disconfirming_evidence[0].source_ids
        == ["research:missing_information"]
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
