import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.output_schema import (
    ActivationTriggerSpec,
    AssessmentClaim,
    BusinessModelProfile,
    RevenueResilience,
)
from kncompanyscraper.analysis.agent.result_parser import StockAnalysisValidationError
from tests.test_agent_result_boundary import qualitative_response, valid_result


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "deterministic_contract_failures_2026_09_04.json"
)
MANIFEST_PATH = (
    Path(__file__).parent.parent
    / "analysis-results"
    / "controlled-rollout-2026-09-04"
    / "retry-manifest-2026-09-04.json"
)


def _fixture_cases():
    return json.loads(FIXTURE_PATH.read_text())["cases"]


def _case(ticker):
    return next(case for case in _fixture_cases() if case["ticker"] == ticker)


def _candidate(case):
    candidate_shape = case.get("candidate", {})
    documents = [
        {"source_id": source_id}
        for source_id in candidate_shape.get("documents", ["news:21"])
    ]
    ownership_ids = candidate_shape.get("ownership_liquidity_source_ids")
    research_evidence = {"documents": documents}
    if ownership_ids is not None:
        research_evidence["ownership_liquidity"] = {"source_ids": ownership_ids}
    reverse_status = candidate_shape.get("reverse_dcf_status", "unavailable")
    reverse_dcf = {"status": reverse_status}
    if reverse_status == "available":
        reverse_dcf["expectation_curve"] = [{"revenue_growth": 0.10}]
    return AgentCandidate(
        rank=1,
        company_id=case["company_id"],
        ticker=case["ticker"],
        name=f"{case['ticker']} fixture",
        full_results={"reverse_dcf": reverse_dcf},
        research_evidence=research_evidence,
    )


def _result(case):
    result = valid_result()
    result.company_id = case["company_id"]
    result.ticker = case["ticker"]
    result.company_name = f"{case['ticker']} fixture"
    shape = case["shape"]
    if "ownership_claims" in shape:
        result.ownership_claims = [
            AssessmentClaim(
                claim["statement"],
                "fact",
                claim["source_ids"],
            )
            for claim in shape["ownership_claims"]
        ]
    if "verdict" in shape:
        result.verdict = shape["verdict"]
        result.latent_case_type = shape["latent_case_type"]
        result.activation_trigger = shape["activation_trigger"]
        result.activation_trigger_spec = ActivationTriggerSpec(
            **shape["activation_trigger_spec"]
        )
        result.reverse_dcf_expectation_assessment = shape[
            "reverse_dcf_expectation_assessment"
        ]
        result.reverse_dcf_expectation_rationale = "Fixture rationale."
    if "business_model_profile" in shape:
        result.business_model_profile = BusinessModelProfile(
            **shape["business_model_profile"]
        )
    if "revenue_resilience" in shape:
        result.revenue_resilience = RevenueResilience(**shape["revenue_resilience"])
    return result


@pytest.mark.parametrize("ticker", ["GULD", "CLAS B", "NELLY", "BETS B", "VUXEN", "LIME", "BYGGP"])
def test_2026_09_04_company_failure_shape_is_frozen(ticker):
    case = _case(ticker)

    with pytest.raises(StockAnalysisValidationError) as exc_info:
        AgentExecutionBoundary(MagicMock()).validate_qualitative_response(
            qualitative_response(_result(case)), _candidate(case)
        )

    assert str(exc_info.value) == case["expected_message"]


def test_retry_manifest_has_exactly_seven_active_companies_and_excludes_navigo():
    manifest = json.loads(MANIFEST_PATH.read_text())
    tickers = [company["ticker"] for company in manifest["companies"]]

    assert tickers == ["GULD", "CLAS B", "NELLY", "BETS B", "VUXEN", "LIME", "BYGGP"]
    assert len(tickers) == len(set(tickers)) == 7
    assert all(company["active_company"] for company in manifest["companies"])
    assert "NAVIGO STAM" not in tickers
    assert manifest["model_calls_made_in_workstream"] == 0
    assert manifest["excluded_methodology_cases"] == [
        {
            "company_id": 154,
            "ticker": "NAVIGO STAM",
            "company_name": "Navigo Invest",
            "excluded_from_retry_manifest": True,
            "classification": "holding/property methodology case",
            "preserved_failed_job_id": 1379,
            "reason": "Excluded by remediation plan until approved holding/property valuation methodology exists.",
        }
    ]


def test_retry_manifest_preserves_predecessor_audit_links_without_fresh_jobs():
    manifest = json.loads(MANIFEST_PATH.read_text())

    for company in manifest["companies"]:
        assert company["fresh_job"] == {
            "status": "pending_not_launched_in_workstream_1",
            "job_id": None,
        }
        predecessor = company["preserved_predecessor_job"]
        assert predecessor["status"] == "failed"
        assert predecessor["terminal_failure_reason"] == "validation_attempts_exhausted"
        assert predecessor["failure_stage"] == "qualitative"
        assert predecessor["packet_hash"]
        assert predecessor["prompt_contract_version"] == "qualitative-stage-prompt-v3"
        assert len(predecessor["raw_attempts"]) == 2
        assert all(raw["validation_status"] == "rejected" for raw in predecessor["raw_attempts"])
        assert all(raw["raw_response_sha256"] for raw in predecessor["raw_attempts"])
