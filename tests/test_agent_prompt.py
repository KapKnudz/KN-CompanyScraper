from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.output_schema import (
    ManagementClaimAssessment,
    StockAnalysisResult,
    ValuationScenario,
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
    )

    prompt = AgentPromptBuilder().build(candidate)

    assert "Three return engines" in prompt.system
    assert "Follow the steps in order" in prompt.system
    assert '"company_id": 42' in prompt.user
    assert '"operating_margin": 0.08' in prompt.user
    assert '"policy_version": "reverse-dcf-v1"' in prompt.user
    assert '"latest stock price unavailable"' in prompt.user
    assert '"verdict": "reject | watch | latent_case | activated_case"' in prompt.user


def test_stock_analysis_result_serializes_nested_evidence():
    result = StockAnalysisResult(
        company_id=42,
        ticker="TEST",
        company_name="Testbolaget",
        verdict="latent_case",
        confidence="medium",
        one_sentence_thesis="Growth and operating leverage may align after the next report.",
        valuation_scenarios=[
            ValuationScenario(
                label="base",
                implied_value_per_share=125.0,
                expected_return=0.25,
                assumptions=["Revenue grows 15%"],
            )
        ],
        management_credibility_ledger=[
            ManagementClaimAssessment(
                date="2026-Q1",
                claim="Operating costs will normalize.",
                expected_timing="2026-H2",
                observed_outcome=None,
                result="unverifiable",
            )
        ],
    )

    serialized = result.to_dict()

    assert serialized["verdict"] == "latent_case"
    assert serialized["valuation_scenarios"][0]["expected_return"] == 0.25
    assert serialized["management_credibility_ledger"][0]["result"] == "unverifiable"
