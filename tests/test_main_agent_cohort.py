from datetime import date
from unittest.mock import patch

import pytest

from kncompanyscraper.main import _refresh_agent_cohort_snapshot


def test_refresh_agent_cohort_uses_latest_deterministic_run():
    run = {"id": 42, "scores": []}

    with (
        patch(
            "kncompanyscraper.repositories.ranking_repository.RankingRepository"
        ) as rankings,
        patch(
            "kncompanyscraper.repositories.agent_cohort_repository.AgentCohortRepository"
        ) as cohorts,
        patch("kncompanyscraper.analysis.agent_cohort.AgentCohortService") as service,
    ):
        rankings.return_value.get_latest_deterministic_run.return_value = run
        service.return_value.refresh.return_value = (7, object(), True)

        result = _refresh_agent_cohort_snapshot()

    as_of = rankings.return_value.get_latest_deterministic_run.call_args.args[0]
    assert as_of == date.today()
    service.assert_called_once_with(cohorts.return_value)
    service.return_value.refresh.assert_called_once_with(run, as_of=as_of)
    assert result == service.return_value.refresh.return_value


def test_refresh_agent_cohort_requires_deterministic_run():
    with patch(
        "kncompanyscraper.repositories.ranking_repository.RankingRepository"
    ) as rankings:
        rankings.return_value.get_latest_deterministic_run.return_value = None

        with pytest.raises(SystemExit, match="run rank-watchlist first"):
            _refresh_agent_cohort_snapshot()
