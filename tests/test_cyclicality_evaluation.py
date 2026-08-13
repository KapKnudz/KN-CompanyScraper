import json

import pytest

from kncompanyscraper.analysis.agent.cyclicality_evaluation import (
    CyclicalityClassification,
    CyclicalityCitation,
    CyclicalityDimension,
    CyclicalityEvaluationError,
    CyclicalityPromptBuilder,
    CyclicalityRun,
    build_evidence_passages,
    build_cyclicality_consensus,
    cyclicality_run_from_dict,
    derive_risk_profile,
    parse_cyclicality_classification,
    summarize_cyclicality_runs,
)


DOCUMENTS = [
    {
        "source_id": "document:1",
        "title": "Annual report",
        "text": (
            "Subscription revenue represented 82% of annual revenue.\n\n"
            "Customer demand remained resilient through the economic downturn."
        ),
    }
]


def dimension(assessment="unclassified", passage_ids=None):
    return {
        "assessment": assessment,
        "rationale": "Evidence assessment.",
        "passage_ids": passage_ids or [],
    }


def payload(**dimension_overrides):
    dimensions = {
        "revenue_recurrence": dimension(),
        "economic_demand_sensitivity": dimension(),
        "customer_concentration": dimension(),
        "project_dependence": dimension(),
        "order_phasing": dimension(),
        "commodity_or_financing_exposure": dimension(),
    }
    dimensions.update(dimension_overrides)
    return json.dumps(
        {
            "dimensions": dimensions,
            "rationale": "The supplied evidence was assessed by dimension.",
            "missing_information": [],
        }
    )


def test_passages_have_stable_ids_and_retain_source_text():
    passages = build_evidence_passages(DOCUMENTS)

    assert [passage["passage_id"] for passage in passages] == [
        "document:1#p1",
        "document:1#p2",
    ]
    assert passages[0]["source_id"] == "document:1"
    assert passages[0]["text"] == "Subscription revenue represented 82% of annual revenue."


def test_asymmetric_prompt_defines_a_conservative_materiality_gate():
    from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate

    prompt = CyclicalityPromptBuilder().build(
        AgentCandidate(1, 1, "ONE", "One", research_evidence={"documents": []})
    )

    assert "realized significant revenue, profit, or cash-flow damage" in prompt.system
    assert "Postponed decisions or longer sales cycles alone" in prompt.system
    assert "one contract or award without company scale" in prompt.system
    assert prompt.policy_version == "2.1.0"


def test_parser_resolves_passage_ids_without_model_copied_quotes():
    result = parse_cyclicality_classification(
        payload(
            revenue_recurrence=dimension("predominant", ["document:1#p1"]),
            economic_demand_sensitivity=dimension("material", ["document:1#p2"]),
        ),
        DOCUMENTS,
    )

    assert result.risk_profile == "cyclical_or_other_risk"
    assert result.profile_driver == "economic_demand_sensitivity"
    assert result.evidence[0].quote == (
        "Subscription revenue represented 82% of annual revenue."
    )


def test_parser_rejects_unknown_passage_or_unsupported_dimension():
    with pytest.raises(CyclicalityEvaluationError, match="unknown passage"):
        parse_cyclicality_classification(
            payload(revenue_recurrence=dimension("predominant", ["document:1#p99"])),
            DOCUMENTS,
        )

    with pytest.raises(CyclicalityEvaluationError, match="requires passage evidence"):
        parse_cyclicality_classification(
            payload(revenue_recurrence=dimension("predominant")), DOCUMENTS
        )

    with pytest.raises(CyclicalityEvaluationError, match="unknown assessment"):
        parse_cyclicality_classification(
            payload(revenue_recurrence=dimension("high", ["document:1#p1"])),
            DOCUMENTS,
        )

    with pytest.raises(CyclicalityEvaluationError, match="unknown assessment"):
        parse_cyclicality_classification(
            payload(
                economic_demand_sensitivity=dimension(
                    "moderate", ["document:1#p2"]
                )
            ),
            DOCUMENTS,
        )


def test_no_evidence_stays_on_low_confidence_baseline():
    result = parse_cyclicality_classification(payload(), [])

    assert result.risk_profile == "slightly_cyclical"
    assert result.profile_driver == "baseline_no_material_risk"
    assert result.confidence == "low"
    assert result.evidence == []


def test_deterministic_rules_only_escalate_on_material_risk():
    dimensions = {
        name: CyclicalityDimension("unclassified", "Missing", [])
        for name in (
            "economic_demand_sensitivity",
            "customer_concentration",
            "project_dependence",
            "order_phasing",
            "commodity_or_financing_exposure",
        )
    }
    dimensions["revenue_recurrence"] = CyclicalityDimension(
        "predominant", "Supported", ["source#p2"]
    )
    assert derive_risk_profile(dimensions) == (
        "slightly_cyclical",
        "baseline_no_material_risk",
    )

    dimensions["project_dependence"] = CyclicalityDimension(
        "material", "Supported", ["source#p3"]
    )
    assert derive_risk_profile(dimensions) == (
        "cyclical_or_other_risk",
        "project_dependence",
    )


def test_order_phasing_does_not_select_a_risk_curve():
    dimensions = {
        name: CyclicalityDimension("unclassified", "Missing", [])
        for name in (
            "revenue_recurrence",
            "economic_demand_sensitivity",
            "customer_concentration",
            "project_dependence",
            "order_phasing",
            "commodity_or_financing_exposure",
        )
    }
    dimensions["order_phasing"] = CyclicalityDimension(
        "meaningful", "Quarterly orders vary", ["source#p1"]
    )

    assert derive_risk_profile(dimensions) == (
        "slightly_cyclical",
        "baseline_no_material_risk",
    )


def test_material_assessment_requires_passage_reference():
    with pytest.raises(CyclicalityEvaluationError, match="requires passage evidence"):
        parse_cyclicality_classification(
            payload(customer_concentration=dimension("material")), DOCUMENTS
        )


def test_harmless_json_deviations_are_normalized_with_warnings():
    raw = json.loads(payload())
    raw["company_id"] = 42
    raw["ticker"] = "TEST"
    raw["missing_information"] = "No passages supplied"
    raw["rationale"] = ""
    for item in raw["dimensions"].values():
        item["rationale"] = ""

    result = parse_cyclicality_classification(json.dumps(raw), [])

    assert result.missing_information == ["No passages supplied"]
    assert "missing_information string normalized to array" in result.warnings
    assert "ignored echoed identity field: company_id" in result.warnings
    assert "missing or empty top-level rationale normalized" in result.warnings
    assert len(result.warnings) == 10


def test_passage_retrieval_balances_dimensions():
    recurrence = "\n\n".join(
        f"Subscription revenue statement number {index} is recurring revenue evidence."
        for index in range(20)
    )
    documents = [
        {"source_id": "document:1", "title": "Report", "text": recurrence},
        {
            "source_id": "document:2",
            "title": "Risk report",
            "text": "The largest customer represents 45 percent of group revenue.",
        },
    ]

    passages = build_evidence_passages(documents, max_passages=6)

    assert len(passages) == 6
    assert any(
        "customer_concentration" in passage["relevant_dimensions"]
        for passage in passages
    )


def test_summary_measures_exact_between_run_profile_agreement():
    dimensions = {
        name: CyclicalityDimension("unclassified", "Missing", [])
        for name in (
            "revenue_recurrence",
            "economic_demand_sensitivity",
            "customer_concentration",
            "project_dependence",
            "order_phasing",
            "commodity_or_financing_exposure",
        )
    }
    classifications = [
        CyclicalityClassification(
            profile, "low", "Reason", [], [], "driver", dimensions, []
        )
        for profile in ("unclassified", "unclassified", "slightly_cyclical")
    ]
    runs = [
        CyclicalityRun(
            1,
            "ONE",
            "One",
            index,
            str(index),
            "model",
            {},
            "{}",
            classification,
            None,
        )
        for index, classification in enumerate(classifications, 1)
    ]

    summary = summarize_cyclicality_runs(runs)

    assert summary["unanimous_company_rate"] == 0.0
    assert summary["pairwise_profile_agreement"] == pytest.approx(1 / 3)
    assert summary["validation_pass_rate"] == 1.0
    assert summary["comparable_company_count"] == 1


def consensus_run(run, material_dimensions=(), error=None):
    dimensions = {
        name: CyclicalityDimension("unclassified", "Missing", [])
        for name in (
            "revenue_recurrence",
            "economic_demand_sensitivity",
            "customer_concentration",
            "project_dependence",
            "order_phasing",
            "commodity_or_financing_exposure",
        )
    }
    evidence = []
    for name in material_dimensions:
        passage_id = f"document:{run}#{name}"
        dimensions[name] = CyclicalityDimension(
            "material", "Supported", [passage_id]
        )
        evidence.append(
            CyclicalityCitation(passage_id, f"document:{run}", "Supported passage")
        )
    classification = None
    if error is None:
        profile, driver = derive_risk_profile(dimensions)
        classification = CyclicalityClassification(
            profile, "medium", "Reason", evidence, [], driver, dimensions, []
        )
    return CyclicalityRun(
        1,
        "ONE",
        "One",
        run,
        str(run),
        "model",
        {},
        "{}",
        classification,
        error,
    )


def test_consensus_escalates_only_on_same_dimension_majority():
    runs = [
        consensus_run(1, ("project_dependence",)),
        consensus_run(2, ("project_dependence",)),
        consensus_run(3),
    ]

    consensus = build_cyclicality_consensus(runs)[0]

    assert consensus["status"] == "complete"
    assert consensus["risk_profile"] == "cyclical_or_other_risk"
    assert consensus["profile_driver"] == "project_dependence"
    assert consensus["material_votes"]["project_dependence"] == 2
    assert consensus["material_runs"]["project_dependence"] == [1, 2]
    assert consensus["supporting_runs"] == [1, 2]
    assert [item["passage_id"] for item in consensus["evidence"]] == [
        "document:1#project_dependence",
        "document:2#project_dependence",
    ]
    assert consensus["review_required"] is True


def test_consensus_does_not_combine_different_material_dimensions():
    runs = [
        consensus_run(1, ("economic_demand_sensitivity",)),
        consensus_run(2, ("project_dependence",)),
        consensus_run(3),
    ]

    consensus = build_cyclicality_consensus(runs)[0]

    assert consensus["risk_profile"] == "slightly_cyclical"
    assert consensus["profile_driver"] == "baseline_no_consensus_material_risk"
    assert consensus["review_required"] is True
    assert consensus["evidence"] == []
    assert consensus["material_runs"] == {
        "economic_demand_sensitivity": [1],
        "customer_concentration": [],
        "project_dependence": [2],
        "commodity_or_financing_exposure": [],
    }


def test_unanimous_baseline_consensus_does_not_require_review():
    consensus = build_cyclicality_consensus(
        [consensus_run(1), consensus_run(2), consensus_run(3)]
    )[0]

    assert consensus["risk_profile"] == "slightly_cyclical"
    assert consensus["consensus_strength"] == "unanimous"
    assert consensus["review_required"] is False


def test_unanimous_material_consensus_does_not_require_review():
    consensus = build_cyclicality_consensus(
        [
            consensus_run(1, ("project_dependence",)),
            consensus_run(2, ("project_dependence",)),
            consensus_run(3, ("project_dependence",)),
        ]
    )[0]

    assert consensus["risk_profile"] == "cyclical_or_other_risk"
    assert consensus["consensus_strength"] == "unanimous"
    assert consensus["review_required"] is False


def test_consensus_is_incomplete_without_three_valid_runs():
    consensus = build_cyclicality_consensus(
        [consensus_run(1), consensus_run(2, error="invalid"), consensus_run(3)]
    )[0]

    assert consensus["status"] == "incomplete"
    assert consensus["risk_profile"] is None
    assert consensus["valid_run_count"] == 2
    assert consensus["review_required"] is True


def test_saved_run_round_trips_into_consensus_replay():
    original = consensus_run(1, ("project_dependence",))

    replayed = cyclicality_run_from_dict(original.to_dict())

    assert replayed == original


def test_evaluator_retains_generation_failure_as_failed_run():
    from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
    from kncompanyscraper.analysis.agent.cyclicality_evaluation import CyclicalityEvaluator

    class FailingAdapter:
        model = "test-model"

        def generate(self, prompt):
            raise RuntimeError("output limit")

    candidate = AgentCandidate(1, 1, "ONE", "One", research_evidence={"documents": []})

    runs = CyclicalityEvaluator(FailingAdapter()).evaluate([candidate], runs=2)

    assert len(runs) == 2
    assert runs[0].classification is None
    assert runs[0].error == "generation failed: output limit"
