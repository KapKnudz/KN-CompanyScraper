import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.agent_packet import AgentCandidatePacket, serialize_packet
from kncompanyscraper.analysis.agent.output_schema import (
    BusinessModelSpecialistOutput,
    GrowthValuationSpecialistOutput,
    InsiderOwnershipSpecialistOutput,
    OwnershipBinding,
    OwnershipClaim,
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
    ManagementLedgerRow,
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
    _validate_with_boundary,
)
from kncompanyscraper.analysis.agent.output_schema import StockAnalysisResult


SOURCE = "financial:fixture"
DETERMINISTIC_SOURCE = "valuation:reverse_dcf:revenue_growth"
SCENARIO_SOURCE = "news:scenario"
SELL_SOURCE = "news:sell-unassessable"
OWNERSHIP_SOURCE = "news:ownership"


def packet():
    return AgentCandidatePacket(
        rank=1, company_id=42, ticker="TEST", name="Test", ranking_model="general",
        rank_eligible=True, eligibility_reasons=[], total_score=1.0,
        score_breakdown={}, data_quality="medium", flags=[], candidate_reason=None,
        positives=[], negatives=[], missing_data=[],
        full_results={
            "reverse_dcf": {
                "implied_expectations": {
                    "revenue_growth": {"source_id": DETERMINISTIC_SOURCE}
                }
            }
        },
        research_evidence={
            "as_of": "2026-08-16",
            "documents": [
                {"source_id": SOURCE},
                {"source_id": "news:unmatched"},
                {"source_id": "news:unassessable"},
                {"source_id": SCENARIO_SOURCE},
                {"source_id": SELL_SOURCE},
                {"source_id": OWNERSHIP_SOURCE},
            ],
            "ownership_liquidity": {
                "source_ids": [OWNERSHIP_SOURCE],
                "flow_signals": {
                    "buybacks": {"latest_event_date": "2026-08-16"}
                },
                "source_ids_by_measure": {
                    "latest_event_date": [OWNERSHIP_SOURCE]
                },
            },
        },
    )


def make_candidate(verdict="watch", confidence="medium", packet_hash=None):
    return StockAnalysisResult(
        42,
        "TEST",
        "Test",
        verdict,
        confidence,
        "",
        packet_hash=packet_hash
        or sha256(serialize_packet(packet()).encode()).hexdigest(),
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


def inputs(items, p=None):
    p = p or packet()
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
    assert "business_model:business.engine" in prompt.user
    assert "evidence_readiness" in prompt.user
    assert "company.engine" not in prompt.user
    assert prompt.schema_name == "petter_aggregator_v3"


@pytest.mark.parametrize(
    ("upstream_domain", "final_domain", "upstream_claim_id"),
    [
        ("growth_state", "revenue", "growth_valuation_2"),
        ("growth_valuation", "valuation", "growth_valuation_7"),
    ],
)
def test_final_claim_traces_exact_growth_claim_and_all_sources(
    upstream_domain, final_domain, upstream_claim_id
):
    items = list(bundle())
    growth_claim = items[4].output.growth_valuation.claims[0]
    growth_claim.claim_id = upstream_claim_id
    growth_claim.domain = upstream_domain
    growth_claim.source_ids = [SOURCE, SCENARIO_SOURCE]
    aggregation_inputs = inputs(tuple(items))
    candidate = make_candidate(packet_hash=aggregation_inputs.packet_hash)
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": (
                "revenue_or_demand_break_1"
                if final_domain == "revenue"
                else "valuation_expectations_unsupported"
            ),
            "domain": final_domain,
            "predicate": "assessment",
            "value": "unsupported",
            "source_ids": [SOURCE, SCENARIO_SOURCE],
        }
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].upstream_claim_ids == (
        f"growth_valuation:{upstream_claim_id}",
    )
    assert manifest.evidence_trace[0].source_ids == (SOURCE, SCENARIO_SOURCE)


def test_handoff_qualifies_upstream_claim_ids_and_keeps_source_ids_separate():
    items = list(bundle())
    growth_claim = items[4].output.growth_valuation.claims[0]
    growth_claim.claim_id = "growth_valuation_2"
    growth_claim.source_ids = [SOURCE, SCENARIO_SOURCE]

    prompt = PetterAggregatorPromptBuilder().build(inputs(tuple(items)))

    assert "growth_valuation:growth_valuation_2" in prompt.user
    assert SOURCE in prompt.user
    assert SCENARIO_SOURCE in prompt.user
    assert "are source-ID fields: never put a claim ID in them" in prompt.system


def test_source_less_future_break_test_is_audited_without_fabricated_linkage():
    aggregation_inputs = inputs(bundle())
    candidate = make_candidate(packet_hash=aggregation_inputs.packet_hash)
    candidate.structured_conclusions = {
        "thesis_break_tests": [{
            "break_type": "revenue_or_demand",
            "condition_code": "demand_loss",
            "observable_metric_code": "revenue",
            "threshold_code": "declines",
            "response": "reassess",
            "source_ids": [],
            "limitation_codes": [],
        }]
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].source_ids == ()
    assert manifest.evidence_trace[0].upstream_claim_ids == ()


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


def test_operating_latent_uses_upper_bound_for_return_hurdle():
    result = StockAnalysisResult(42, "TEST", "Test", "latent_case", "high", "")
    result.latent_case_type = "operating"
    aggregation_inputs = inputs(bundle())
    aggregation_inputs = AggregatorInput(
        packet=aggregation_inputs.packet,
        packet_hash=aggregation_inputs.packet_hash,
        run_id=aggregation_inputs.run_id,
        specialist_outputs=aggregation_inputs.specialist_outputs,
        deterministic_scenario_results={
            "status": "available",
            "base": {
                "low_annualized_return": 0.05,
                "high_annualized_return": 0.20,
            },
        },
        reverse_dcf_results=aggregation_inputs.reverse_dcf_results,
    )

    _, decision = enforce_aggregation_constraints(result, aggregation_inputs)

    assert "required_return_hurdle_unsatisfied" not in decision.blocked_by


def test_management_cap_and_sell_break_are_deterministic_and_flow_cannot_rescue():
    result = StockAnalysisResult(42, "TEST", "Test", "activated_case", "high", "")
    result, decision = enforce_aggregation_constraints(
        result, inputs(bundle(management_cap="low", sell_break=True))
    )
    assert result.confidence == "low"
    assert result.verdict == "reject"
    assert "causal_sell_break_triggered" in decision.blocked_by


def test_numeric_valuation_claim_is_rejected_with_generic_identifiers():
    candidate = make_candidate()
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


@pytest.mark.parametrize("packet_hash", ["wrong", None])
def test_candidate_packet_hash_must_match_frozen_packet(packet_hash):
    candidate = make_candidate()
    candidate.packet_hash = packet_hash

    with pytest.raises(AggregatorValidationError, match="identity"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_execution_boundary_round_trip_preserves_candidate_packet_hash():
    aggregation_inputs = inputs(bundle())
    candidate = StockAnalysisResult(
        42,
        "TEST",
        "Test",
        "watch",
        "medium",
        "",
        packet_hash=aggregation_inputs.packet_hash,
    )

    class BoundarySpy:
        def validate_qualitative_response(self, raw_response, candidate_model):
            assert "packet_hash" not in json.loads(raw_response)
            return StockAnalysisResult(42, "TEST", "Test", "watch", "medium", "")

    validated = _validate_with_boundary(candidate, aggregation_inputs, BoundarySpy())

    assert validated.packet_hash == aggregation_inputs.packet_hash


def test_numeric_valuation_domain_variant_is_rejected():
    candidate = make_candidate()
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
    candidate = make_candidate()
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


def test_source_less_limited_code_cannot_support_value_claim():
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "limited_support",
            "domain": "business_model",
            "predicate": "assessment",
            "value": "supported",
            "source_ids": [],
            "limitation_codes": ["missing_history"],
        }
    }

    with pytest.raises(AggregatorValidationError, match="requires source_ids"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_source_less_null_value_is_a_typed_absence():
    aggregation_inputs = inputs(bundle())
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "unavailable_value",
            "domain": "business_model",
            "predicate": "assessment",
            "value": None,
            "source_ids": [],
            "limitation_codes": [],
        }
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].source_ids == ()
    assert manifest.evidence_trace[0].upstream_claim_ids == ()


def test_financial_annual_source_ids_must_match_the_packet_exactly():
    p = packet()
    p.research_evidence["documents"].append(
        {"source_id": "financial:annual:2025-12-30"}
    )
    items = list(bundle())
    items[0].output.business_model.claims[0].source_ids = [
        "financial:annual:2025-12-30"
    ]
    aggregation_inputs = inputs(tuple(items), p)
    candidate = make_candidate(packet_hash=aggregation_inputs.packet_hash)
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "annual_period_claim",
            "domain": "business_model",
            "predicate": "assessment",
            "value": "supported",
            "source_ids": ["financial:annual:2025-12-31"],
        }
    }

    with pytest.raises(AggregatorValidationError, match="unknown source ID"):
        validate_aggregator_output(candidate, aggregation_inputs)


def test_expectation_and_baseline_references_are_traced():
    aggregation_inputs = inputs(bundle())
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "headline_case": {"expectation_refs": [DETERMINISTIC_SOURCE]},
        "falsifiable_case": {"baseline_refs": [SOURCE]},
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert [trace.source_ids for trace in manifest.evidence_trace] == [
        (DETERMINISTIC_SOURCE,), (SOURCE,)
    ]
    assert not manifest.evidence_trace[0].upstream_claim_ids
    assert manifest.evidence_trace[0].deterministic_source_ids == (DETERMINISTIC_SOURCE,)
    assert manifest.evidence_trace[1].upstream_claim_ids
    assert not manifest.evidence_trace[1].deterministic_source_ids


def test_sourced_scenario_assumption_is_an_upstream_trace_record():
    items = list(bundle())
    items[4].output.growth_valuation.scenario_bundles = [{
        "revenue_cagr": {"value": 0.1, "source_ids": [SCENARIO_SOURCE]},
    }]
    aggregation_inputs = inputs(tuple(items))
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "evidence_claims": [{
            "claim_id": "scenario.final", "domain": "revenue",
            "predicate": "assessment", "value": "supported",
            "source_ids": [SCENARIO_SOURCE],
        }]
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].upstream_claim_ids == (
        "growth_valuation:scenario_bundle:0:revenue_cagr",
    )


def test_every_cited_source_requires_complete_trace_linkage():
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "partially_traced", "domain": "revenue",
            "predicate": "assessment", "value": "supported",
            "source_ids": [SOURCE, "news:unmatched"],
        }
    }

    with pytest.raises(AggregatorValidationError, match="complete source linkage"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_sell_activation_blocker_blocks_activation():
    items = list(bundle())
    items[-1].output.sell_conditions.activation_blockers = [
        {"blocker_code": "valuation_overshoot", "source_ids": [SOURCE], "claim_ids": []}
    ]

    result = StockAnalysisResult(42, "TEST", "Test", "activated_case", "high", "")
    _, decision = enforce_aggregation_constraints(result, inputs(tuple(items)))

    assert not decision.eligible
    assert "causal_activation_blocker" in decision.blocked_by


def test_management_ledger_is_an_upstream_trace_record():
    items = list(bundle())
    items[1].output.management_credibility.ledger = [
        ManagementLedgerRow(
            quarter="2026-Q2", claim_id="management.row", claim="Guidance",
            expected_timing="2026-Q2", observed_outcome="Kept", result="kept",
            claim_source_ids=[SOURCE], outcome_source_ids=[SOURCE], source_ids=[SOURCE],
        )
    ]
    aggregation_inputs = inputs(tuple(items))
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "management_claims": [{
            "claim_id": "management.final", "domain": "management",
            "predicate": "outcome", "value": "confirmed", "source_ids": [SOURCE],
        }]
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].upstream_claim_ids == ("management_credibility:management.row",)


def test_specialist_missing_information_reaches_final_trace():
    items = list(bundle())
    items[0].output.missing_information = [
        SpecialistMissingInformation("missing_history", "supplemental", "case_limited")
    ]
    aggregation_inputs = inputs(tuple(items))
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "limited_support", "domain": "business_model",
            "predicate": "assessment", "value": "supported", "source_ids": [SOURCE],
        }
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].limitation_codes == ("missing_history",)


def test_unassessable_sell_test_cannot_support_final_claim():
    items = list(bundle())
    items[-1].output.sell_conditions.tests[0].source_ids = [SELL_SOURCE]
    items[-1].output.sell_conditions.tests[0].current_break_status = "unassessable"
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "sell_gap", "domain": "revenue",
            "predicate": "assessment", "value": "supported", "source_ids": [SELL_SOURCE],
        }
    }

    with pytest.raises(AggregatorValidationError, match="upstream specialist claim"):
        validate_aggregator_output(candidate, inputs(tuple(items)))


def test_limited_claim_trace_deduplicates_upstream_claim_ids():
    aggregation_inputs = inputs(bundle())
    candidate = make_candidate(packet_hash=aggregation_inputs.packet_hash)
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "limited_support",
            "domain": "business_model",
            "predicate": "assessment",
            "value": "unassessable",
            "source_ids": [SOURCE],
        }
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].upstream_claim_ids == (
        "business_model:business.engine",
    )


def test_top_level_ownership_claim_is_traced():
    items = list(bundle())
    items[3].output.insider_ownership.event_claims = [
        claim("insider.event", "insider")
    ]
    items[3].output.insider_ownership.event_claims[0].source_ids = [OWNERSHIP_SOURCE]
    aggregation_inputs = inputs(tuple(items))
    candidate = make_candidate()
    candidate.structured_conclusions = {}
    candidate.ownership_claims = [
        OwnershipClaim(
            claim_kind="buyback", subject_role="company", measure="latest_event_date",
            binding=OwnershipBinding(
                source_ids=[OWNERSHIP_SOURCE],
                deterministic_field="research_evidence.ownership_liquidity.flow_signals.buybacks.latest_event_date",
                asserted_value="2026-08-16", asserted_unit="date",
            ),
        )
    ]

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert manifest.evidence_trace[0].upstream_claim_ids == ("insider_ownership:insider.event",)


def test_insider_ownership_evidence_cannot_support_balance_sheet_claim():
    items = list(bundle())
    items[3].output.insider_ownership.event_claims = [
        claim("insider.event", "insider")
    ]
    items[3].output.insider_ownership.event_claims[0].source_ids = [OWNERSHIP_SOURCE]
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "balance_sheet_claim",
            "domain": "balance_sheet",
            "predicate": "assessment",
            "value": "supported",
            "source_ids": [OWNERSHIP_SOURCE],
        }
    }

    with pytest.raises(AggregatorValidationError, match="upstream specialist claim"):
        validate_aggregator_output(candidate, inputs(tuple(items)))


def test_ownership_binding_cannot_bypass_packet_value_or_specialist_linkage():
    candidate = make_candidate()
    candidate.structured_conclusions = {}
    candidate.ownership_claims = [
        OwnershipClaim(
            claim_kind="buyback",
            subject_role="company",
            measure="latest_event_date",
            binding=OwnershipBinding(
                source_ids=[OWNERSHIP_SOURCE],
                deterministic_field=(
                    "research_evidence.ownership_liquidity.flow_signals.buybacks."
                    "latest_event_date"
                ),
                asserted_value="2026-08-15",
                asserted_unit="date",
            ),
        )
    ]

    with pytest.raises(AggregatorValidationError, match="supplied packet value"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_ownership_binding_must_use_exact_packet_source_set():
    candidate = make_candidate()
    candidate.structured_conclusions = {}
    candidate.ownership_claims = [
        OwnershipClaim(
            claim_kind="buyback",
            subject_role="company",
            measure="latest_event_date",
            binding=OwnershipBinding(
                source_ids=[SOURCE],
                deterministic_field=(
                    "research_evidence.ownership_liquidity.flow_signals.buybacks."
                    "latest_event_date"
                ),
                asserted_value="2026-08-16",
                asserted_unit="date",
            ),
        )
    ]

    with pytest.raises(AggregatorValidationError, match="exact packet source set"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_valid_ownership_binding_still_requires_specialist_linkage():
    candidate = make_candidate()
    candidate.structured_conclusions = {}
    candidate.ownership_claims = [
        OwnershipClaim(
            claim_kind="buyback",
            subject_role="company",
            measure="latest_event_date",
            binding=OwnershipBinding(
                source_ids=[OWNERSHIP_SOURCE],
                deterministic_field=(
                    "research_evidence.ownership_liquidity.flow_signals.buybacks."
                    "latest_event_date"
                ),
                asserted_value="2026-08-16",
                asserted_unit="date",
            ),
        )
    ]

    with pytest.raises(AggregatorValidationError, match="upstream specialist claim"):
        validate_aggregator_output(candidate, inputs(bundle()))


def test_source_empty_unassessable_claim_remains_limited():
    aggregation_inputs = inputs(bundle())
    candidate = make_candidate()
    candidate.structured_conclusions = {
        "claim": {
            "claim_id": "limited", "domain": "evidence",
            "predicate": "source_gap", "value": "unassessable", "source_ids": [],
            "limitation_codes": ["missing_history"],
        }
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert not decision.eligible
    assert manifest.evidence_trace[0].source_ids == ()
    assert manifest.evidence_trace[0].upstream_claim_ids == ()


def test_source_bearing_break_test_is_traced_and_preserves_limitations():
    items = list(bundle())
    items[0].output.business_model.claims[0].limitation_codes = ["limited_history"]
    candidate = make_candidate()
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
    candidate = make_candidate()
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


def test_core_candidate_missing_information_blocks_and_is_manifested():
    candidate = make_candidate("activated_case", "high")
    aggregation_inputs = inputs(bundle())
    candidate.structured_conclusions = {
        "missing_information_details": [{
            "item_code": "missing_cash_flow_history",
            "limitation_class": "core",
            "impact_code": "case_limited",
        }]
    }

    candidate, decision = validate_aggregator_output(candidate, aggregation_inputs)
    manifest = build_aggregation_manifest(aggregation_inputs, candidate, decision)

    assert not decision.eligible
    assert "candidate_core_evidence_missing" in decision.blocked_by
    assert manifest.candidate_missing_information == ({
        "item_code": "missing_cash_flow_history",
        "limitation_class": "core",
        "impact_code": "case_limited",
    },)
