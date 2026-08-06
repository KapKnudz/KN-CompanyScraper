import json
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.output_schema import (
    ManagementClaimAssessment,
    StockAnalysisResult,
    ValuationScenario,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)


def valid_result() -> StockAnalysisResult:
    return StockAnalysisResult(
        company_id=42,
        ticker="TEST",
        company_name="Testbolaget",
        verdict="watch",
        confidence="medium",
        one_sentence_thesis="Evidence is incomplete.",
        expected_return_components={
            "revenue_growth": None,
            "margin_change": None,
            "multiple_change": None,
            "balance_sheet_change": None,
            "dilution": None,
        },
        valuation_scenarios=[
            ValuationScenario(
                label="base",
                implied_value_per_share=None,
                expected_return=None,
                assumptions=["Current evidence is insufficient"],
            )
        ],
        management_credibility_ledger=[
            ManagementClaimAssessment(
                date="2026-Q2",
                claim="Margins will improve.",
                expected_timing=None,
                observed_outcome=None,
                result="unverifiable",
            )
        ],
    )


def valid_response() -> str:
    return json.dumps(valid_result().to_dict())


def test_parser_builds_nested_result_dataclasses():
    result = parse_stock_analysis_result(valid_response())

    assert result.verdict == "watch"
    assert result.valuation_scenarios[0].label == "base"
    assert result.management_credibility_ledger[0].result == "unverifiable"


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
    candidate = AgentCandidate(rank=1, company_id=42, ticker="test", name="Testbolaget")

    persisted = AgentExecutionBoundary(repository).persist_response(
        valid_response(),
        candidate,
        created_by="test-model",
        metadata={"prompt_version": 1},
    )

    assert persisted.analysis_id == 99
    repository.save_stock_analysis.assert_called_once_with(
        persisted.result,
        created_by="test-model",
        metadata={"prompt_version": 1},
    )
