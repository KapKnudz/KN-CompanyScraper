from datetime import date
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.portfolio_selection import PortfolioSelectionService


def _score(company_id, *, risk_profile="slightly_cyclical"):
    return SimpleNamespace(
        company_id=company_id,
        ticker=f"T{company_id}",
        name=f"Company {company_id}",
        rank_eligible=True,
        eligibility_reasons=[],
        risk_profile=risk_profile,
    )


def _analysis(company_id, *, risk_profile="slightly_cyclical", evidence_as_of="2026-08-12"):
    return {
        "analysis_id": 100 + company_id,
        "company_id": company_id,
        "content": {
            "analysis_status": "complete",
            "verdict": "activated_case",
            "confidence": "high",
            "one_sentence_thesis": f"Case {company_id} is active.",
            "portfolio_eligibility": "investable",
            "portfolio_reason_code": "investable",
            "reconsideration_trigger": None,
            "reverse_dcf_expectation_assessment": "plausible",
            "risk_profile": risk_profile,
            "thesis_break_conditions": ["Growth stalls."],
        },
        "metadata": {
            "validation_status": "accepted",
            "evidence_as_of": evidence_as_of,
        },
    }


def test_selects_five_equal_weight_investable_cases_in_ranking_order():
    ranking = SimpleNamespace(scores=[_score(company_id) for company_id in range(1, 7)])
    analyses = {company_id: _analysis(company_id) for company_id in range(1, 7)}

    result = PortfolioSelectionService().select(
        ranking,
        analyses,
        as_of=date(2026, 8, 12),
    )

    assert result.status == "ready"
    assert [holding.company_id for holding in result.selected] == [1, 2, 3, 4, 5]
    assert all(holding.target_weight == pytest.approx(0.20) for holding in result.selected)
    assert result.missing_slots == 0


def test_does_not_force_weights_when_fewer_than_five_cases_qualify():
    ranking = SimpleNamespace(scores=[_score(1), _score(2), _score(3)])
    analyses = {
        1: _analysis(1),
        2: _analysis(2, evidence_as_of="2026-06-01"),
    }

    result = PortfolioSelectionService().select(
        ranking,
        analyses,
        as_of=date(2026, 8, 12),
    )

    assert result.status == "not_ready"
    assert [holding.company_id for holding in result.selected] == [1]
    assert result.selected[0].target_weight is None
    assert result.missing_slots == 4
    assert [item.reason_code for item in result.excluded_finalists] == [
        "stale_analysis",
        "no_validated_analysis",
    ]


def test_limits_high_risk_holdings_to_two():
    ranking = SimpleNamespace(scores=[_score(company_id) for company_id in range(1, 7)])
    analyses = {
        company_id: _analysis(company_id, risk_profile="cyclical_or_other_risk")
        for company_id in range(1, 7)
    }

    result = PortfolioSelectionService().select(
        ranking,
        analyses,
        as_of=date(2026, 8, 12),
    )

    assert len(result.selected) == 2
    assert all(holding.target_weight is None for holding in result.selected)
    assert all(
        item.reason_code == "risk_concentration"
        for item in result.excluded_finalists
    )


def test_excludes_accepted_analysis_from_old_contract():
    ranking = SimpleNamespace(scores=[_score(1)])
    analysis = _analysis(1)
    del analysis["content"]["portfolio_eligibility"]

    result = PortfolioSelectionService().select(
        ranking,
        {1: analysis},
        as_of=date(2026, 8, 12),
    )

    assert result.excluded_finalists[0].reason_code == "analysis_contract_outdated"


def test_excludes_blocked_analysis_without_treating_watch_as_verdict():
    ranking = SimpleNamespace(scores=[_score(1)])
    analysis = _analysis(1)
    analysis["content"]["analysis_status"] = "evidence_blocked"
    analysis["content"]["verdict"] = "watch"

    result = PortfolioSelectionService().select(
        ranking,
        {1: analysis},
        as_of=date(2026, 8, 12),
    )

    assert result.excluded_finalists[0].reason_code == "analysis_incomplete"


def test_excludes_investable_case_without_classified_business_risk():
    ranking = SimpleNamespace(scores=[_score(1)])
    analysis = _analysis(1, risk_profile="unclassified")

    result = PortfolioSelectionService().select(
        ranking,
        {1: analysis},
        as_of=date(2026, 8, 12),
    )

    assert result.selected == ()
    assert result.excluded_finalists[0].reason_code == "risk_unclassified"
