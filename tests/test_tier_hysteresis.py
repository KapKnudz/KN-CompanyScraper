from datetime import date

from kncompanyscraper.analysis.comparative_ranking import (
    ComparativeRankingService,
    MonthlyTierHysteresisPolicy,
)
from tests.test_comparative_ranking import stored_analysis
from tests.test_forward_scenario import analysis_with_returns


def proposed_rank(base_low=0.09, base_high=0.12, blocked=False):
    stored = stored_analysis(
        1,
        analysis_with_returns(base_low=base_low, base_high=base_high),
        required_return=0.10,
    )
    return ComparativeRankingService().build(
        {1: stored},
        as_of=date(2026, 9, 1),
        blocked_company_ids={1} if blocked else set(),
    ).ranks


def previous_run(*, pending=None):
    return {
        "scores": [{"company_id": 1, "tier": "A", "economic_tier": "A"}],
        "inputs_summary": {
            "effective_economic_tiers": {"1": "A"},
            "pending_tier_transitions": pending or {},
        },
    }


def test_first_near_boundary_move_is_held_and_marked_pending():
    decision = MonthlyTierHysteresisPolicy().decide(
        proposed_rank(), {1: 0.10}, previous_run()
    )

    assert decision.economic_tier_overrides == {1: "A"}
    assert decision.pending_transitions["1"]["target_tier"] == "B"

    stored = stored_analysis(
        1,
        analysis_with_returns(base_low=0.09, base_high=0.12),
        required_return=0.10,
    )
    effective = ComparativeRankingService().build(
        {1: stored},
        as_of=date(2026, 9, 1),
        economic_tier_overrides=decision.economic_tier_overrides,
    ).ranks[0]
    assert effective.economic_tier == "A"
    assert effective.tier == "A"
    assert "economic tier held" in effective.flags[0]


def test_second_consecutive_near_boundary_move_is_applied():
    decision = MonthlyTierHysteresisPolicy().decide(
        proposed_rank(),
        {1: 0.10},
        previous_run(
            pending={
                "1": {"from_tier": "A", "target_tier": "B", "observed_count": 1}
            }
        ),
    )

    assert decision.economic_tier_overrides == {}
    assert decision.pending_transitions == {}


def test_reversion_clears_pending_transition():
    decision = MonthlyTierHysteresisPolicy().decide(
        proposed_rank(base_low=0.11),
        {1: 0.10},
        previous_run(
            pending={
                "1": {"from_tier": "A", "target_tier": "B", "observed_count": 1}
            }
        ),
    )

    assert decision.economic_tier_overrides == {}
    assert decision.pending_transitions == {}


def test_large_move_and_critic_block_apply_immediately():
    policy = MonthlyTierHysteresisPolicy()

    large = policy.decide(
        proposed_rank(base_low=0.05), {1: 0.10}, previous_run()
    )
    blocked = policy.decide(
        proposed_rank(blocked=True), {1: 0.10}, previous_run()
    )

    assert large.economic_tier_overrides == {}
    assert blocked.economic_tier_overrides == {}
