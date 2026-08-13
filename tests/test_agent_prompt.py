import hashlib

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.output_schema import (
    EvidenceCitation,
    ManagementClaimAssessment,
    StockAnalysisResult,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder
from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.valuation.reverse_dcf_skill import ReverseDcfAnalysis


def test_prompt_builder_packages_policy_workflow_and_candidate_evidence():
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        total_score=81.5,
        full_results={
            "financial": FinancialResult(
                operating_margin=0.08,
                net_margin=0.05,
                fcf_margin=0.04,
                revenue_growth=0.18,
                ebit_growth=0.25,
                net_income_growth=0.20,
                roe=0.12,
                roa=0.07,
                debt_to_equity=0.30,
            ),
            "reverse_dcf": ReverseDcfAnalysis(
                status="unavailable",
                policy_version="reverse-dcf-v1",
                model="fcff",
                missing_information=("latest stock price unavailable",),
            ),
        },
        research_evidence={
            "as_of": "2026-08-09",
            "documents": [
                {
                    "source_id": "news:21",
                    "title": "Interim report Q2 2026",
                    "text": "Management expects continued growth.",
                }
            ],
        },
    )

    prompt = AgentPromptBuilder().build(candidate)

    assert "Three return engines" in prompt.system
    assert "Follow the steps in order" in prompt.system
    assert prompt.policy_name == "nordic-case-investing-policy"
    assert prompt.policy_version == "1.17.0"
    assert prompt.policy_sha256 == hashlib.sha256(
        (
            AgentPromptBuilder._read_resource("resources/analyst_policy.md")
            + "\n\n"
            + AgentPromptBuilder._read_resource("resources/analysis_workflow.md")
        ).encode("utf-8")
    ).hexdigest()
    assert f"- Name: `{prompt.policy_name}`" in prompt.system
    assert f"- Version: `{prompt.policy_version}`" in prompt.system
    assert f"- SHA-256: `{prompt.policy_sha256}`" in prompt.system
    assert "full_results.reverse_dcf.implied_expectations" in prompt.system
    assert "Do not calculate or state a forward fair value" in prompt.system
    assert "alternative growth–margin combinations" in prompt.system
    assert "price_fundamental_attribution" in prompt.system
    assert "year-one revenue growth" in prompt.system
    assert "year-five EBIT margin" in prompt.system
    assert "Reverse DCF produces no scalar score" in prompt.system
    assert "copy its `risk_profile` exactly" in prompt.system
    assert "consensus is absent or incomplete" in prompt.system
    assert "Do not independently classify cyclicality" in prompt.system
    assert "discount_rate_sensitivities" in prompt.system
    assert "must not modify inputs" in prompt.system
    assert "Do not invent a numerical return decomposition" in prompt.system
    assert "current price and market-implied operating expectation" in prompt.system
    assert "the valuation assumption" not in prompt.system
    assert "does not mean the company requires no reinvestment" in prompt.system
    assert "plausible`, `demanding`, `unsupported`, or `unassessable`" in prompt.system
    assert "Never apply a universal growth or margin cutoff" in prompt.system
    assert "never scores, probabilities, or generic valuation grades" in prompt.system
    assert "normalize a resolvable path" in prompt.system
    assert "Never invent or abbreviate a path" in prompt.system
    assert "A company buyback is capital allocation" in prompt.system
    assert '"company_id": 42' in prompt.user
    assert '"operating_margin": 0.08' in prompt.user
    assert '"policy_version": "reverse-dcf-v1"' in prompt.user
    assert '"latest stock price unavailable"' in prompt.user
    assert '"source_id": "news:21"' in prompt.user
    assert '"verdict": "reject | watch | latent_case | activated_case"' in prompt.user
    assert '"risk_profile"' in prompt.user
    assert '"reverse_dcf_expectation_assessment"' in prompt.user
    assert '"portfolio_eligibility": "investable | not_investable"' in prompt.user
    assert "`activated_case` may be `investable`" in prompt.system


def test_stock_analysis_result_serializes_nested_evidence():
    result = StockAnalysisResult(
        company_id=42,
        ticker="TEST",
        company_name="Testbolaget",
        verdict="latent_case",
        confidence="medium",
        one_sentence_thesis="Growth and operating leverage may align after the next report.",
        valuation_scenarios=[],
        management_credibility_ledger=[
            ManagementClaimAssessment(
                date="2026-Q1",
                claim="Operating costs will normalize.",
                expected_timing="2026-H2",
                observed_outcome=None,
                result="unverifiable",
                source_ids=["news:21"],
            )
        ],
        citations=[
            EvidenceCitation(
                source_id="news:21",
                claim="Management expects continued growth.",
            )
        ],
    )

    serialized = result.to_dict()

    assert serialized["verdict"] == "latent_case"
    assert serialized["valuation_scenarios"] == []
    assert serialized["management_credibility_ledger"][0]["result"] == "unverifiable"
    assert serialized["citations"][0]["source_id"] == "news:21"
