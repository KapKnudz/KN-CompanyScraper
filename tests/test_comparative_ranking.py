from dataclasses import asdict
from datetime import date

from kncompanyscraper.analysis.comparative_ranking import ComparativeRankingService
from tests.test_forward_scenario import analysis_with_returns


def stored_analysis(company_id, analysis, *, required_return=0.10, confidence="high"):
    return {
        "analysis_id": company_id + 100,
        "content": {
            "ticker": f"C{company_id}",
            "confidence": confidence,
            "forward_scenario_analysis": asdict(analysis),
        },
        "metadata": {
            "forward_scenario": {
                "required_return": required_return,
            }
        },
    }


def test_comparative_ranking_uses_persisted_forward_results():
    analyses = {
        1: stored_analysis(
            1,
            analysis_with_returns(
                base_low=0.16,
                bear_fundamental_impairment_low=-0.45,
            ),
        ),
        2: stored_analysis(
            2,
            analysis_with_returns(
                base_low=0.12,
                bear_fundamental_impairment_low=-0.15,
            ),
        ),
    }

    snapshot = ComparativeRankingService().build(analyses, as_of=date(2026, 8, 31))

    assert snapshot.as_of == "2026-08-31"
    assert [item.company_id for item in snapshot.ranks] == [2, 1]
    assert snapshot.analysis_ids == {1: 101, 2: 102}


def test_comparative_ranking_keeps_missing_results_visible():
    analyses = {
        1: {
            "analysis_id": 101,
            "content": {"ticker": "C1", "confidence": "medium"},
            "metadata": {},
        }
    }

    snapshot = ComparativeRankingService().build(analyses, as_of=date(2026, 8, 31))

    assert snapshot.ranks[0].tier == "IE"
    assert "forward scenario analysis is missing" in snapshot.ranks[0].flags


def test_comparative_ranking_requires_persisted_hurdle():
    stored = stored_analysis(1, analysis_with_returns())
    stored["metadata"]["forward_scenario"]["required_return"] = None

    snapshot = ComparativeRankingService().build({1: stored}, as_of=date(2026, 8, 31))

    assert snapshot.ranks[0].tier == "IE"
    assert "required return is unavailable" in snapshot.ranks[0].flags


def test_comparative_ranking_blocks_open_high_severity_challenge():
    stored = stored_analysis(1, analysis_with_returns())

    snapshot = ComparativeRankingService().build(
        {1: stored},
        as_of=date(2026, 8, 31),
        blocked_company_ids={1},
    )

    assert snapshot.ranks[0].tier == "RESEARCH"
    assert not snapshot.ranks[0].actionable
