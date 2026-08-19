import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.comparative_review import ComparativeReviewService
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from tests.test_comparative_ranking import stored_analysis
from tests.test_forward_scenario import analysis_with_returns


def analyses():
    result = {
        1: stored_analysis(1, analysis_with_returns(), confidence="high"),
        2: stored_analysis(2, analysis_with_returns(), confidence="medium"),
    }
    for company_id, stored in result.items():
        stored["content"].update(
            {
                "one_sentence_thesis": f"Thesis {company_id}",
                "confidence_limitations": [],
                "company_fact_ledger": {},
                "confirming_evidence": [],
                "disconfirming_evidence": [],
                "missing_information": [],
                "citations": [
                    {"source_id": f"report:{company_id}", "claim": "Evidence"}
                ],
            }
        )
    return result


def ranking_run():
    return {
        "id": 60,
        "scores": [
            {"company_id": 1, "rank": 1, "tier": "A"},
            {"company_id": 2, "rank": 2, "tier": "A"},
        ],
        "inputs_summary": {"as_of": "2026-08-18", "analysis_ids": {1: 101, 2: 102}},
    }


def review_payload(source_id="report:1"):
    return {
        "ranking_run_id": 60,
        "cases": [
            {
                "company_id": 1,
                "calibrated_confidence": "low",
                "confidence_change": "lowered",
                "summary": "Evidence is less complete than the peer set.",
                "comparative_evidence_strengths": [],
                "comparative_evidence_limitations": ["Narrow history"],
                "source_ids": [source_id],
            },
            {
                "company_id": 2,
                "calibrated_confidence": "medium",
                "confidence_change": "unchanged",
                "summary": "Evidence remains adequate relative to peers.",
                "comparative_evidence_strengths": ["Consistent reporting"],
                "comparative_evidence_limitations": [],
                "source_ids": ["report:2"],
            },
        ],
        "portfolio_level_observations": ["Evidence depth varies."],
    }


def test_comparative_review_calibrates_confidence_then_uses_deterministic_ranker():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_1",
        model="test-model",
        output_text=json.dumps(review_payload()),
        usage={},
    )
    repository = MagicMock()
    repository.get_by_ranking_run.return_value = None
    repository.save_attempt.return_value = 70
    challenges = MagicMock()
    challenges.unresolved_high_company_ids.return_value = set()

    outcome = ComparativeReviewService(adapter, repository, challenges).review(
        ranking_run(), analyses()
    )

    assert outcome.review_id == 70
    assert outcome.created is True
    by_company = {item.company_id: item for item in outcome.final_ranking.ranks}
    assert by_company[1].evidence_confidence == "low"
    assert by_company[1].tier == "B"
    repository.accept.assert_called_once()
    attach = repository.attach_to_ranking_run.call_args.kwargs
    assert attach["review_id"] == 70


def test_comparative_review_rejects_unknown_company_source():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        response_id="resp_1",
        model="test-model",
        output_text=json.dumps(review_payload("future:99")),
        usage={},
    )
    repository = MagicMock()
    repository.get_by_ranking_run.return_value = None
    repository.save_attempt.return_value = 70

    with pytest.raises(ValueError, match="unknown sources"):
        ComparativeReviewService(adapter, repository, MagicMock()).review(
            ranking_run(), analyses()
        )

    repository.reject.assert_called_once()
    repository.accept.assert_not_called()


def test_rejected_comparative_response_is_revalidated_without_second_model_call():
    repository = MagicMock()
    repository.get_by_ranking_run.return_value = {
        "id": 70,
        "ranking_run_id": 60,
        "status": "rejected",
        "raw_response": json.dumps(review_payload()),
        "created_by": "test-model",
        "metadata": {},
    }
    challenges = MagicMock()
    challenges.unresolved_high_company_ids.return_value = set()
    adapter = MagicMock()

    outcome = ComparativeReviewService(adapter, repository, challenges).review(
        ranking_run(), analyses()
    )

    assert outcome.created is False
    adapter.generate.assert_not_called()
    repository.accept.assert_called_once()
