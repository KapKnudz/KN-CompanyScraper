import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.context_provenance import deterministic_context_sha256
from kncompanyscraper.analysis.agent.output_schema import CompanyFact
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
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
from tests.test_agent_result_boundary import valid_result


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

    assert context.new_source_ids == ("news:new",)
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
        current_thesis={"id": 9},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=("news:new",),
        deterministic_context_sha256="hash",
        deterministic_context_changed=False,
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=15)

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        update_response(), context, "test-model", {"prior_thesis_revision_id": 9}
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
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": valid_result().to_dict()},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=16)

    accepted = ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        update_response("no_material_change", []), context, "test-model"
    )

    assert accepted.persisted_analysis.analysis_id == 16


def test_no_material_change_reports_differing_thesis_fields():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current = valid_result().to_dict()
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": current},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )
    changed = valid_result()
    changed.one_sentence_thesis = "Quietly rewritten thesis."
    response = json.dumps(
        {
            "impact": "no_material_change",
            "summary": "Nothing changed.",
            "changed_sections": [],
            "thesis": changed.to_dict(),
        }
    )

    with pytest.raises(StockAnalysisValidationError, match="one_sentence_thesis"):
        ThesisUpdateExecutionBoundary(MagicMock()).persist_response(
            response, context, "test-model"
        )


def test_no_material_change_discards_ledger_only_rewrite():
    candidate = AgentCandidate(1, 42, "TEST", "Testbolaget")
    current = valid_result().to_dict()
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": current},
        current_facts=[],
        prior_source_ids=(),
        new_source_ids=(),
        deterministic_context_sha256="hash",
        deterministic_context_changed=True,
    )
    changed = valid_result()
    changed.company_fact_ledger.business_model = [
        CompanyFact("Reconstructed legacy fact.", "analyst_inference", ["news:21"])
    ]
    response = json.dumps(
        {
            "impact": "no_material_change",
            "summary": "Nothing changed.",
            "changed_sections": [],
            "thesis": changed.to_dict(),
        }
    )
    stock_boundary = MagicMock()
    stock_boundary.persist_response.return_value = MagicMock(analysis_id=19)

    ThesisUpdateExecutionBoundary(stock_boundary).persist_response(
        response, context, "test-model"
    )

    persisted_payload = json.loads(stock_boundary.persist_response.call_args.args[0])
    assert persisted_payload["company_fact_ledger"] == current["company_fact_ledger"]


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
    context = ThesisUpdateContext(
        candidate=candidate,
        current_thesis={"id": 9, "content": valid_result().to_dict()},
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
