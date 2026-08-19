from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.analysis.agent_cohort import AgentCohortService


def deterministic_run(company_ids, run_id=10):
    return {
        "id": run_id,
        "scores": [
            {"company_id": company_id, "rank_eligible": True}
            for company_id in company_ids
        ],
    }


def test_cohort_adds_top_30_immediately():
    repository = MagicMock()
    repository.get_for_month.return_value = None
    repository.get_latest_before.return_value = None
    repository.save.return_value = (5, True)

    snapshot_id, snapshot, created = AgentCohortService(repository).refresh(
        deterministic_run(range(1, 36)),
        as_of=date(2026, 8, 18),
    )

    assert snapshot_id == 5
    assert created is True
    assert snapshot.top_company_ids == tuple(range(1, 31))
    assert [member.company_id for member in snapshot.members] == list(range(1, 31))
    assert all(member.status == "entrant" for member in snapshot.members)


def test_cohort_retains_misses_for_two_months_and_drops_on_third():
    repository = MagicMock()
    repository.get_for_month.return_value = None
    repository.save.return_value = (6, True)
    repository.get_latest_before.return_value = {
        "members": [
            {
                "company_id": 99,
                "status": "grace",
                "deterministic_rank": 31,
                "consecutive_misses": 1,
                "entered_month": "2026-06-01",
            },
            {
                "company_id": 98,
                "status": "grace",
                "deterministic_rank": 32,
                "consecutive_misses": 2,
                "entered_month": "2026-05-01",
            },
        ]
    }

    _, snapshot, _ = AgentCohortService(repository).refresh(
        deterministic_run(range(1, 31)),
        as_of=date(2026, 8, 18),
    )

    member_ids = [member.company_id for member in snapshot.members]
    assert 99 in member_ids
    assert 98 not in member_ids
    retained = next(member for member in snapshot.members if member.company_id == 99)
    assert retained.status == "grace"
    assert retained.consecutive_misses == 2
    assert len(snapshot.members) == 31


def test_cohort_same_month_is_immutable():
    repository = MagicMock()
    stored = {
        "id": 5,
        "snapshot_month": date(2026, 8, 1),
        "deterministic_run_id": 10,
        "eligible_universe_company_ids": [1],
        "top_company_ids": [1],
        "members": [
            {
                "company_id": 1,
                "status": "entrant",
                "deterministic_rank": 1,
                "consecutive_misses": 0,
                "entered_month": "2026-08-01",
            }
        ],
        "policy_version": "agent-cohort-v1",
        "target_size": 30,
        "grace_months": 3,
    }
    repository.get_for_month.return_value = stored

    snapshot_id, snapshot, created = AgentCohortService(repository).refresh(
        deterministic_run([2], run_id=11),
        as_of=date(2026, 8, 25),
    )

    assert snapshot_id == 5
    assert created is False
    assert snapshot.top_company_ids == (1,)
    repository.save.assert_not_called()
