import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.context_provenance import deterministic_context_sha256
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
    parse_thesis_update_result,
)
from kncompanyscraper.analysis.agent.thesis_update import (
    ThesisUpdateContext,
    ThesisUpdateContextBuilder,
    ThesisUpdatePromptBuilder,
)
from kncompanyscraper.analysis.agent.thesis_update_service import (
    ThesisUpdateExecutionBoundary,
    ThesisUpdateService,
)
from tests.test_agent_result_boundary import _v3_qualitative_response, valid_result


def update_response(impact="thesis_strengthened", changed_sections=None):
    return json.dumps(
        {
            "impact": impact,
            "summary": "The new report supports the revenue mechanism.",
            "changed_sections": (
                ["revenue_drivers"] if changed_sections is None else changed_sections
            ),
            "thesis": valid_result().to_dict(),
        }
    )


def v3_update_response(impact="thesis_strengthened", changed_sections=None):
    thesis = valid_result()
    thesis.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    return json.dumps(
        {
            "impact": impact,
            "summary": "The new report supports the revenue mechanism.",
            "changed_sections": (
                ["revenue_drivers"] if changed_sections is None else changed_sections
            ),
            "thesis": json.loads(_v3_qualitative_response(thesis)),
        }
    )


def latent_update_response(*, evidence_status="unresolved", evidence_window="Q3 2026 report"):
    return v3_latent_update_response(
        evidence_entries=True,
        evidence_status=evidence_status,
        evidence_window={
            "Q3 2026 report": "0_12m",
            "Q4 2026 report": "12_24m",
        }.get(evidence_window, evidence_window),
    )


def latent_context():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current = valid_result()
    current.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    current_payload = json.loads(_v3_qualitative_response(current))
    current_payload["verdict"] = "latent_case"
    current_payload["structured_conclusions"]["trigger"] = json.loads(
        v3_latent_update_response()
    )["thesis"]["structured_conclusions"]["trigger"]
    return ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": current_payload},
        current_facts=[],
        prior_source_ids=("news:old",),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )


def v3_latent_update_response(
    *, evidence_entries=True, evidence_status="unresolved", evidence_window="0_12m"
):
    thesis = valid_result()
    thesis.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    payload = json.loads(_v3_qualitative_response(thesis))
    payload["verdict"] = "latent_case"
    payload["structured_conclusions"]["trigger"] = {
        "claim_id": "operating_trigger",
        "trigger_type": "operating",
        "unresolved_claim_code": "margin_recovery",
        "observable_metric_code": "ebit_margin",
        "threshold_code": "above_10_percent",
        "evidence_window": evidence_window,
        "single_observation_sufficient": True,
        "observation_requirement": "single_observation",
        "source_ids": ["news:new"],
        "limitation_codes": [],
    }
    payload["structured_conclusions"]["trigger_evidence"] = (
        [
            {
                "claim": {
                    "claim_id": "trigger_check",
                    "domain": "margin",
                    "predicate": "observation",
                    "value": "supported",
                    "source_ids": ["news:new"],
                    "limitation_codes": [],
                },
                "status": evidence_status,
                "rationale_code": "persistence_unresolved",
            }
        ]
        if evidence_entries
        else []
    )
    return json.dumps(
        {
            "impact": "thesis_strengthened",
            "summary": "The stored typed trigger was evaluated.",
            "changed_sections": ["triggers_and_break_conditions"],
            "thesis": payload,
        }
    )


def current_thesis(candidate, source_ids=None, context_hash=None):
    return {
        "id": 9,
        "company_id": candidate.company_id,
        "revision": 2,
        "content": valid_result().to_dict(),
        "metadata": {
            "evidence_source_ids": source_ids or [],
            "deterministic_context_sha256": context_hash,
        },
    }


def test_incremental_result_parser_builds_nested_thesis():
    update = parse_thesis_update_result(update_response())

    assert update.impact == "thesis_strengthened"
    assert update.thesis.company_id == 42


def test_full_result_parser_accepts_v3_persisted_thesis():
    thesis = valid_result()
    thesis.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"

    parsed = parse_stock_analysis_result(_v3_qualitative_response(thesis))

    assert parsed.thesis_card_version == "individual-thesis-card-v3-structured-conclusions"
    assert parsed.structured_conclusions is not None


def test_context_builder_supplies_only_new_sources_and_detects_unchanged_context():
    candidate = AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        full_results={"financial": {"revenue_growth": 0.1}},
        research_evidence={
            "as_of": "2026-08-16",
            "documents": [
                {"source_id": "news:old", "text": "Old release"},
                {"source_id": "news:new", "text": "New release"},
            ],
            "insider_transactions": [],
            "ownership_liquidity": {
                "source_ids": ["liquidity:borsdata:42:2026-08-16:20d"]
            },
        },
    )
    repository = MagicMock()
    repository.get_latest.return_value = current_thesis(
        candidate,
        ["news:old"],
        deterministic_context_sha256(candidate),
    )
    repository.list_latest_facts.return_value = []

    context = ThesisUpdateContextBuilder(repository).build(candidate)

    assert context.new_source_ids == (
        "news:new",
        "liquidity:borsdata:42:2026-08-16:20d",
    )
    assert [
        item["source_id"] for item in context.candidate.research_evidence["documents"]
    ] == ["news:new"]
    assert context.deterministic_context_changed is False
    assert context.has_changes is True


def test_update_service_skips_model_when_sources_and_deterministic_context_are_unchanged():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    repository = MagicMock()
    repository.get_latest.return_value = current_thesis(
        candidate,
        context_hash=deterministic_context_sha256(candidate),
    )
    repository.list_latest_facts.return_value = []
    model_adapter = MagicMock()

    outcomes = ThesisUpdateService(
        model_adapter,
        ThesisUpdateContextBuilder(repository),
        MagicMock(),
    ).update([candidate])

    assert outcomes[0].status == "no_new_evidence"
    model_adapter.generate.assert_not_called()


def test_incremental_boundary_persists_material_update_with_linkage_metadata():
    candidate = AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        research_evidence={"documents": [{"source_id": "news:new"}]},
    )
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={
            "id": 9,
            "content": {
                "thesis_card_version": "individual-thesis-card-v3-structured-conclusions"
            },
        },
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=15)

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        v3_update_response(), context, "test-model", {"prior_thesis_revision_id": 9}
    )

    assert accepted.persisted_analysis.analysis_id == 15
    metadata = stock_boundary.persist_response.call_args.kwargs["metadata"]
    assert metadata["thesis_revision_type"] == "incremental_update"
    assert metadata["thesis_update_impact"] == "thesis_strengthened"


def test_incremental_boundary_rejects_changed_sections_for_no_material_change():
    context = MagicMock()
    context.candidate.company_id = 42

    with pytest.raises(StockAnalysisValidationError, match="cannot contain changed sections"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            update_response("no_material_change", ["revenue_drivers"]),
            context,
            "test-model",
        )


def test_incremental_boundary_preserves_thesis_for_no_material_change():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current = valid_result()
    current.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": json.loads(_v3_qualitative_response(current))},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=16)

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        v3_update_response("no_material_change", []), context, "test-model"
    )

    assert accepted.persisted_analysis.analysis_id == 16


def test_legacy_thesis_requires_full_reassessment_before_incremental_update():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    legacy = valid_result().to_dict()
    for field in (
        "evidence_as_of",
        "business_model_profile",
        "margin_expansion_case",
        "timing_assessment",
    ):
        legacy.pop(field)
    legacy["thesis_card_version"] = "individual-thesis-card-v1"
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": legacy},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=20)

    with pytest.raises(StockAnalysisValidationError, match="full reassessment"):
        ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
            update_response("no_material_change", []), context, "test-model"
        )
    stock_boundary.persist_response.assert_not_called()


def test_no_material_change_ignores_calculated_forward_scenario_output():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current_result = valid_result()
    current_result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    current = json.loads(_v3_qualitative_response(current_result))
    current["forward_scenario_analysis"] = {"status": "calculated"}
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": current},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=17)

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        v3_update_response("no_material_change", []), context, "test-model"
    )

    assert accepted.persisted_analysis.analysis_id == 17


def test_no_material_change_reports_differing_thesis_fields():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current_result = valid_result()
    current_result.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    current = json.loads(_v3_qualitative_response(current_result))
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": current},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )
    changed = json.loads(v3_update_response("no_material_change", [])
    )
    changed["thesis"]["structured_conclusions"]["headline_case"]["break_condition"][
        "value"
    ] = "Quietly rewritten thesis."
    response = json.dumps(
        {
            **changed,
        }
    )

    with pytest.raises(StockAnalysisValidationError, match="structured_conclusions"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            response, context, "test-model"
        )


def test_incremental_boundary_rejects_audit_only_v2_thesis():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={
            "id": 9,
            "content": {
                "thesis_card_version": "individual-thesis-card-v2"
            },
        },
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )

    with pytest.raises(StockAnalysisValidationError, match="audit-only"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            v3_update_response("no_material_change", []), context, "test-model"
        )


def test_incremental_boundary_does_not_replace_thesis_when_reassessment_is_required():
    context = MagicMock()
    context.candidate.company_id = 42
    stock_boundary = MagicMock()

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        update_response("full_reassessment_required", ["business_model"]),
        context,
        "test-model",
    )

    assert accepted.persisted_analysis is None
    stock_boundary.persist_response.assert_not_called()


def test_update_prompt_has_incremental_schema_and_current_thesis():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current = valid_result()
    current.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": json.loads(_v3_qualitative_response(current))},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )

    prompt = ThesisUpdatePromptBuilder().build(context)

    assert prompt.schema_name == "thesis_update"
    assert prompt.output_schema["properties"]["impact"]["enum"][0] == (
        "no_material_change"
    )
    assert "Current thesis and provenance" in prompt.user


def test_update_prompt_rejects_audit_only_v2_thesis():
    context = ThesisUpdateContext(
        candidate=AgentCandidate(1, 42, "TEST", "Testbolaget"),
        current_thesis={
            "id": 9,
            "content": {"thesis_card_version": "individual-thesis-card-v2"},
        },
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )

    with pytest.raises(ValueError, match="v2 theses require"):
        ThesisUpdatePromptBuilder().build(context)


def test_incremental_update_must_record_trigger_evaluation():
    context = latent_context()
    response = json.loads(latent_update_response())
    response["thesis"]["structured_conclusions"]["trigger_evidence"] = []

    with pytest.raises(StockAnalysisValidationError, match="must evaluate the stored activation trigger"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            json.dumps(response), context, "test-model"
        )


def test_v3_incremental_update_must_evaluate_structured_trigger():
    current = valid_result()
    current.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    current_payload = json.loads(_v3_qualitative_response(current))
    current_payload["verdict"] = "latent_case"
    current_payload["structured_conclusions"]["trigger"] = json.loads(
        v3_latent_update_response()
    )["thesis"]["structured_conclusions"]["trigger"]
    context = ThesisUpdateContext(
        candidate=AgentCandidate(1, 42, "TEST", "Testbolaget"),
        current_thesis={"id": 9, "content": current_payload},
        current_facts=[],
        prior_source_ids=("news:old",),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )

    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=22)
    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        v3_latent_update_response(), context, "test-model"
    )

    assert accepted.persisted_analysis.analysis_id == 22


def test_v3_incremental_update_cannot_downgrade_to_v2():
    current = valid_result()
    current.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    context = ThesisUpdateContext(
        candidate=AgentCandidate(1, 42, "TEST", "Testbolaget"),
        current_thesis={"id": 9, "content": current.to_dict()},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )

    with pytest.raises(StockAnalysisValidationError, match="require v3"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            update_response(), context, "test-model"
        )


def test_v3_incremental_update_rejects_unchecked_structured_trigger():
    current = valid_result()
    current.thesis_card_version = "individual-thesis-card-v3-structured-conclusions"
    current_payload = json.loads(_v3_qualitative_response(current))
    current_payload["verdict"] = "latent_case"
    current_payload["structured_conclusions"]["trigger"] = json.loads(
        v3_latent_update_response()
    )["thesis"]["structured_conclusions"]["trigger"]
    context = ThesisUpdateContext(
        candidate=AgentCandidate(1, 42, "TEST", "Testbolaget"),
        current_thesis={"id": 9, "content": current_payload},
        current_facts=[],
        prior_source_ids=("news:old",),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )

    with pytest.raises(StockAnalysisValidationError, match="must evaluate"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            v3_latent_update_response(evidence_entries=False), context, "test-model"
        )


def test_unresolved_trigger_evaluation_can_be_recorded_without_changing_thesis():
    context = latent_context()
    response = json.loads(latent_update_response())
    response["impact"] = "no_material_change"
    response["changed_sections"] = []
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=21)

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        json.dumps(response), context, "test-model"
    )

    assert accepted.persisted_analysis.analysis_id == 21


def test_incremental_update_cannot_roll_an_unresolved_trigger_forward():
    context = latent_context()

    with pytest.raises(StockAnalysisValidationError, match="cannot roll"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            latent_update_response(evidence_window="Q4 2026 report"),
            context,
            "test-model",
        )


def test_incremental_update_cannot_leave_a_confirmed_trigger_latent():
    context = latent_context()

    with pytest.raises(StockAnalysisValidationError, match="requires activation"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            latent_update_response(evidence_status="confirms"),
            context,
            "test-model",
        )


def test_update_service_revalidates_stored_response_without_model_call():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    context = MagicMock()
    context.candidate = candidate
    context_builder = MagicMock()
    context_builder.build.return_value = context
    raw_repository = MagicMock()
    raw_repository.get_latest_rejected_incremental_updates.return_value = {
        42: {
            "id": 77,
            "company_id": 42,
            "content": update_response(),
            "created_by": "test-model",
            "metadata": {
                "analysis_mode": "incremental_update",
                "validation_status": "rejected",
                "validation_error": "old boundary defect",
                "prior_thesis_revision_id": 9,
            },
        }
    }
    boundary = MagicMock()
    boundary.persist_response.return_value = MagicMock(
        update=MagicMock(impact="thesis_strengthened"),
        persisted_analysis=MagicMock(analysis_id=18),
    )
    model_adapter = MagicMock()

    outcomes = ThesisUpdateService(
        model_adapter,
        context_builder,
        boundary,
        raw_response_repository=raw_repository,
    ).revalidate_rejected([candidate])

    assert outcomes[0].analysis_id == 18
    model_adapter.generate.assert_not_called()
    metadata = boundary.persist_response.call_args.kwargs["metadata"]
    assert metadata == {"prior_thesis_revision_id": 9, "raw_analysis_id": 77}
    raw_repository.update_raw_validation.assert_called_once_with(77, "accepted")
