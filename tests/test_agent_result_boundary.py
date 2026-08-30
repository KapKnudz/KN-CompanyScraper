import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.output_schema import (
    AssessmentClaim,
    BusinessModelProfile,
    CompanyFact,
    EvidenceCitation,
    ManagementClaimAssessment,
    ManagementCredibilityCoverage,
    RevenueResilience,
    StockAnalysisResult,
    ThesisCatalyst,
    TimingAssessment,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.valuation.forward_scenario import ForwardScenarioEngine
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
        revenue_resilience=RevenueResilience(
            assessment="unassessable",
            limitations=["Revenue drivers and cash-flow history are incomplete."],
        ),
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
        management_credibility_coverage=ManagementCredibilityCoverage(
            eligible_claim_count=1,
            pending_claim_count=1,
        ),
        citations=[],
    )


def valid_response() -> str:
    return json.dumps(valid_result().to_dict())


def test_parser_builds_nested_result_dataclasses():
    result = parse_stock_analysis_result(valid_response())

    assert result.verdict == "watch"
    assert result.scenario_bundles == []
    assert result.management_credibility_ledger[0].result == "unverifiable"


def test_parser_migrates_legacy_pending_management_ledger_entries():
    payload = valid_result().to_dict()
    payload.pop("management_credibility_coverage")
    payload["management_credibility_ledger"][0].pop("claim_source_ids")
    payload["management_credibility_ledger"][0].pop("outcome_source_ids")

    result = parse_stock_analysis_result(json.dumps(payload))

    assert result.management_credibility_ledger[0].claim_source_ids == ["news:21"]
    assert result.management_credibility_ledger[0].outcome_source_ids == []
    assert result.management_credibility_coverage.pending_claim_count == 1


def test_parser_accepts_evidence_backed_mixed_revenue_resilience():
    payload = valid_result()
    payload.revenue_resilience = RevenueResilience(
        assessment="mixed",
        recurring_driver="A contractual service base renews annually.",
        variable_driver="Usage volume and project orders vary by quarter.",
        cash_flow_observation="Operating cash flow has been positive but uneven.",
        source_ids=["news:21"],
    )

    result = parse_stock_analysis_result(json.dumps(payload.to_dict()))

    assert result.revenue_resilience.assessment == "mixed"


def test_execution_boundary_rejects_assessable_resilience_without_evidence():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.revenue_resilience = RevenueResilience(
        assessment="variable",
        recurring_driver="No recurring driver is documented.",
        variable_driver="Orders vary.",
        cash_flow_observation="Cash flow varies.",
    )

    with pytest.raises(StockAnalysisValidationError, match="documentary evidence"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


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
        "agent-boundary-v20-thesis-v2"
    )
    assert saved.kwargs["metadata"]["forward_scenario"]["status"] == (
        "insufficient_evidence"
    )
    assert saved.kwargs["metadata"]["management_credibility"] == {
        "eligible_claim_count": 1,
        "assessed_claim_count": 0,
        "pending_claim_count": 1,
        "omitted_claim_count": 0,
        "omission_reasons": [],
    }
    assert persisted.result.insider_assessment == (
        "No insider transactions are available for the selected period. "
        "No inference can be made from their absence."
    )


def test_execution_boundary_persists_deterministic_h1_reconciliation_limitation():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 100
    limitation = (
        "Report document:11 states revenue=250 for 2025-H1, versus standardized "
        "history revenue=260 from financial:quarterly:2025-03-28, "
        "financial:quarterly:2025-06-28; standardized history remains the calculation source."
    )
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "financial_history": {
                "half_year_comparison": {"limitations": [limitation]}
            }
        },
        research_evidence={
            "documents": [
                {"source_id": "document:11"},
                {"source_id": "news:21"},
            ]
        },
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        valid_response(), candidate, created_by="test-model"
    )

    assert limitation in persisted.result.confidence_limitations
    assert repository.save_stock_analysis.call_args.kwargs["metadata"][
        "financial_reconciliation_limitations"
    ] == [limitation]


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
    payload.management_credibility_coverage = ManagementCredibilityCoverage()

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


def test_execution_boundary_accepts_structured_deterministic_source_paths():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 101
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "financial_history": {
                "half_year_comparison": {"latest_source_ids": []},
            },
            "insider": {"data_available": True},
            "reverse_dcf": {
                "required_return": {"required_return": 0.115},
                "expectation_curve": [],
            },
            "peer_comparison": {
                "target_metrics": {
                    "current_ev_ebit": {
                        "source_ids": ["peer:target:valuation:42:2026-08-28"]
                    }
                }
            },
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "full_results.financial_history.half_year_comparison",
            "The standardized H1 comparison is available.",
        ),
        EvidenceCitation(
            "full_results.insider",
            "Insider data is available.",
        ),
        EvidenceCitation(
            "full_results.reverse_dcf.required_return",
            "The deterministic hurdle is available.",
        ),
        EvidenceCitation(
            "full_results.reverse_dcf.expectation_curve",
            "The deterministic expectation curve is available.",
        ),
        EvidenceCitation(
            "peer:target:valuation:42:2026-08-28",
            "The peer target valuation is available.",
        ),
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert [citation.source_id for citation in persisted.result.citations] == [
        "deterministic:financial_history:half_year_comparison",
        "deterministic:insider",
        "deterministic:reverse_dcf:required_return",
        "deterministic:reverse_dcf:expectation_curve",
        "peer:target:valuation:42:2026-08-28",
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


def test_parser_rejects_model_generated_forward_scenario_result():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result().to_dict()
    payload["forward_scenario_analysis"] = {
        "status": "available",
        "policy_version": "model-authored",
        "bands": [],
        "methodology_flags": [],
        "warnings": [],
    }

    with pytest.raises(StockAnalysisValidationError, match="forward_scenario_analysis"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload), candidate, created_by="test-model"
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
                "price_currency": "SEK",
                "financial_currency": "SEK",
                "assumption_sources": {
                    "current_net_debt": "deterministic:financial:net_debt"
                },
                "required_return": {
                    "required_return": 0.115,
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
    payload.scenario_bundles = list(valid_inputs().bundles)

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.forward_scenario_analysis.status == "available"
    assert persisted.result.forward_scenario_analysis.result("base") is not None
    metadata = repository.save_stock_analysis.call_args.kwargs["metadata"]
    assert metadata["forward_scenario"]["required_return"] == 0.115
    assert metadata["forward_scenario"]["status"] == "available"
    bridge = next(
        item
        for item in metadata["forward_scenario"]["net_debt_bridges"]
        if item["case"] == "base"
    )
    assert bridge["current_net_debt_source_ids"] == [
        "deterministic:financial:net_debt"
    ]
    assert bridge["change_source_ids"] == ["report:2026-q2"]
    assert bridge["provenance_type"] == "not_applicable"
    assert bridge["reconciles"] is True
    assert bridge["current_shares"] == 10.0
    assert bridge["projected_shares"] == 10.0
    assert bridge["distributions_per_share"] == 0.0
    assert metadata["artifact_type"] == "validated_analysis"


def test_net_debt_bridge_uses_latest_r12_source_when_reverse_provenance_is_missing():
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "financial_history": {
                "latest_r12": {"source_id": "financial:r12:2026-06-30"},
            },
            "reverse_dcf": {
                "current_net_debt": 10.0,
                "current_shares": 10.0,
            },
        },
    )
    payload = valid_result()
    payload.scenario_bundles = list(valid_inputs().bundles)

    bridge = AgentExecutionBoundary._net_debt_bridges(payload, candidate)[0]

    assert bridge["current_net_debt_source_ids"] == [
        "financial:r12:2026-06-30"
    ]


def test_execution_boundary_passes_currency_mismatch_to_forward_engine():
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "current_price": 10.0,
                "current_revenue": 100.0,
                "current_shares": 10.0,
                "current_net_debt": 0.0,
                "price_currency": "SEK",
                "financial_currency": "EUR",
            },
            "valuation": {
                "ev_ebit_guardrail_low": 5.0,
                "ev_ebit_guardrail_high": 15.0,
            },
        },
    )
    payload = valid_result()
    payload.scenario_bundles = list(valid_inputs().bundles)

    result = ForwardScenarioEngine().analyze(
        AgentExecutionBoundary._forward_scenario_inputs(payload, candidate)
    )

    assert result.status == "insufficient_evidence"
    assert any("currency mismatch" in flag for flag in result.methodology_flags)
    assert result.bands == ()


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


def test_execution_boundary_requires_available_forward_scenario_for_investable_output():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "implied_expectations": {"revenue_growth": {}},
                "expectation_curve": [{"revenue_growth": 0.10}],
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.verdict = "activated_case"
    payload.portfolio_eligibility = "investable"
    payload.portfolio_reason_code = "investable"

    with pytest.raises(StockAnalysisValidationError, match="available forward scenario"):
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

    with pytest.raises(StockAnalysisValidationError, match="require claim_source_ids"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_assessed_management_claim_with_outcome_provenance():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 108
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [
                {"source_id": "news:21"},
                {"source_id": "news:22"},
            ]
        },
    )
    payload = valid_result()
    payload.management_credibility_ledger = [
        ManagementClaimAssessment(
            date="2025-Q2",
            claim="Margins will improve.",
            expected_timing="2026-H1",
            observed_outcome="Margins improved in the first half of 2026.",
            result="kept",
            source_ids=["news:21", "news:22"],
            claim_source_ids=["news:21"],
            outcome_source_ids=["news:22"],
        )
    ]
    payload.management_credibility_coverage = ManagementCredibilityCoverage(
        eligible_claim_count=1,
        assessed_claim_count=1,
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assessment = persisted.result.management_credibility_ledger[0]
    assert assessment.claim_source_ids == ["news:21"]
    assert assessment.outcome_source_ids == ["news:22"]
    assert repository.save_stock_analysis.call_args.kwargs["metadata"][
        "management_credibility"
    ]["assessed_claim_count"] == 1


def test_execution_boundary_rejects_assessed_management_claim_without_outcome_source():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_credibility_ledger = [
        ManagementClaimAssessment(
            date="2025-Q2",
            claim="Margins will improve.",
            expected_timing="2026-H1",
            observed_outcome="Margins improved.",
            result="kept",
            claim_source_ids=["news:21"],
        )
    ]
    payload.management_credibility_coverage = ManagementCredibilityCoverage(
        eligible_claim_count=1,
        assessed_claim_count=1,
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="require outcome_source_ids",
    ):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_requires_reasons_for_omitted_management_claims():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_credibility_coverage = ManagementCredibilityCoverage(
        eligible_claim_count=2,
        pending_claim_count=1,
        omitted_claim_count=1,
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="require omission_reasons",
    ):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_requires_structured_claims_for_management_assessment():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_assessment = "Management has improved cost discipline."

    with pytest.raises(StockAnalysisValidationError, match="structured management claims"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_section_owned_management_claim():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 105
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_assessment = "Management has improved cost discipline."
    payload.management_claims = [
        AssessmentClaim(
            statement="Management reduced operating costs in the latest report.",
            evidence_kind="fact",
            source_ids=["news:21"],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.management_claims[0].source_ids == ["news:21"]


def test_execution_boundary_requires_section_owned_insider_claim():
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
    payload = valid_result()
    payload.insider_assessment = "Insider buying is a positive signal."
    payload.citations = [EvidenceCitation("insider:1", "An insider purchased shares.")]

    with pytest.raises(StockAnalysisValidationError, match="structured insider claims"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_section_owned_insider_claim():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 106
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
    payload.insider_assessment = "Insider buying is a positive signal."
    payload.insider_claims = [
        AssessmentClaim(
            statement="An insider purchased shares during the lookback period.",
            evidence_kind="fact",
            source_ids=["insider:1"],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.insider_claims[0].source_ids == ["insider:1"]


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


def test_execution_boundary_accepts_noninvestable_activated_case_with_available_reverse_dcf():
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

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.analysis_id == 102
    saved_metadata = repository.save_stock_analysis.call_args.kwargs["metadata"]
    assert saved_metadata["validation_version"] == (
        "agent-boundary-v20-thesis-v2"
    )
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
            "market_cap": None,
            "size_bucket": None,
            "required_return": None,
            "source_date": None,
        },
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


def test_execution_boundary_normalizes_supplied_insider_alias():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 106
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"financial": {"gross_margin": 0.48}},
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "insider_status": "unavailable",
        },
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "full_results.financial.gross_margin",
            "The deterministic gross margin is 48%.",
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
        "deterministic:financial:gross_margin",
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
