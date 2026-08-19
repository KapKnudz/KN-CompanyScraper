from types import SimpleNamespace

from kncompanyscraper.analysis.agent.agent_context_builder import AgentContextBuilder


def test_context_builder_preserves_deterministic_ranking_context():
    score = SimpleNamespace(
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        ranking_model="general",
        rank_eligible=True,
        eligibility_reasons=[],
        total_score=50.0,
        quality_score=60.0,
        growth_score=55.0,
        valuation_score=45.0,
        balance_sheet_score=50.0,
        data_quality="medium",
        flags=["low_data_quality"],
        candidate_reason=None,
        positives=["Profitable"],
        negatives=["Weak margin trend"],
        missing_data=[],
    )
    ranking = SimpleNamespace(scores=[score])

    candidate = AgentContextBuilder().build(ranking, {})[0]

    assert candidate.positives == ["Profitable"]
    assert candidate.negatives == ["Weak margin trend"]
    assert candidate.flags == ["low_data_quality"]


def test_context_builder_injects_persisted_cyclicality_consensus():
    repository = SimpleNamespace(
        get_consensus=lambda company_id: {
            "status": "complete",
            "company_id": company_id,
            "risk_profile": "slightly_cyclical",
        }
    )
    score = SimpleNamespace(
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        ranking_model="general",
        rank_eligible=True,
        eligibility_reasons=[],
        total_score=50.0,
        quality_score=60.0,
        growth_score=55.0,
        valuation_score=45.0,
        balance_sheet_score=50.0,
        data_quality="medium",
        flags=[],
        candidate_reason=None,
        positives=[],
        negatives=[],
        missing_data=[],
    )

    candidate = AgentContextBuilder(cyclicality_repository=repository).build(
        SimpleNamespace(scores=[score]),
        {42: {"reverse_dcf": {}}},
    )[0]

    assert candidate.full_results["cyclicality_consensus"]["company_id"] == 42
    assert candidate.full_results["reverse_dcf"] == {}


def test_context_builder_injects_structured_financial_history():
    financial_evidence = SimpleNamespace(build=lambda company_id: {"company": company_id})
    score = SimpleNamespace(
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        ranking_model="general",
        rank_eligible=True,
        eligibility_reasons=[],
        total_score=50.0,
        quality_score=60.0,
        growth_score=55.0,
        valuation_score=45.0,
        balance_sheet_score=50.0,
        data_quality="medium",
        flags=[],
        candidate_reason=None,
        positives=[],
        negatives=[],
        missing_data=[],
    )

    candidate = AgentContextBuilder(
        financial_evidence_builder=financial_evidence
    ).build(SimpleNamespace(scores=[score]), {})[0]

    assert candidate.full_results["financial_history"] == {"company": 42}


def test_context_builder_uses_persisted_cohort_order():
    def score(company_id):
        return SimpleNamespace(
            company_id=company_id,
            ticker=f"C{company_id}",
            name=f"Company {company_id}",
            ranking_model="general",
            rank_eligible=True,
            eligibility_reasons=[],
            total_score=50.0,
            quality_score=50.0,
            growth_score=50.0,
            valuation_score=50.0,
            balance_sheet_score=50.0,
            data_quality="medium",
            flags=[],
            candidate_reason=None,
            positives=[],
            negatives=[],
            missing_data=[],
        )

    candidates = AgentContextBuilder().build_shortlist(
        SimpleNamespace(scores=[score(1), score(2), score(3)]),
        {},
        company_ids=(3, 1),
    )

    assert [candidate.company_id for candidate in candidates] == [3, 1]
    assert [candidate.rank for candidate in candidates] == [3, 1]
