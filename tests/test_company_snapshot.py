from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from kncompanyscraper.analysis.agent.readiness import AgentReadinessGate
from kncompanyscraper.analysis.base.analysisengine import AnalysisEngine
from kncompanyscraper.analysis.company_snapshot import (
    CompanyDeterministicSnapshotService,
)
from kncompanyscraper.analysis.watchlist.watchlist_analysis_service import (
    WatchlistAnalysisService,
)
from kncompanyscraper.composition import build_company_deterministic_snapshot_service
from kncompanyscraper.models.company import Company


def company(company_id: int, ticker: str = "TEST") -> Company:
    return Company(
        id=company_id,
        name=f"Company {company_id}",
        ticker=ticker,
        mfn_slug=None,
        borsdata_id=None,
        last_updated=None,
        branch_id=None,
    )


class RecordingSkill:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def run(self, selected_company):
        self.calls.append(selected_company.id)
        return {"company_id": selected_company.id, "skill": self.name}


class ActiveCompanyRepository:
    def __init__(self, companies):
        self.companies = companies
        self.active_calls = 0

    def get_active_companies(self):
        self.active_calls += 1
        return list(self.companies)


class RankingRecorder:
    def __init__(self):
        self.calls = []

    def rank(self, companies, results_by_company):
        self.calls.append((companies, results_by_company))
        return SimpleNamespace(scores=[])


def test_snapshot_results_match_watchlist_results_for_same_frozen_inputs():
    companies = [company(1), company(2)]
    skills = [
        RecordingSkill(name)
        for name in (
            "financial",
            "valuation",
            "reverse_dcf",
            "sector_kpis",
            "fundamental_kpis",
            "insider",
        )
    ]
    engine = AnalysisEngine(skills)
    active_repository = ActiveCompanyRepository(companies)
    ranking = RankingRecorder()

    watchlist_run = WatchlistAnalysisService(
        active_repository, engine, ranking
    ).analyze_watchlist()
    snapshot_run = CompanyDeterministicSnapshotService(
        engine,
        readiness_evidence_provider=lambda selected_company: {
            "documents": [{"source_id": f"document:{selected_company.id}"}]
        },
    ).analyze([companies[1]])

    snapshot = snapshot_run.snapshots[0]
    assert snapshot.results == watchlist_run.results_by_company[2]
    assert set(snapshot.results) == {
        "financial",
        "valuation",
        "reverse_dcf",
        "sector_kpis",
        "fundamental_kpis",
        "insider",
    }
    assert snapshot.readiness.company_id == 2
    assert active_repository.active_calls == 1
    assert len(ranking.calls) == 1


def test_snapshot_does_not_load_active_companies_or_write_ranking_or_cohort():
    selected = company(7)
    engine = AnalysisEngine([])

    with (
        patch(
            "kncompanyscraper.repositories.company_repository.CompanyRepository.get_active_companies"
        ) as get_active,
        patch(
            "kncompanyscraper.repositories.ranking_repository.RankingRepository.save_ranking_run"
        ) as save_ranking,
        patch(
            "kncompanyscraper.repositories.agent_cohort_repository.AgentCohortRepository.save"
        ) as save_cohort,
    ):
        result = CompanyDeterministicSnapshotService(engine).analyze([selected])

    assert result.snapshots[0].company_id == 7
    get_active.assert_not_called()
    save_ranking.assert_not_called()
    save_cohort.assert_not_called()


def test_snapshot_work_is_bounded_to_selected_company_count():
    selected = [company(2), company(5)]
    skills = [RecordingSkill(name) for name in ("financial", "insider")]

    CompanyDeterministicSnapshotService(AnalysisEngine(skills)).analyze(selected)

    for skill in skills:
        assert skill.calls == [2, 5]


def test_snapshot_builds_readiness_without_ranking_fields():
    selected = company(42)
    results = {
        "reverse_dcf": {
            "status": "available",
            "current_price": 100.0,
            "current_revenue": 1_000.0,
            "current_shares": 100.0,
            "current_net_debt": 100.0,
            "price_currency": "SEK",
            "financial_currency": "SEK",
        },
        "valuation": {
            "ev_ebit_guardrail_low": 8.0,
            "ev_ebit_guardrail_high": 12.0,
            "raw_ev_ebit": 10.0,
        },
    }
    engine = MagicMock()
    engine.analyze_companies.return_value = {42: results}

    snapshot = CompanyDeterministicSnapshotService(
        engine,
        readiness_gate=AgentReadinessGate(),
        readiness_evidence_provider=lambda _: {
            "documents": [{"source_id": "document:42"}]
        },
    ).analyze([selected]).snapshots[0]

    assert snapshot.readiness.status == "ready"
    assert not hasattr(snapshot, "rank")
    assert not hasattr(snapshot, "total_score")
    assert not hasattr(snapshot, "cohort")
    assert not hasattr(snapshot, "ranking")


def test_snapshot_diagnostics_keep_refresh_deterministic_and_model_time_separate():
    timer_values = iter((10.0, 10.375))
    run = CompanyDeterministicSnapshotService(
        AnalysisEngine([]), timer=lambda: next(timer_values)
    ).analyze([company(1)])

    assert run.diagnostics(
        refresh_duration_seconds=2.5,
        model_duration_seconds=9.0,
    ) == {
        "refresh_duration_seconds": 2.5,
        "deterministic_duration_seconds": 0.375,
        "model_duration_seconds": 9.0,
    }


def test_company_snapshot_composition_does_not_construct_ranking_or_cohort_repositories():
    with (
        patch("kncompanyscraper.repositories.ranking_repository.RankingRepository") as ranking,
        patch("kncompanyscraper.repositories.agent_cohort_repository.AgentCohortRepository") as cohort,
    ):
        build_company_deterministic_snapshot_service()

    ranking.assert_not_called()
    cohort.assert_not_called()
