from hashlib import sha256
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.agent_packet import AgentCandidatePacket, serialize_packet
from kncompanyscraper.analysis.agent.output_schema import (
    BusinessModelSpecialistOutput,
    GrowthValuationSpecialistOutput,
    InsiderOwnershipSpecialistOutput,
    ManagementCredibilityCoverage,
    ManagementCredibilitySpecialistOutput,
    MarginSpecialistOutput,
    SpecialistAgentName,
    SpecialistClaim,
    SpecialistClaimDirection,
    SpecialistConfidence,
    SpecialistMissingInformation,
    SpecialistOutput,
    SpecialistStatus,
    SellConditionAssessment,
    SellConditionsSpecialistOutput,
)
from kncompanyscraper.analysis.agent.petter_aggregator import (
    AggregatorValidationError,
    AggregatorInput,
    PetterAggregatorPromptBuilder,
    build_aggregation_manifest,
    enforce_aggregation_constraints,
    validate_aggregator_output,
)
from kncompanyscraper.analysis.agent.output_schema import StockAnalysisResult


SOURCE = "financial:fixture"


def packet():
    return AgentCandidatePacket(
        rank=1, company_id=42, ticker="TEST", name="Test", ranking_model="general",
        rank_eligible=True, eligibility_reasons=[], total_score=1.0,
        score_breakdown={}, data_quality="medium", flags=[], candidate_reason=None,
        positives=[], negatives=[], missing_data=[], full_results={},
        research_evidence={
            "as_of": "2026-08-16",
            "documents": [
                {"source_id": SOURCE},
                {"source_id": "news:unmatched"},
                {"source_id": "news:unassessable"},
            ],
        },
    )


def output(agent, domain, *, confidence="high", cap="high"):
    return SpecialistOutput(
        schema_version="specialist-output-v1", run_id="run", agent_name=agent,
        company_id=42, ticker="TEST", evidence_as_of="2026-08-16",
        status=SpecialistStatus.COMPLETE, confidence=confidence,
        confidence_cap=cap, claims=[], missing_information=[], packet_hash="x" * 64,
        **{domain: domain_value(domain)},
    )


def domain_value(domain):
    if domain == "business_model":
        return BusinessModelSpecialistOutput(
            circle_of_competence="inside", profitability_state="profitable",
            claims=[claim("business.engine", "business_model")],
        )
    if domain == "management_credibility":
        return ManagementCredibilitySpecialistOutput(
            coverage=ManagementCredibilityCoverage(
                coverage_tier="no_ledger",
                coverage_state="insufficient_for_pattern_recognition",
                confidence_cap="low",
            ),
            claims=[],
        )
    if domain == "margin":
        return MarginSpecialistOutput(
            margin_state="active", mechanism="scale", supporting_source_ids=[SOURCE],
            margin_dependency="secondary",
        )
    if domain == "insider_ownership":
        return InsiderOwnershipSpecialistOutput(
            insider_signal="none", signal_strength="none", flow_effect="unassessable",
        )
    if domain == "growth_valuation":
        return GrowthValuationSpecialistOutput(
            growth_state="supported", revenue_mechanism="organic_growth",
            reverse_dcf_assessment="plausible", engine_dependency="fundamental",
            claims=[claim("growth.engine", "revenue")],
        )
    return SellConditionsSpecialistOutput(
        tests=[
            SellConditionAssessment(
                break_type=kind, condition="condition", observable_metric_or_event="metric",
                threshold_or_direction="declines", current_break_status="not_triggered",
                response="reassess", source_ids=[], claim_ids=[],
            ) for kind in (
                "revenue_or_demand", "margin_or_execution", "balance_sheet_or_dilution",
                "management_credibility", "valuation_overshoot",
                "superior_evidence_or_opportunity",
            )
        ],
        current_break_status="not_triggered",
    )


def claim(claim_id, domain, direction=SpecialistClaimDirection.POSITIVE):
    return SpecialistClaim(
        claim_id=claim_id, domain=domain, predicate="assessment", value="supported",
        direction=direction, source_ids=[SOURCE],
    )


def bundle(*, management_cap="high", business_circle="inside", sell_break=False):
    items = [
        output(SpecialistAgentName.BUSINESS_MODEL, "business_model"),
        output(SpecialistAgentName.MANAGEMENT_CREDIBILITY, "management_credibility", cap=management_cap),
        output(SpecialistAgentName.MARGIN, "margin"),
        output(SpecialistAgentName.INSIDER_OWNERSHIP, "insider_ownership"),
        output(SpecialistAgentName.GROWTH_VALUATION, "growth_valuation"),
        output(SpecialistAgentName.SELL_CONDITIONS, "sell_conditions"),
    ]
    if business_circle != "inside":
        items[0].business_model.circle_of_competence = business_circle
    if sell_break:
        items[-1].sell_conditions.tests[0].current_break_status = "triggered"
        items[-1].sell_conditions.current_break_status = "triggered"
    return tuple(SimpleNamespace(output=item, agent_name=item.agent_name.value, status="accepted", artifact_ids=(1,)) for item in items)


def inputs(items):
    p = packet()
    packet_hash = sha256(serialize_packet(p).encode()).hexdigest()
    for item in items:
        item.output.packet_hash = packet_hash
    return AggregatorInput(
        packet=p,
        packet_hash=packet_hash,
        run_id="run",
        specialist_outputs=items,
        deterministic_scenario_results={
            "status": "available", "base": {"low_annualized_return": 0.20}
        },
        reverse_dcf_results={
            "status": "available", "required_return": {"required_return": 0.10}
        },
    )


def test_prompt_contains_typed_inputs_and_precedence_without_prose_reports():
    prompt = PetterAggregatorPromptBuilder().build(inputs(bundle()))
    assert "business.engine" in prompt.user
    assert "evidence_readiness" in prompt.user
    assert "company.engine" not in prompt.user
    assert prompt.schema_name == "petter_aggregator_v3"


def test_activation_is_blocked_by_missing_inputs_and_deterministic_hurdle():
    result = StockAnalysisResult(42, "TEST", "Test", "activated_case", "high", "")
    partial = inputs(bundle()[:-2])
    partial = AggregatorInput(
        packet=partial.packet, packet_hash=partial.packet_hash, run_id=partial.run_id,
        specialist_outputs=partial.specialist_outputs,
        deterministic_scenario_results={"status": "insufficient_evidence"},
        reverse_dcf_results={"status": "available", "required_return": {"required_return": .1}},
    )
    result, decision = enforce_aggregation_constraints(result, partial)
    assert result.verdict == "watch"
    assert not decision.eligible
    assert "missing_growth_valuation" in decision.blocked_by
    assert "deterministic_valuation_insufficient" in decision.blocked_by


def test_management_cap_and_sell_break_are_deterministic_and_flow_cannot_rescue():
    result = StockAnalysisResult(42, "TEST", "Test", "activated_case", "high", "")
    result, decision = enforce_aggregation_constraints(
        result, inputs(bundle(management_cap="low", sell_break=True))
    )
    assert result.confidence == "low"
    assert result.verdict == "reject"
    assert "causal_sell_break_triggered" in decision.blocked_by


def test_numeric_valuation_claim_is_rejected_with_generic_identifiers():
    candidate = StockAnalysisResult(42, "TEST", "Test", "watch", "medium", "")
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "generic",
            "domain": "valuation",
            "predicate": "assessment",
            "value": 123.0,
            "source_ids": [SOURCE],
        }
    }

    with pytest.raises(AggregatorValidationError, match="may not author"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_numeric_valuation_domain_variant_is_rejected():
    candidate = StockAnalysisResult(42, "TEST", "Test", "watch", "medium", "")
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "generic",
            "domain": "valuation_expectations",
            "predicate": "assessment",
            "value": 123.0,
            "source_ids": [SOURCE],
        }
    }

    with pytest.raises(AggregatorValidationError, match="may not author"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_final_claim_requires_upstream_specialist_linkage():
    candidate = StockAnalysisResult(42, "TEST", "Test", "watch", "medium", "")
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "unlinked",
            "domain": "revenue",
            "predicate": "assessment",
            "value": "supported",
            "source_ids": ["news:unmatched"],
        }
    }

    with pytest.raises(AggregatorValidationError, match="upstream specialist claim"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_source_bearing_break_test_is_traced_and_preserves_limitations():
    items = list(bundle())
    items[0].output.business_model.claims[0].limitation_codes = ["limited_history"]
    candidate = StockAnalysisResult(42, "TEST", "Test", "watch", "medium", "")
    candidate.structured_conclusions = {
        "thesis_break_tests": [{"break_type": "revenue_or_demand", "source_ids": [SOURCE]}]
    }

    aggregation_inputs = inputs(tuple(items))
    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert "business_model:business.engine" in manifest.evidence_trace[0].upstream_claim_ids
    assert manifest.evidence_trace[0].limitation_codes == ("limited_history",)


def test_unassessable_specialist_claim_cannot_support_final_claim():
    items = list(bundle())
    items[0].output.business_model.claims[0].source_ids = ["news:unassessable"]
    items[0].output.business_model.claims[0].direction = SpecialistClaimDirection.UNASSESSABLE
    candidate = StockAnalysisResult(42, "TEST", "Test", "watch", "medium", "")
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "unsupported",
            "domain": "business_model",
            "predicate": "assessment",
            "value": "supported",
            "source_ids": ["news:unassessable"],
        }
    }

    with pytest.raises(AggregatorValidationError, match="upstream specialist claim"):
        validate_aggregator_output(candidate, inputs(tuple(items)))


def test_core_specialist_missing_information_blocks_activation():
    items = list(bundle())
    items[0].output.missing_information = [
        SpecialistMissingInformation("missing_history", "core", "case_limited")
    ]

    result = StockAnalysisResult(42, "TEST", "Test", "activated_case", "high", "")
    result, decision = enforce_aggregation_constraints(result, inputs(tuple(items)))

    assert not decision.eligible
    assert "business_model_core_evidence_missing" in decision.blocked_by
