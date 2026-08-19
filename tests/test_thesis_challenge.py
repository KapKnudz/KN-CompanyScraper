import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.thesis_challenge import (
    ThesisChallengeResponseService,
    ThesisChallengeService,
)
from tests.test_thesis_update import update_response


def challenge_payload(source_id="report:1"):
    return {
        "challenged_claim": "Margins can reach 15%.",
        "severity": "high",
        "verdict": "revision_required",
        "summary": "The margin claim exceeds demonstrated operating evidence.",
        "methodology_findings": ["Peak margin lacks a cost bridge."],
        "evidence_findings": [
            {"statement": "Historical margin was lower.", "source_ids": [source_id]}
        ],
        "missing_evidence": ["Segment cost bridge"],
        "decision_impact": "The base return band may no longer clear its hurdle.",
    }


def test_challenge_is_linked_to_exact_revision_and_original_evidence():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_1",
        model="test-model",
        output_text=json.dumps(challenge_payload()),
        usage={"total_tokens": 100},
    )
    repository = MagicMock()
    repository.save.return_value = 77
    thesis = {
        "id": 9,
        "company_id": 42,
        "revision": 3,
        "evidence_as_of": "2026-08-01",
        "content": {"ticker": "TEST", "one_sentence_thesis": "Margins expand."},
        "metadata": {},
    }
    evidence = {"documents": [{"source_id": "report:1", "text": "Report"}]}

    challenge_id, result = ThesisChallengeService(adapter, repository).challenge(
        thesis, evidence, "Why is a 15% margin defensible?"
    )

    assert challenge_id == 77
    assert result.severity == "high"
    assert repository.save.call_args.kwargs["thesis_revision_id"] == 9
    assert repository.save.call_args.kwargs["company_id"] == 42
    assert repository.save.call_args.kwargs["metadata"][
        "original_evidence_source_ids"
    ] == ["report:1"]


def test_challenge_rejects_citations_outside_original_evidence():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_1",
        model="test-model",
        output_text=json.dumps(challenge_payload("future:2")),
        usage={},
    )
    repository = MagicMock()
    thesis = {
        "id": 9,
        "company_id": 42,
        "revision": 3,
        "content": {},
        "metadata": {},
    }

    with pytest.raises(ValueError, match="unknown original evidence"):
        ThesisChallengeService(adapter, repository).challenge(
            thesis,
            {"documents": [{"source_id": "report:1"}]},
            "Challenge this.",
        )

    repository.save.assert_not_called()


def open_challenge(raw_analysis_id=None):
    return {
        "id": 7,
        "company_id": 42,
        "thesis_revision_id": 9,
        "question": "Is the margin evidence sufficient?",
        "challenged_claim": "Margins can reach 15%.",
        "severity": "high",
        "verdict": "revision_required",
        "status": "open",
        "response_raw_analysis_id": raw_analysis_id,
        "content": {"result": challenge_payload()},
    }


def challenged_thesis():
    from tests.test_agent_result_boundary import valid_result

    return {
        "id": 9,
        "company_id": 42,
        "revision": 2,
        "content": valid_result().to_dict(),
        "metadata": {"evidence_source_ids": ["report:1"]},
    }


def response_candidate():
    return AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        research_evidence={"documents": [{"source_id": "report:1"}]},
    )


def test_challenge_response_persists_revision_before_resolving_challenge():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_2",
        model="test-model",
        output_text=update_response("thesis_weakened", ["revenue_growth_case"]),
        usage={"total_tokens": 80},
    )
    boundary = MagicMock()
    boundary.persist_response.return_value = MagicMock(
        update=MagicMock(impact="thesis_weakened", summary="Margin case revised."),
        persisted_analysis=MagicMock(analysis_id=15),
    )
    challenge_repository = MagicMock()
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.return_value = 81

    outcome = ThesisChallengeResponseService(
        adapter,
        boundary,
        challenge_repository,
        raw_repository,
    ).respond(
        open_challenge(),
        challenged_thesis(),
        response_candidate(),
        {"documents": [{"source_id": "report:1"}]},
        [],
    )

    assert outcome.status == "revised"
    assert outcome.analysis_id == 15
    challenge_repository.attach_response_attempt.assert_called_once_with(7, 81)
    challenge_repository.resolve_with_response.assert_called_once_with(
        7, "revised", "Margin case revised.", 15
    )
    metadata = boundary.persist_response.call_args.kwargs["metadata"]
    assert metadata["challenge_id"] == 7
    assert metadata["prior_thesis_revision_id"] == 9
    assert metadata["raw_analysis_id"] == 81


def test_challenge_response_reuses_stored_raw_response_without_model_call():
    adapter = MagicMock()
    boundary = MagicMock()
    boundary.persist_response.return_value = MagicMock(
        update=MagicMock(impact="no_material_change", summary="Thesis survives."),
        persisted_analysis=MagicMock(analysis_id=16),
    )
    challenge_repository = MagicMock()
    raw_repository = MagicMock()
    raw_repository.get_stock_analysis_raw.return_value = {
        "id": 81,
        "content": update_response("no_material_change", []),
        "created_by": "test-model",
        "metadata": {"analysis_mode": "challenge_response"},
    }

    outcome = ThesisChallengeResponseService(
        adapter,
        boundary,
        challenge_repository,
        raw_repository,
    ).respond(
        open_challenge(81),
        challenged_thesis(),
        response_candidate(),
        {"documents": [{"source_id": "report:1"}]},
        [],
    )

    assert outcome.status == "upheld"
    adapter.generate.assert_not_called()
    raw_repository.save_stock_analysis_raw.assert_not_called()
    challenge_repository.resolve_with_response.assert_called_once_with(
        7, "upheld", "Thesis survives.", 16
    )


def test_full_reassessment_leaves_challenge_open():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_2",
        model="test-model",
        output_text=update_response("full_reassessment_required", ["business_model"]),
        usage={},
    )
    boundary = MagicMock()
    boundary.persist_response.return_value = MagicMock(
        update=MagicMock(
            impact="full_reassessment_required",
            summary="Original evidence cannot settle the challenge.",
        ),
        persisted_analysis=None,
    )
    challenge_repository = MagicMock()
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.return_value = 82

    outcome = ThesisChallengeResponseService(
        adapter,
        boundary,
        challenge_repository,
        raw_repository,
    ).respond(
        open_challenge(),
        challenged_thesis(),
        response_candidate(),
        {"documents": [{"source_id": "report:1"}]},
        [],
    )

    assert outcome.status == "full_reassessment_required"
    challenge_repository.resolve_with_response.assert_not_called()


def test_failed_challenge_response_validation_leaves_challenge_open():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_2",
        model="test-model",
        output_text=update_response(),
        usage={},
    )
    boundary = MagicMock()
    boundary.persist_response.side_effect = ValueError("invalid response")
    challenge_repository = MagicMock()
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.return_value = 83

    with pytest.raises(ValueError, match="invalid response"):
        ThesisChallengeResponseService(
            adapter,
            boundary,
            challenge_repository,
            raw_repository,
        ).respond(
            open_challenge(),
            challenged_thesis(),
            response_candidate(),
            {"documents": [{"source_id": "report:1"}]},
            [],
        )

    raw_repository.update_raw_validation.assert_called_once_with(
        83, "rejected", "invalid response"
    )
    challenge_repository.resolve_with_response.assert_not_called()


def test_challenge_response_finishes_resolution_for_already_persisted_revision():
    thesis = challenged_thesis()
    thesis.update({"id": 10, "source_analysis_id": 16})
    thesis["metadata"].update(
        {
            "challenge_id": 7,
            "prior_thesis_revision_id": 9,
            "thesis_update_impact": "thesis_weakened",
            "thesis_update_summary": "Margin case revised.",
        }
    )
    challenge_repository = MagicMock()
    adapter = MagicMock()

    outcome = ThesisChallengeResponseService(
        adapter,
        MagicMock(),
        challenge_repository,
        MagicMock(),
    ).respond(
        open_challenge(81),
        thesis,
        response_candidate(),
        {"documents": [{"source_id": "report:1"}]},
        [],
    )

    assert outcome.status == "revised"
    adapter.generate.assert_not_called()
    challenge_repository.resolve_with_response.assert_called_once_with(
        7, "revised", "Margin case revised.", 16
    )


def test_challenge_response_rejects_unlinked_newer_thesis():
    thesis = challenged_thesis()
    thesis["id"] = 10
    thesis["metadata"] = {}

    with pytest.raises(ValueError, match="older thesis revision"):
        ThesisChallengeResponseService(
            MagicMock(), MagicMock(), MagicMock(), MagicMock()
        ).respond(
            open_challenge(),
            thesis,
            response_candidate(),
            {"documents": [{"source_id": "report:1"}]},
            [],
        )
