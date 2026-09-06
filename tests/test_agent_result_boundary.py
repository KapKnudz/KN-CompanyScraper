import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.agent_packet import build_evidence_catalog
from kncompanyscraper.analysis.agent.output_schema import (
    AssessmentClaim,
    OwnershipBinding,
    OwnershipClaim,
    BusinessModelProfile,
    CompanyFact,
    DecisiveEvidence,
    EvidenceCitation,
    FalsifiableCase,
    ManagementClaimAssessment,
    ManagementCredibilityCoverage,
    MissingInformationItem,
    RevenueResilience,
    StockAnalysisResult,
    ActivationTriggerSpec,
    ThesisCatalyst,
    TimingAssessment,
    ThesisBreakTest,
)
from kncompanyscraper.models.stored_analysis import StoredAnalysisDocument
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_qualitative_stock_analysis_result,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.valuation.forward_scenario import ForwardScenarioEngine
from kncompanyscraper.analysis.valuation.forward_scenario import (
    ForwardScenarioAnalysis,
    ScenarioBandResult,
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


def qualitative_response(result: StockAnalysisResult) -> str:
    payload = result.to_dict()
    payload.pop("scenario_bundles")
    payload.pop("forward_scenario_analysis")
    return json.dumps(payload)


def test_parser_builds_nested_result_dataclasses():
    result = parse_stock_analysis_result(valid_response())

    assert result.verdict == "watch"
    assert result.scenario_bundles == []
    assert result.management_credibility_ledger[0].result == "unverifiable"


def test_parser_builds_falsifiable_case_decisive_evidence_and_break_tests():
    payload = valid_result()
    payload.case_horizon_months = 36
    payload.falsifiable_case = FalsifiableCase(
        statement=payload.one_sentence_thesis,
        falsification_test="Revenue remains below the cited baseline through 2028.",
        horizon_months=36,
        source_ids=["news:21"],
    )
    payload.strongest_confirming_evidence = DecisiveEvidence(
        statement="The current evidence supports observation.",
        why_it_matters="It establishes the baseline mechanism.",
        source_ids=["news:21"],
    )
    payload.thesis_break_tests = [
        ThesisBreakTest(
            break_type="revenue_or_demand",
            condition="Demand fails to recover.",
            observable_metric_or_event="Reported organic revenue",
            threshold_or_direction="Remains below the cited baseline",
            response="reassess",
            source_ids=["news:21"],
        )
    ]

    parsed = parse_stock_analysis_result(json.dumps(payload.to_dict()))

    assert parsed.falsifiable_case.horizon_months == 36
    assert parsed.strongest_confirming_evidence.source_ids == ["news:21"]
    assert parsed.thesis_break_tests[0].break_type == "revenue_or_demand"


def test_execution_boundary_rejects_duplicate_thesis_break_type():
    payload = valid_result()
    break_test = ThesisBreakTest(
        break_type="margin_or_execution",
        condition="The margin mechanism fails.",
        observable_metric_or_event="Reported EBIT margin",
        threshold_or_direction="Remains below the cited baseline",
        response="sell",
        source_ids=["news:21"],
    )
    payload.thesis_break_tests = [break_test, break_test]
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    with pytest.raises(StockAnalysisValidationError, match="duplicate thesis break type"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            qualitative_response(payload), candidate
        )


def test_execution_boundary_rejects_unreconciled_falsifiable_case():
    payload = valid_result()
    payload.falsifiable_case = FalsifiableCase(
        statement="A different thesis.",
        falsification_test="Revenue remains below the cited baseline.",
        horizon_months=36,
        source_ids=["news:21"],
    )
    payload.case_horizon_months = 36
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    with pytest.raises(StockAnalysisValidationError, match="must match one_sentence_thesis"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            qualitative_response(payload), candidate
        )


def test_supplemental_missing_information_does_not_cap_high_confidence():
    result = valid_result()
    result.confidence = "high"
    result.missing_information = ["Free-float data is unavailable."]
    result.missing_information_details = [
        MissingInformationItem(
            item="Free-float data is unavailable.",
            limitation_class="supplemental",
            impact="Execution capacity cannot be assessed, but the business case is unchanged.",
        )
    ]
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "expectation_curve": [{"revenue_growth": 0.10}],
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    parsed = AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
        qualitative_response(result), candidate
    )

    assert parsed.confidence == "high"


def test_core_missing_information_caps_high_confidence_at_medium():
    result = valid_result()
    result.confidence = "high"
    result.missing_information = ["Cash-flow normalization is unresolved."]
    result.missing_information_details = [
        MissingInformationItem(
            item="Cash-flow normalization is unresolved.",
            limitation_class="core",
            impact="The stated cash-generation mechanism cannot yet be verified.",
        )
    ]
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "expectation_curve": [{"revenue_growth": 0.10}],
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    boundary = AgentExecutionBoundary(MagicMock())
    parsed = boundary.validate_qualitative_response(qualitative_response(result), candidate)

    assert parsed.confidence == "medium"


def test_no_textual_evidence_caps_confidence_at_low():
    result = valid_result()
    result.confidence = "high"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "expectation_curve": [{"revenue_growth": 0.10}],
            }
        },
        research_evidence={},
    )

    parsed = AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
        qualitative_response(result), candidate
    )

    assert parsed.confidence == "low"


def test_latent_case_requires_subtype_and_structured_trigger():
    result = valid_result()
    result.verdict = "latent_case"

    with pytest.raises(StockAnalysisValidationError, match="latent_case_type"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            qualitative_response(result),
            AgentCandidate(
                rank=1,
                company_id=42,
                ticker="TEST",
                name="Testbolaget",
                research_evidence={"documents": [{"source_id": "news:21"}]},
            ),
        )


def test_latent_trigger_rejects_generic_two_report_wait():
    result = valid_result()
    result.verdict = "latent_case"
    result.latent_case_type = "operating"
    result.activation_trigger = "Wait for two strong reports."
    result.activation_trigger_spec = ActivationTriggerSpec(
        unresolved_claim="The operating recovery is durable.",
        observable_metric_or_event="Two strong reports",
        threshold_or_direction="Improvement",
        evidence_window="two reports",
        single_observation_sufficient=False,
        observation_requirement="Persistence needs to be demonstrated.",
    )

    with pytest.raises(StockAnalysisValidationError, match="company-specific metric"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            qualitative_response(result),
            AgentCandidate(
                rank=1,
                company_id=42,
                ticker="TEST",
                name="Testbolaget",
                research_evidence={"documents": [{"source_id": "news:21"}]},
            ),
        )


def coherence_result(verdict, *, subtype=None, low=0.10, high=0.12):
    result = valid_result()
    result.verdict = verdict
    result.latent_case_type = subtype
    if verdict == "latent_case":
        result.activation_trigger = "The price trigger is defined."
        result.activation_trigger_spec = ActivationTriggerSpec(
            unresolved_claim="The setup is attractive at a lower valuation.",
            observable_metric_or_event="Share price reaches the entry level.",
            threshold_or_direction="Price below the stated entry level.",
            evidence_window="One market observation.",
            single_observation_sufficient=True,
            observation_requirement="One observation resolves the price condition.",
        )
    result.reverse_dcf_expectation_assessment = "plausible"
    result.forward_scenario_analysis = ForwardScenarioAnalysis(
        status="available",
        policy_version="test",
        bands=(
            ScenarioBandResult(
                case="base",
                horizon_months=36,
                low_price=10,
                high_price=10,
                low_holding_value=10,
                high_holding_value=10,
                low_annualized_return=low,
                high_annualized_return=high,
            ),
        ),
    )
    return result


def coherence_candidate(required_return=0.10, assessment="available"):
    return AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": assessment,
                "required_return": {"required_return": required_return},
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )


@pytest.mark.parametrize(
    "low, should_raise",
    [(0.099, True), (0.10, False), (0.101, False)],
)
def test_activated_case_uses_base_lower_bound_return_hurdle(low, should_raise):
    result = coherence_result("activated_case", low=low, high=0.12)
    boundary = AgentExecutionBoundary(MagicMock())
    if should_raise:
        with pytest.raises(StockAnalysisValidationError, match="lower-bound"):
            boundary._validate_verdict_coherence(result, coherence_candidate())
    else:
        boundary._validate_verdict_coherence(result, coherence_candidate())


@pytest.mark.parametrize(
    "high, should_raise",
    [(0.099, True), (0.10, False), (0.101, False)],
)
def test_operating_latent_uses_base_upper_bound_return_hurdle(high, should_raise):
    result = coherence_result("latent_case", subtype="operating", low=0.02, high=high)
    boundary = AgentExecutionBoundary(MagicMock())
    if should_raise:
        with pytest.raises(StockAnalysisValidationError, match="upper-bound"):
            boundary._validate_verdict_coherence(result, coherence_candidate())
    else:
        boundary._validate_verdict_coherence(result, coherence_candidate())


def test_price_latent_coherence_error_exposes_deterministic_repair_diagnostic():
    result = coherence_result("latent_case", subtype="price", low=0.10, high=0.12)
    boundary = AgentExecutionBoundary(MagicMock())

    with pytest.raises(StockAnalysisValidationError) as raised:
        boundary._validate_verdict_coherence(result, coherence_candidate())

    assert raised.value.deterministic_output_diagnostic == {
        "type": "verdict_coherence",
        "verdict": "latent_case",
        "latent_case_type": "price",
        "base_annualized_return_range": [0.10, 0.12],
        "required_return": 0.10,
        "conflict": "price latent cannot claim economically sufficient current-price returns",
    }


def test_parser_supplies_missing_deterministic_scenario_fields():
    payload = valid_result().to_dict()
    payload.pop("scenario_bundles")
    payload.pop("forward_scenario_analysis")

    result = parse_stock_analysis_result(json.dumps(payload))

    assert result.scenario_bundles == []
    assert result.forward_scenario_analysis is None


def test_qualitative_boundary_accepts_thesis_without_calculating_or_persisting_scenarios():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    payload = valid_result().to_dict()
    payload.pop("scenario_bundles")
    payload.pop("forward_scenario_analysis")
    result = AgentExecutionBoundary(repository).validate_qualitative_response(
        json.dumps(payload), candidate
    )

    assert result.scenario_bundles == []
    assert result.forward_scenario_analysis is None
    repository.save_stock_analysis.assert_not_called()


def test_qualitative_boundary_defers_operating_latent_forward_scenario_checks():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "reverse_dcf": {
                "status": "available",
                "expectation_curve": [{"revenue_growth": 0.10}],
                "required_return": {"required_return": 0.10},
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.verdict = "latent_case"
    payload.latent_case_type = "operating"
    payload.activation_trigger = "EBIT margin confirms the operating recovery."
    payload.activation_trigger_spec = ActivationTriggerSpec(
        unresolved_claim="The operating recovery is durable.",
        observable_metric_or_event="EBIT margin in the FY 2026 report.",
        threshold_or_direction="EBIT margin remains above 12%.",
        evidence_window="FY 2026 report",
        single_observation_sufficient=True,
        observation_requirement="One annual observation resolves the durability question.",
    )
    payload.reverse_dcf_expectation_assessment = "plausible"
    payload.reverse_dcf_expectation_rationale = "The implied expectations are plausible."

    result = AgentExecutionBoundary(repository).validate_qualitative_response(
        qualitative_response(payload), candidate
    )

    assert result.verdict == "latent_case"
    assert result.latent_case_type == "operating"
    assert result.forward_scenario_analysis is None
    repository.save_stock_analysis.assert_not_called()


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


def test_execution_boundary_rejects_resilient_resilience_without_persistence_evidence():
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
        assessment="resilient",
        recurring_driver="Customers may return to the brand.",
        variable_driver="Product sales vary.",
        cash_flow_observation="Cash flow is available.",
        source_ids=["news:21"],
    )

    with pytest.raises(StockAnalysisValidationError, match="persistence"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_mixed_resilience_without_both_model_types():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.business_model_profile.revenue_model_types = ["product_sales"]
    payload.business_model_profile.recurring_revenue_profile = "partial"
    payload.revenue_resilience = RevenueResilience(
        assessment="mixed",
        recurring_driver="Contract renewals provide persistence.",
        variable_driver="Product sales vary.",
        cash_flow_observation="Cash flow is available.",
        source_ids=["news:21"],
    )

    with pytest.raises(StockAnalysisValidationError, match="model types"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_revenue_resilience_rejects_subscription_model_as_variable():
    result = valid_result()
    result.business_model_profile.revenue_model_types = ["subscription"]
    result.business_model_profile.recurring_revenue_profile = "majority"
    result.revenue_resilience = RevenueResilience(
        assessment="variable",
        recurring_driver="No contractual persistence is documented.",
        variable_driver="Usage orders vary.",
        cash_flow_observation="Cash flow varies.",
        source_ids=["news:21"],
    )

    with pytest.raises(StockAnalysisValidationError, match="recurring revenue model"):
        AgentExecutionBoundary._validate_revenue_resilience(result)


def test_licensing_does_not_by_itself_make_product_revenue_recurring():
    result = valid_result()
    result.business_model_profile.revenue_model_types = [
        "product_sales",
        "licensing",
    ]
    result.business_model_profile.recurring_revenue_profile = "none"
    result.revenue_resilience = RevenueResilience(
        assessment="variable",
        recurring_driver="No contractual persistence is documented.",
        variable_driver="Product sales volumes vary.",
        cash_flow_observation="Cash flow varies.",
        source_ids=["news:21"],
        variable_source_ids=["news:21"],
    )

    AgentExecutionBoundary._validate_revenue_resilience(result)


def test_qualitative_validation_returns_independent_violations_together():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    result = valid_result()
    result.management_assessment = "Management execution is improving."
    result.management_claims = []
    result.revenue_resilience = RevenueResilience(
        assessment="variable",
        recurring_driver="No contractual persistence is documented.",
        variable_driver="Product orders vary.",
        cash_flow_observation="Cash flow varies.",
    )

    with pytest.raises(StockAnalysisValidationError) as exc_info:
        AgentExecutionBoundary(repository).validate_qualitative_response(
            qualitative_response(result), candidate
        )

    message = str(exc_info.value)
    assert "management assessment requires structured management claims" in message
    assert "revenue resilience assessments require documentary evidence" in message


def test_qualitative_validation_aggregates_assessment_source_violations():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "source_ids": ["liquidity:borsdata:42:2026-09-03:20d"]
            },
        },
    )
    result = valid_result()
    result.management_claims = [
        AssessmentClaim("Revenue increased.", "fact", ["financial:annual:2025"])
    ]
    result.ownership_claims = [
        AssessmentClaim("A holder owns 15%.", "fact", ["news:21"])
    ]

    with pytest.raises(StockAnalysisValidationError) as exc_info:
        AgentExecutionBoundary(repository).validate_qualitative_response(
            qualitative_response(result), candidate
        )

    message = str(exc_info.value)
    assert "management claims must cite supplied documents" in message
    assert "ownership claims must cite supplied ownership/liquidity evidence" in message


def test_mixed_resilience_requires_separately_sourced_drivers():
    result = valid_result()
    result.business_model_profile.revenue_model_types = [
        "subscription",
        "product_sales",
    ]
    result.business_model_profile.recurring_revenue_profile = "partial"
    result.revenue_resilience = RevenueResilience(
        assessment="mixed",
        recurring_driver="Contract renewals provide persistence.",
        variable_driver="Product sales vary.",
        cash_flow_observation="Cash flow is available.",
        source_ids=["news:21"],
    )

    with pytest.raises(StockAnalysisValidationError, match="sourced recurring"):
        AgentExecutionBoundary._validate_revenue_resilience(result)


def test_multi_report_trigger_requires_named_persistence_risk():
    result = valid_result()
    result.activation_trigger_spec = ActivationTriggerSpec(
        unresolved_claim="The margin recovery is durable.",
        observable_metric_or_event="EBIT margin in the next two quarterly reports.",
        threshold_or_direction="Maintain at least 12%.",
        evidence_window="Q3 and Q4 2026 reports",
        single_observation_sufficient=False,
        observation_requirement="Two reports are needed to test whether the margin improvement persists beyond a temporary quarter.",
    )

    AgentExecutionBoundary._validate_activation_trigger(result)


def test_price_and_report_trigger_can_name_a_baseline_recheck_as_the_risk():
    result = valid_result()
    result.activation_trigger_spec = ActivationTriggerSpec(
        unresolved_claim="The current valuation becomes attractive without weakening the operating case.",
        observable_metric_or_event="EV/EBIT after the next regular financial report.",
        threshold_or_direction="EV/EBIT falls to 19.9x or lower.",
        evidence_window="One closing-price observation after the next regular financial report, with the operating baseline rechecked in that report.",
        single_observation_sufficient=False,
        observation_requirement="A valuation observation and the accompanying next regular financial report are both required; one price observation alone is insufficient because the operating baseline must be rechecked before activation.",
    )

    AgentExecutionBoundary._validate_activation_trigger(result)


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


def test_execution_boundary_normalizes_child_path_to_known_parent_source():
    full_results = {
        "reverse_dcf": {
            "operating_history": {"r12_ebit_margin_peak": 0.18},
        }
    }
    catalog = build_evidence_catalog(full_results, {})

    assert AgentExecutionBoundary._resolve_source_alias(
        "full_results.reverse_dcf.operating_history.r12_ebit_margin_peak",
        catalog,
        full_results,
        {},
    ) == "deterministic:reverse_dcf:operating_history"


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
        "agent-boundary-v23-ownership-source-contract"
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
    assert persisted.result.ownership_and_flow_assessment == (
        "Ownership and liquidity evidence are unavailable. "
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
            "full_results.peer_comparison",
            "The dated peer range is a separate valuation sanity check.",
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
        "deterministic:peer_comparison",
        "peer:target:valuation:42:2026-08-28",
    ]


def test_execution_boundary_accepts_source_ids_nested_in_scenario_history():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 102
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "financial_history": {
                "scenario_history": {
                    "source_ids": {
                        "r12_ebit_margin": ["financial:r12:2018-12-31"]
                    }
                }
            }
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "financial:r12:2018-12-31",
            "The historical margin summary includes the older R12 observation.",
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == "financial:r12:2018-12-31"


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


def test_execution_boundary_accepts_liquidity_evidence_source():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 106
    source_id = "liquidity:borsdata:42:2026-08-31:20d"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {"source_ids": [source_id]},
        },
    )
    payload = valid_result()
    payload.citations = [EvidenceCitation(source_id, "20-day ADTV proxy")]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == source_id


def test_parser_migrates_legacy_result_without_ownership_claims():
    payload = valid_result().to_dict()
    payload.pop("ownership_claims")

    result = parse_stock_analysis_result(json.dumps(payload))

    assert result.ownership_claims == []


def test_execution_boundary_requires_structured_ownership_claims():
    repository = MagicMock()
    source_id = "liquidity:borsdata:42:2026-08-31:20d"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {"source_ids": [source_id]},
        },
    )
    payload = valid_result()
    payload.ownership_and_flow_assessment = "The stored ADTV proxy is relevant."

    with pytest.raises(StockAnalysisValidationError, match="structured ownership claims"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_accepts_cited_liquidity_claim():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 107
    source_id = "liquidity:borsdata:42:2026-08-31:20d"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "source_ids": [source_id],
                "liquidity": {"status": "available", "adtv_20": 1_200_000},
                "ownership": {"status": "unavailable"},
            },
        },
    )
    payload = valid_result()
    payload.ownership_and_flow_assessment = "The 20-day ADTV proxy is 1.2 million."
    payload.ownership_claims = [
        AssessmentClaim(
            statement="The 20-day ADTV proxy is 1.2 million.",
            evidence_kind="fact",
            source_ids=[source_id],
        )
    ]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.ownership_claims[0].source_ids == [source_id]


def test_execution_boundary_drops_unsupported_ownership_claim_when_supported_remains():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 108
    source_id = "liquidity:borsdata:42:2026-08-31:20d"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "source_ids": [source_id],
                "liquidity": {"status": "available", "adtv_20": 1_200_000},
                "ownership": {"status": "unavailable"},
            },
        },
    )
    payload = valid_result()
    payload.ownership_and_flow_assessment = "Liquidity is available; news is secondary."
    payload.ownership_claims = [
        AssessmentClaim(
            statement="The 20-day ADTV proxy is 1.2 million.",
            evidence_kind="fact",
            source_ids=[source_id],
        ),
        AssessmentClaim(
            statement="A news release discusses ownership.",
            evidence_kind="fact",
            source_ids=["news:21"],
        ),
        AssessmentClaim(
            statement="An unsourced ownership observation.",
            evidence_kind="analyst_inference",
            source_ids=[],
        ),
    ]

    with pytest.raises(StockAnalysisValidationError, match="news:21"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_precise_unsupported_ownership_claim():
    repository = MagicMock()
    source_id = "liquidity:borsdata:42:2026-08-31:20d"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "source_ids": [source_id],
                "liquidity": {"status": "available", "adtv_20": 1_200_000},
                "ownership": {"status": "unavailable"},
            },
        },
    )
    payload = valid_result()
    payload.ownership_and_flow_assessment = "Free float is 35%."
    payload.ownership_claims = [
        AssessmentClaim(
            statement="Free float is 35%.",
            evidence_kind="fact",
            source_ids=[source_id],
        )
    ]

    with pytest.raises(StockAnalysisValidationError, match="deterministic field"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


def test_execution_boundary_rejects_unknown_ownership_claim_source():
    repository = MagicMock()
    source_id = "liquidity:borsdata:42:2026-08-31:20d"
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {"source_ids": [source_id]},
        },
    )
    payload = valid_result()
    payload.ownership_and_flow_assessment = "Liquidity is relevant."
    payload.ownership_claims = [
        AssessmentClaim(
            statement="Liquidity is relevant.",
            evidence_kind="analyst_inference",
            source_ids=["liquidity:borsdata:42:2026-08-30:20d"],
        )
    ]

    with pytest.raises(StockAnalysisValidationError, match="ownership_claims") as raised:
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )

    assert "Liquidity is relevant." in str(raised.value)
    assert "changing a documentary citation into an ownership citation is not permitted" in str(
        raised.value
    )


def _v3_qualitative_response(result):
    payload = result.to_dict()
    for key in (
        "one_sentence_thesis", "falsifiable_case", "business_model_profile",
        "margin_expansion_case", "timing_assessment", "confidence_limitations",
        "company_fact_ledger", "reconsideration_trigger", "activation_trigger",
        "latent_case_type", "activation_trigger_spec", "activation_trigger_evidence",
        "reverse_dcf_expectation_rationale", "revenue_resilience", "peak_margin_evidence",
        "management_assessment", "management_claims", "management_credibility_ledger",
        "management_credibility_coverage", "ownership_and_flow_assessment",
        "insider_assessment", "insider_claims", "confirming_evidence",
        "disconfirming_evidence", "thesis_break_conditions",
        "strongest_confirming_evidence", "strongest_disconfirming_evidence",
        "thesis_break_tests", "missing_information", "missing_information_details",
        "citations", "scenario_bundles", "forward_scenario_analysis",
    ):
        payload.pop(key, None)
    def claim(claim_id, domain="risk", predicate="source_gap", value=None, source_ids=None, limitation_codes=None):
        return {"claim_id": claim_id, "domain": domain, "predicate": predicate,
                "value": value, "source_ids": source_ids or [],
                "limitation_codes": limitation_codes or []}
    payload["structured_conclusions"] = {
        "headline_case": {"case_ref": "fundamental_case", "horizon_months": 36,
            "revenue_mechanism": "organic_growth", "profitability_state": "profitable",
            "expectation_refs": [], "break_condition": claim("break")},
        "falsifiable_case": {"case_ref": "fundamental_case", "horizon_months": 36,
            "baseline_refs": [], "falsification": claim("falsification", source_ids=["news:21"])},
        "evidence_claims": [], "break_tests": [], "management_claims": [],
        "management_ledger": [], "company_facts": [], "business_model_facts": [],
        "margin_facts": [], "timing_facts": [], "limitation_codes": ["missing_revenue_evidence"],
        "strongest_confirming_evidence": {
            "claim": claim("confirming", "revenue", "observation", "supported", ["news:21"]),
            "relevance_code": "baseline_support",
        },
        "strongest_disconfirming_evidence": {
            "claim": claim("disconfirming", "risk", "observation", "unsupported", ["news:21"]),
            "relevance_code": "downside_exposure",
        },
        "thesis_break_tests": [
            {
                "break_type": break_type,
                "condition_code": condition_code,
                "observable_metric_code": metric_code,
                "threshold_code": "below_10_percent",
                "response": "reassess",
                "source_ids": ["news:21"],
                "limitation_codes": [],
            }
            for break_type, condition_code, metric_code in (
                ("revenue_or_demand", "revenue_decline", "revenue"),
                ("margin_or_execution", "margin_decline", "ebit_margin"),
                ("balance_sheet_or_dilution", "debt_increase", "net_debt"),
                ("management_credibility", "management_miss", "management_guidance"),
                ("valuation_overshoot", "valuation_expansion", "valuation"),
                ("superior_evidence_or_opportunity", "superior_evidence", "new_evidence"),
            )
        ],
        "missing_information_details": [
            {
                "item_code": "missing_revenue_evidence",
                "limitation_class": "core",
                "impact_code": "conclusion_limited",
            }
        ],
        "reconsideration_trigger": None,
        "trigger_evidence": [],
        "trigger": None,
        "revenue_resilience": claim("resilience", "revenue", "assessment", "unassessable"),
        "reverse_dcf_assessment": "unassessable",
    }
    return json.dumps(payload)


def test_v3_schema_rejects_legacy_free_text_ownership_claims():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    result.ownership_claims = [
        AssessmentClaim(
            statement="The founder owns 20%.",
            evidence_kind="fact",
            source_ids=["news:21"],
        )
    ]

    with pytest.raises(StockAnalysisValidationError, match="missing fields:"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            qualitative_response(result),
            AgentCandidate(
                rank=1,
                company_id=42,
                ticker="TEST",
                name="Testbolaget",
                research_evidence={"documents": [{"source_id": "news:21"}]},
            ),
        )


def test_v3_schema_rejects_free_text_structured_conclusion_values():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["structured_conclusions"]["headline_case"]["case_ref"] = (
        "The founder owns 20%."
    )
    payload["structured_conclusions"]["headline_case"]["break_condition"][
        "value"
    ] = "The founder owns 20%."

    with pytest.raises(StockAnalysisValidationError, match="must match"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            json.dumps(payload),
            AgentCandidate(
                rank=1,
                company_id=42,
                ticker="TEST",
                name="Testbolaget",
                research_evidence={"documents": [{"source_id": "news:21"}]},
            ),
        )


def test_v3_company_fact_cannot_carry_free_text_ownership_conclusion():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["structured_conclusions"]["company_facts"] = [
        {
            "claim_id": "capital_allocation_fact",
            "fact_code": "cash_balance",
            "domain": "balance_sheet",
            "predicate": "observation",
            "value": "The founder owns 20%.",
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]

    with pytest.raises(StockAnalysisValidationError, match="must match"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            json.dumps(payload),
            AgentCandidate(
                rank=1,
                company_id=42,
                ticker="TEST",
                name="Testbolaget",
                research_evidence={"documents": [{"source_id": "news:21"}]},
            ),
        )


def test_v3_projection_preserves_management_and_capital_facts():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    structured = payload["structured_conclusions"]
    structured["company_facts"] = [
        {
            "claim_id": "capital_allocation_fact",
            "fact_code": "cash_balance",
            "domain": "balance_sheet",
            "predicate": "observation",
            "value": 1250,
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]
    structured["management_claims"] = [
        {
            "claim_id": "management_experience",
            "fact_code": "tenure",
            "domain": "management",
            "predicate": "observation",
            "value": 12,
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]
    structured["management_ledger"] = [
        {
            "claim_id": "management_execution_history",
            "fact_code": "execution",
            "domain": "management",
            "predicate": "outcome",
            "value": "confirmed",
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]
    structured["business_model_facts"] = [
        {
            "claim_id": "business_model_observation",
            "domain": "business_model",
            "predicate": "observation",
            "value": "supported",
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]
    structured["margin_facts"] = [
        {
            "claim_id": "margin_observation",
            "domain": "margin",
            "predicate": "observation",
            "value": "improving",
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]
    structured["timing_facts"] = [
        {
            "claim_id": "timing_observation",
            "domain": "timing",
            "predicate": "observation",
            "value": "observed",
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]
    structured["falsifiable_case"]["falsification"]["claim_id"] = (
        "founder_owns_20_percent"
    )

    persisted = AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
        json.dumps(payload),
        AgentCandidate(
            rank=1,
            company_id=42,
            ticker="TEST",
            name="Testbolaget",
            research_evidence={"documents": [{"source_id": "news:21"}]},
        ),
    )

    serialized = persisted.to_dict()
    assert "company_fact_ledger" not in serialized
    assert "management_claims" not in serialized
    assert serialized["structured_conclusions"]["company_facts"][0]["value"] == 1250

    summary = StoredAnalysisDocument(
        {"content": serialized, "metadata": {}}
    ).thesis_summary
    assert summary["company_fact_ledger"]["balance_sheet_and_capital_allocation"][0][
        "statement"
    ] == "balance_sheet cash balance: 1250"
    assert summary["management_claims"][0]["statement"] == (
        "management tenure: 12"
    )
    assert summary["company_fact_ledger"]["business_model"][0]["statement"] == (
        "business_model observation: supported"
    )
    assert summary["business_model_profile"]["summary"] == (
        "business_model observation: supported"
    )
    assert summary["margin_expansion_case"]["mechanism"] == (
        "margin observation: improving"
    )
    assert summary["timing_assessment"]["why_now"] == (
        "timing observation: observed"
    )
    assert "founder_owns_20_percent" not in summary["falsifiable_case"][
        "falsification_test"
    ]
    assert persisted.management_credibility_ledger[0].claim == (
        "management execution: confirmed"
    )
    assert persisted.strongest_confirming_evidence.why_it_matters == (
        "It establishes the current baseline for the case."
    )
    assert len(persisted.thesis_break_tests) == 6
    assert persisted.missing_information_details[0].limitation_class == "core"


def test_v3_structured_trigger_projects_activation_contract():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["structured_conclusions"]["trigger"] = {
        "claim_id": "operating_trigger",
        "trigger_type": "operating",
        "unresolved_claim_code": "margin_recovery",
        "observable_metric_code": "ebit_margin",
        "threshold_code": "above_10_percent",
        "evidence_window": "0_12m",
        "single_observation_sufficient": True,
        "observation_requirement": "single_observation",
        "source_ids": ["news:21"],
        "limitation_codes": [],
    }

    parsed = parse_qualitative_stock_analysis_result(json.dumps(payload))

    assert parsed.latent_case_type == "operating"
    assert parsed.activation_trigger == "Resolve margin recovery when ebit margin above 10 percent."
    assert parsed.activation_trigger_spec.observable_metric_or_event == "ebit margin"
    assert parsed.activation_trigger_spec.threshold_or_direction == "above 10 percent"
    AgentExecutionBoundary._validate_activation_trigger(parsed)


def test_v3_requires_decisive_evidence_when_sources_are_citable():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["structured_conclusions"]["strongest_confirming_evidence"] = None
    payload["structured_conclusions"]["strongest_disconfirming_evidence"] = None

    with pytest.raises(StockAnalysisValidationError, match="typed decisive evidence"):
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            json.dumps(payload),
            AgentCandidate(
                rank=1,
                company_id=42,
                ticker="TEST",
                name="Testbolaget",
                research_evidence={"documents": [{"source_id": "news:21"}]},
            ),
        )


def test_v3_trigger_rejects_ownership_like_code():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["structured_conclusions"]["trigger"] = {
        "claim_id": "operating_trigger",
        "trigger_type": "operating",
        "unresolved_claim_code": "founder_owns_20_percent",
        "observable_metric_code": "ebit_margin",
        "threshold_code": "above_10_percent",
        "evidence_window": "0_12m",
        "single_observation_sufficient": True,
        "observation_requirement": "single_observation",
        "source_ids": [],
        "limitation_codes": [],
    }

    with pytest.raises(StockAnalysisValidationError, match="must match"):
        parse_qualitative_stock_analysis_result(json.dumps(payload))


def test_v3_typed_facts_reject_cross_section_domain_codes():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(result))
    payload["structured_conclusions"]["company_facts"] = [
        {
            "claim_id": "misrouted_fact",
            "fact_code": "tenure",
            "domain": "management",
            "predicate": "observation",
            "value": 12,
            "source_ids": ["news:21"],
            "limitation_codes": [],
        }
    ]

    with pytest.raises(StockAnalysisValidationError, match="must match"):
        parse_qualitative_stock_analysis_result(json.dumps(payload))


def test_operating_latent_rejects_price_only_structured_trigger():
    result = valid_result()
    result.verdict = "latent_case"
    result.latent_case_type = "operating"
    result.activation_trigger = "Share price reaches the entry level."
    result.activation_trigger_spec = ActivationTriggerSpec(
        unresolved_claim="The operating recovery is unresolved.",
        observable_metric_or_event="Share price reaches the entry level.",
        threshold_or_direction="Below the entry level.",
        evidence_window="0-12 months.",
        single_observation_sufficient=True,
        observation_requirement="One observation resolves the condition.",
    )

    with pytest.raises(StockAnalysisValidationError, match="operating metric"):
        AgentExecutionBoundary._validate_activation_trigger(result)


def test_v3_ownership_claim_uses_exact_packet_field_and_source_binding():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    result.ownership_claims = [
        OwnershipClaim(
            claim_kind="liquidity",
            subject_role="market",
            measure="adtv_20",
            binding=OwnershipBinding(
                source_ids=["liquidity:borsdata:42:2026-08-31:20d"],
                deterministic_field=(
                    "research_evidence.ownership_liquidity.liquidity.adtv_20"
                ),
                asserted_value=1_200_000,
                asserted_unit="currency",
            ),
        )
    ]
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "source_ids": ["liquidity:borsdata:42:2026-08-31:20d"],
                "liquidity": {"adtv_20": 1_200_000},
                "source_ids_by_measure": {
                    "adtv_20": ["liquidity:borsdata:42:2026-08-31:20d"]
                },
            },
        },
    )

    parsed = AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
        _v3_qualitative_response(result), candidate
    )

    assert isinstance(parsed.ownership_claims[0], OwnershipClaim)


def test_v3_ownership_binding_requires_complete_multi_source_set():
    result = valid_result()
    result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    result.ownership_claims = [
        OwnershipClaim(
            claim_kind="buyback",
            subject_role="company",
            measure="trailing_3_month_change_shares_raw",
            binding=OwnershipBinding(
                source_ids=[
                    "buyback:borsdata:42:2026-08-20",
                    "buyback:borsdata:42:2026-06-01",
                ],
                deterministic_field=(
                    "research_evidence.ownership_liquidity.flow_signals.buybacks."
                    "trailing_3_month_change_shares_raw"
                ),
                asserted_value=-300,
                asserted_unit="shares",
            ),
        )
    ]
    candidate = AgentCandidate(
        rank=1, company_id=42, ticker="TEST", name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "source_ids": [
                    "buyback:borsdata:42:2026-08-20",
                    "buyback:borsdata:42:2026-06-01",
                ],
                "flow_signals": {"buybacks": {
                    "trailing_3_month_change_shares_raw": -300,
                }},
                "source_ids_by_measure": {
                    "trailing_3_month_change_shares_raw": [
                        "buyback:borsdata:42:2026-08-20",
                        "buyback:borsdata:42:2026-06-01",
                    ]
                },
            },
        },
    )

    parsed = AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
        _v3_qualitative_response(result), candidate
    )

    assert parsed.ownership_claims[0].binding.source_ids == [
        "buyback:borsdata:42:2026-08-20",
        "buyback:borsdata:42:2026-06-01",
    ]


def test_documentary_management_and_capital_allocation_facts_are_not_ownership_claims():
    result = valid_result()
    result.management_assessment = "Management has institutional experience."
    result.management_claims = [
        AssessmentClaim(
            statement=result.management_assessment,
            evidence_kind="management_claim",
            source_ids=["news:21"],
        )
    ]
    result.company_fact_ledger.balance_sheet_and_capital_allocation = [
        CompanyFact(
            statement="The company acquired a stake in Supplier AB.",
            evidence_kind="fact",
            source_ids=["news:21"],
        )
    ]
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )

    persisted = AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
        qualitative_response(result), candidate
    )

    assert persisted.management_assessment == "Management has institutional experience."
    assert persisted.company_fact_ledger.balance_sheet_and_capital_allocation[0].statement == (
        "The company acquired a stake in Supplier AB."
    )


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
    assert persisted.result.peak_margin_bridge["status"] == "unassessable"
    assert persisted.result.peak_margin_bridge["forecast"]
    assert persisted.result.scenario_driver_attribution["status"] == "unassessable"
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

    with pytest.raises(StockAnalysisValidationError, match="available forward scenario"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


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


def test_execution_boundary_removes_outcome_from_unverifiable_management_claim():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 109
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
    claim = payload.management_credibility_ledger[0]
    claim.observed_outcome = "An unsupported outcome assertion."
    claim.claim_source_ids = ["news:21"]
    claim.outcome_source_ids = ["news:22"]
    claim.source_ids = ["news:21", "news:22"]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    normalized = persisted.result.management_credibility_ledger[0]
    assert normalized.observed_outcome is None
    assert normalized.outcome_source_ids == []
    assert normalized.source_ids == ["news:21"]


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


def test_execution_boundary_derives_management_coverage_counts_from_ledger():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 109
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_credibility_coverage = ManagementCredibilityCoverage(
        eligible_claim_count=99,
        assessed_claim_count=99,
        pending_claim_count=99,
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    coverage = persisted.result.management_credibility_coverage
    assert coverage.eligible_claim_count == 1
    assert coverage.assessed_claim_count == 0
    assert coverage.pending_claim_count == 1


def test_execution_boundary_records_packet_gaps_with_typed_missing_information():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 110
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "missing_information": [
                "Free-float percentage is unavailable",
                "Ownership-change history is unavailable",
            ],
        },
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(valid_result().to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.missing_information == [
        "Free-float percentage is unavailable",
        "Ownership-change history is unavailable",
    ]
    assert [detail.limitation_class for detail in persisted.result.missing_information_details] == [
        "supplemental",
        "supplemental",
    ]


def test_execution_boundary_records_omitted_management_claims_as_a_limitation():
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 111
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.management_credibility_coverage = ManagementCredibilityCoverage(
        omitted_claim_count=1,
        omission_reasons=["The selected reports do not cover the earlier guidance history."],
    )

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.missing_information == [
        "Eligible management claims were omitted from the credibility ledger"
    ]
    assert persisted.result.missing_information_details[0].limitation_class == "supplemental"


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

    with pytest.raises(StockAnalysisValidationError, match="available forward scenario"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


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


def test_execution_boundary_rejects_invented_path_for_empty_buyback_evidence():
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"ownership_liquidity": {"status": "available"}},
        research_evidence={
            "documents": [{"source_id": "news:21"}],
            "ownership_liquidity": {
                "flow_signals": {
                    "buybacks": {"status": "empty", "source_ids": []},
                },
                "source_ids": [],
            },
        },
    )
    payload = valid_result()
    payload.citations = [
        EvidenceCitation(
            "full_results.ownership_liquidity.flow_signals.buybacks",
            "No executed buybacks were found.",
        )
    ]
    qualitative_payload = payload.to_dict()
    qualitative_payload.pop("scenario_bundles")
    qualitative_payload.pop("forward_scenario_analysis")

    with pytest.raises(StockAnalysisValidationError, match="unknown evidence source"):
        AgentExecutionBoundary(repository).validate_qualitative_response(
            json.dumps(qualitative_payload), candidate
        )


@pytest.mark.parametrize(
    "full_results",
    [
        {"financial": {"gross_margin": 0.48}},
        {"financial": {"margins": [0.48]}},
        {"financial": {"gross_margin": 0.48}},
        {"financial": {"metrics": {1: "integer", "1": "string"}}},
    ],
)
@pytest.mark.parametrize(
    "source_id",
    [
        "full_results.financial.invented_margin",
        "full_results.financial.margins.1",
        "full_results.financial.gross_margin.trailing",
        "full_results.financial.metrics.1",
    ],
)
def test_m1_boundary_rejects_invalid_exact_paths(full_results, source_id):
    repository = MagicMock()
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results=full_results,
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [EvidenceCitation(source_id, "Unsupported deterministic fact.")]

    with pytest.raises(StockAnalysisValidationError, match="unknown evidence source"):
        AgentExecutionBoundary(repository).persist_response(
            json.dumps(payload.to_dict()), candidate, created_by="test-model"
        )


@pytest.mark.parametrize(
    ("source_id", "canonical"),
    [
        (
            "full_results.financial_history.2024.revenue.1",
            "deterministic:financial_history:2024:revenue:1",
        ),
        (
            "full_results.peer_comparison.114.metrics.0",
            "deterministic:peer_comparison",
        ),
        (
            "full_results.financial_history.half_year_comparison",
            "deterministic:financial_history:half_year_comparison",
        ),
    ],
)
def test_m0_boundary_characterizes_integer_keys_list_indices_and_aggregate_aliases(
    source_id, canonical
):
    repository = MagicMock()
    repository.save_stock_analysis.return_value = 108
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={
            "financial_history": {
                2024: {"revenue": [100.0, 110.0]},
                "half_year_comparison": {"revenue_growth": 0.1},
            },
            "peer_comparison": {114: {"metrics": [7.5]}},
        },
        research_evidence={"documents": [{"source_id": "news:21"}]},
    )
    payload = valid_result()
    payload.citations = [EvidenceCitation(source_id, "Synthetic deterministic fact.")]

    persisted = AgentExecutionBoundary(repository).persist_response(
        json.dumps(payload.to_dict()), candidate, created_by="test-model"
    )

    assert persisted.result.citations[0].source_id == canonical


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
