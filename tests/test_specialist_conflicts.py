import pytest

from kncompanyscraper.analysis.agent.output_schema import (
    BusinessModelSpecialistOutput,
    GrowthValuationSpecialistOutput,
    InsiderOwnershipSpecialistOutput,
    ManagementCredibilitySpecialistOutput,
    ManagementCredibilityCoverage,
    ManagementLedgerRow,
    ManagementPatternState,
    MarginSpecialistOutput,
    SpecialistAgentName,
    SpecialistClaim,
    SpecialistClaimDirection,
    SpecialistConfidence,
    SpecialistOutput,
    SpecialistStatus,
    SellConditionsSpecialistOutput,
)
from kncompanyscraper.analysis.agent.specialist_conflicts import (
    evaluate_specialist_conflicts,
)


_SOURCE = "source:fixture"


def _unassessable_valuation_claim():
    return _claim(
        "valuation.gap",
        "valuation",
        direction=SpecialistClaimDirection.UNASSESSABLE,
    )


def _claim(
    claim_id,
    domain,
    *,
    direction=SpecialistClaimDirection.POSITIVE,
    value=None,
):
    return SpecialistClaim(
        claim_id=claim_id,
        domain=domain,
        predicate="assessment",
        value=(
            "supported"
            if value is None and direction is SpecialistClaimDirection.POSITIVE
            else value
        ),
        direction=direction,
        source_ids=[_SOURCE],
    )


def _output(agent_name, **domain):
    return SpecialistOutput(
        schema_version="specialist-output-v1",
        run_id="run-fixture",
        agent_name=agent_name,
        company_id=42,
        ticker="TEST",
        evidence_as_of="2026-08-16",
        status=SpecialistStatus.COMPLETE,
        confidence=SpecialistConfidence.MEDIUM,
        confidence_cap=SpecialistConfidence.MEDIUM,
        claims=domain.pop("claims", []),
        missing_information=[],
        packet_hash="a" * 64,
        **domain,
    )


def _margin(*, state="stalled", dependency="primary", claims=None):
    return _output(
        SpecialistAgentName.MARGIN,
        claims=claims or [_claim("margin.engine", "margin")],
        margin=MarginSpecialistOutput(
            margin_state=state,
            current_ebit_margin=0.05,
            defensible_peak_ebit_margin=0.15,
            mechanism="fixed-cost absorption",
            supporting_source_ids=[_SOURCE],
            contrary_source_ids=[],
            margin_dependency=dependency,
        ),
    )


def _sell(*, triggered=True, blocker=False):
    tests = [
        {
            "break_type": "margin_or_execution",
            "condition": "margin mechanism fails",
            "observable_metric_or_event": "EBIT margin",
            "threshold_or_direction": "declines",
            "current_break_status": "triggered" if triggered else "not_triggered",
            "response": "reassess",
            "source_ids": [_SOURCE],
            "claim_ids": ["sell.margin"],
        }
    ]
    blockers = (
        [{"blocker_code": "margin_or_execution", "source_ids": [_SOURCE], "claim_ids": ["sell.blocker"]}]
        if blocker
        else []
    )
    return _output(
        SpecialistAgentName.SELL_CONDITIONS,
        sell_conditions=SellConditionsSpecialistOutput(
            tests=tests,
            current_break_status="triggered" if triggered else "not_triggered",
            activation_blockers=blockers,
        ),
    )


def _management(*, result="missed", pattern=ManagementPatternState.WEAK):
    row = ManagementLedgerRow(
        quarter="2026-Q1",
        claim_id="management.promise",
        claim="The promised milestone",
        expected_timing="2026-Q1",
        observed_outcome="The milestone was missed",
        result=result,
        claim_source_ids=[_SOURCE],
        outcome_source_ids=[_SOURCE],
        source_ids=[_SOURCE],
    )
    return _output(
        SpecialistAgentName.MANAGEMENT_CREDIBILITY,
        management_credibility=ManagementCredibilitySpecialistOutput(
            coverage=ManagementCredibilityCoverage(),
            pattern_state=pattern,
            ledger=[row],
        ),
    )


def _insider(*, signal="positive", strength="strong"):
    return _output(
        SpecialistAgentName.INSIDER_OWNERSHIP,
        insider_ownership=InsiderOwnershipSpecialistOutput(
            insider_signal=signal,
            signal_strength=strength,
            flow_effect="supportive",
            event_claims=[_claim("insider.purchase", "insider")],
        ),
    )


def _business(circle="outside", claims=None):
    return _output(
        SpecialistAgentName.BUSINESS_MODEL,
        business_model=BusinessModelSpecialistOutput(
            circle_of_competence=circle,
            claims=claims or [_claim("business.circle", "business_model")],
        ),
    )


def _growth(
    *,
    reverse="demanding",
    dependency="fundamental",
    claims=None,
    envelope_claims=None,
):
    return _output(
        SpecialistAgentName.GROWTH_VALUATION,
        claims=envelope_claims or [],
        growth_valuation=GrowthValuationSpecialistOutput(
            growth_state="supported",
            revenue_mechanism="organic_growth",
            reverse_dcf_assessment=reverse,
            engine_dependency=dependency,
            claims=claims or [_claim("valuation.case", "valuation")],
        ),
    )


EVALUATION_CASES = [
    (("margin", (_margin(), _sell()), None), {"margin_vs_sell_condition"}),
    (("insider", (_management(), _insider()), None), {"insider_vs_credibility_record"}),
    (("circle", (_business("outside"), _growth(reverse="unassessable", claims=[_unassessable_valuation_claim()])), None), {"circle_of_competence_vs_valuation"}),
    (("multiple", (_growth(dependency="multiple_only"),), "latent_case"), {"multiple_expansion_vs_activation"}),
    (("margin-near-miss", (_margin(state="active"), _sell(triggered=True)), None), set()),
    (("shock-near-miss", (_management(result="external_shock"), _insider()), None), set()),
    (("flow-near-miss", (_management(result="kept", pattern=ManagementPatternState.SUPPORTIVE), _insider(), _business("outside")), None), set()),
    (("direction-missing", (_growth(dependency="multiple_only"),), None), set()),
]


@pytest.mark.parametrize(
    ("bundle", "final_direction", "rule_id"),
    [
        (( _margin(), _sell()), None, "margin_vs_sell_condition"),
        (( _margin(), _sell(triggered=False, blocker=True)), None, "margin_vs_sell_condition"),
        (( _management(), _insider()), None, "insider_vs_credibility_record"),
        ((_business("outside"), _growth(reverse="unassessable", claims=[_unassessable_valuation_claim()])), None, "circle_of_competence_vs_valuation"),
        ((_business("unassessable"), _growth(reverse="unassessable", claims=[_unassessable_valuation_claim()])), None, "circle_of_competence_vs_valuation"),
        ((_growth(dependency="multiple_only"),), "latent_case", "multiple_expansion_vs_activation"),
    ],
)
def test_explicit_conflict_rules_surface_typed_triggers(
    bundle, final_direction, rule_id
):
    conflicts = evaluate_specialist_conflicts(bundle, final_direction=final_direction)

    assert [conflict.rule_id for conflict in conflicts] == [rule_id]
    conflict = conflicts[0]
    assert conflict.action == ("annotate" if rule_id == "insider_vs_credibility_record" else "block_activation")
    assert conflict.severity == ("medium" if rule_id == "insider_vs_credibility_record" else "high")
    assert conflict.trigger_fields
    assert conflict.trigger_claim_ids or rule_id == "circle_of_competence_vs_valuation"
    assert conflict.source_ids
    assert conflict.explanation


@pytest.mark.parametrize(
    "bundle,final_direction",
    [
        ((_margin(state="active"), _sell(triggered=False)), None),
        ((_margin(state="active"), _sell(triggered=True)), None),
        ((_management(result="external_shock"), _insider()), None),
        ((_management(result="kept", pattern=ManagementPatternState.SUPPORTIVE), _insider(), _business("outside")), None),
        ((_business("inside"), _growth()), None),
        ((_business("outside"), _growth(reverse="plausible")), None),
        ((_business("outside"), _growth(reverse="unassessable", claims=[_claim("growth.engine", "revenue")])), None),
        (
            (
                _margin(
                    state="active",
                    dependency="material",
                    claims=[
                        _claim(
                            "margin.context",
                            "margin",
                            direction=SpecialistClaimDirection.NEGATIVE,
                            value="confirmed",
                        )
                    ],
                ),
                _growth(dependency="multiple_only"),
            ),
            "latent_case",
        ),
        ((_growth(dependency="multiple_only"),), None),
        ((_growth(dependency="multiple_only", claims=[_claim("revenue.engine", "revenue")]),), "activated_case"),
    ],
)
def test_near_miss_bundles_do_not_surface_generic_disagreement(
    bundle, final_direction
):
    assert evaluate_specialist_conflicts(bundle, final_direction=final_direction) == ()


def test_margin_claim_overlap_does_not_make_other_blockers_margin_conflicts():
    sell = _output(
        SpecialistAgentName.SELL_CONDITIONS,
        sell_conditions=SellConditionsSpecialistOutput(
            activation_blockers=[
                {
                    "blocker_code": "valuation",
                    "source_ids": [_SOURCE],
                    "claim_ids": ["margin.engine"],
                }
            ]
        ),
    )

    assert evaluate_specialist_conflicts((_margin(), sell)) == ()


def test_negative_engine_claim_does_not_support_multiple_expansion():
    claims = [
        _claim(
            "revenue.decline",
            "revenue",
            direction=SpecialistClaimDirection.NEGATIVE,
            value="confirmed",
        )
    ]

    conflicts = evaluate_specialist_conflicts(
        (_growth(dependency="multiple_only", claims=claims),),
        final_direction="latent_case",
    )

    assert [conflict.rule_id for conflict in conflicts] == [
        "multiple_expansion_vs_activation"
    ]


def test_business_model_revenue_engine_supports_multiple_expansion():
    business = _business(
        "inside", claims=[_claim("revenue.engine", "revenue")]
    )

    assert evaluate_specialist_conflicts(
        (business, _growth(dependency="multiple_only")),
        final_direction="latent_case",
    ) == ()


def test_multiple_expansion_audit_includes_business_model_claims():
    business = _business(
        "inside",
        claims=[
            _claim(
                "revenue.decline",
                "revenue",
                direction=SpecialistClaimDirection.NEGATIVE,
                value="confirmed",
            )
        ],
    )

    conflicts = evaluate_specialist_conflicts(
        (business, _growth(dependency="multiple_only")),
        final_direction="latent_case",
    )

    assert conflicts[0].trigger_claim_ids == (
        "valuation.case",
        "revenue.decline",
    )
    assert conflicts[0].source_ids == (_SOURCE,)


def test_circle_audit_includes_growth_envelope_claims():
    growth = _growth(
        reverse="unassessable",
        claims=[_unassessable_valuation_claim()],
        envelope_claims=[_claim("valuation.envelope", "valuation")],
    )

    conflicts = evaluate_specialist_conflicts((_business("outside"), growth))

    assert conflicts[0].trigger_claim_ids == (
        "business.circle",
        "valuation.envelope",
        "valuation.gap",
    )


def test_multiple_expansion_audit_includes_growth_envelope_claims():
    growth = _growth(
        dependency="multiple_only",
        envelope_claims=[
            _claim(
                "revenue.decline",
                "revenue",
                direction=SpecialistClaimDirection.NEGATIVE,
                value="confirmed",
            )
        ],
    )

    conflicts = evaluate_specialist_conflicts(
        (growth,),
        final_direction="latent_case",
    )

    assert conflicts[0].trigger_claim_ids == (
        "revenue.decline",
        "valuation.case",
    )


def test_evaluation_fixture_has_precision_oriented_evidence():
    true_positive = false_positive = false_negative = 0
    for (_, bundle, final_direction), expected in EVALUATION_CASES:
        observed = {
            conflict.rule_id
            for conflict in evaluate_specialist_conflicts(
                bundle, final_direction=final_direction
            )
        }
        true_positive += len(observed & expected)
        false_positive += len(observed - expected)
        false_negative += len(expected - observed)

    precision = true_positive / (true_positive + false_positive)
    assert precision == 1.0
    assert false_negative == 0
    assert true_positive == 4


def test_conflict_records_are_deterministic_and_serializable():
    first = evaluate_specialist_conflicts((_margin(), _sell()))
    second = evaluate_specialist_conflicts((_sell(), _margin()))

    assert first == second
    assert first[0].to_dict() == {
        "rule_id": "margin_vs_sell_condition",
        "severity": "high",
        "trigger_fields": [
            "margin.margin_state",
            "margin.margin_dependency",
            "sell_conditions.margin_or_execution",
        ],
        "trigger_claim_ids": ["margin.engine", "sell.margin"],
        "explanation": "stalled_or_invalidated_material_margin_mechanism_has_a_triggered_break",
        "source_ids": ["source:fixture"],
        "action": "block_activation",
    }
