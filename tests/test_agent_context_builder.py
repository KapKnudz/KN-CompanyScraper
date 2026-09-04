from types import SimpleNamespace

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.agent_packet import AgentCandidatePacket
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


def test_context_candidate_projects_to_explicit_agent_packet_without_losing_evidence():
    candidate = AgentCandidate(
        rank=1,
        company_id=42,
        ticker="TEST",
        name="Testbolaget",
        full_results={"financial": {"source_ids": ["financial:annual:2025"]}},
        research_evidence={
            "documents": [{"source_id": "document:11", "text": "full report"}],
            "insider_transactions": [{"source_id": "insider:1"}],
        },
    )

    packet = AgentCandidatePacket.from_candidate(candidate)

    assert packet.full_results == candidate.full_results
    assert packet.research_evidence == candidate.research_evidence
    assert packet.evidence_catalog["canonical_source_ids"] == [
        "document:11",
        "insider:1",
        "financial:annual:2025",
    ]


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


def test_context_builder_injects_peer_comparison():
    peer_comparison = SimpleNamespace(
        build=lambda company_id, target_terminal_ev_ebit: {
            "company_id": company_id,
            "target_terminal_ev_ebit": target_terminal_ev_ebit,
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

    candidate = AgentContextBuilder(peer_comparison_builder=peer_comparison).build(
        SimpleNamespace(scores=[score]),
        {42: {"valuation": {"ev_ebit_guardrail_low": 8.0, "ev_ebit_guardrail_high": 12.0}}},
    )[0]

    assert candidate.full_results["peer_comparison"] == {
        "company_id": 42,
        "target_terminal_ev_ebit": (8.0, 12.0),
    }


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
