from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from kncompanyscraper.cli.agent import _cmd_adjudicate_monthly_ranking
from kncompanyscraper import composition, scheduler


def test_agent_cohort_candidates_passes_ranking_to_context_builder():
    ranking = MagicMock()
    results_by_company = {7: {"financial": "result"}}
    run = SimpleNamespace(ranking=ranking, results_by_company=results_by_company)
    context_builder = MagicMock()

    composition.build_agent_cohort_candidates(
        run, limit=1, context_builder=context_builder
    )

    context_builder.build_shortlist.assert_called_once_with(
        ranking, results_by_company, limit=1
    )


def test_adjudicate_monthly_ranking_supplies_challenge_repository():
    ranking_run = {"id": 42, "scores": []}

    with (
        patch(
            "kncompanyscraper.repositories.ranking_repository.RankingRepository"
        ) as rankings,
        patch(
            "kncompanyscraper.repositories.analysis_repository.AnalysisRepository"
        ) as analyses,
        patch(
            "kncompanyscraper.repositories.comparative_review_repository.ComparativeReviewRepository"
        ) as reviews,
        patch(
            "kncompanyscraper.repositories.thesis_challenge_repository.ThesisChallengeRepository"
        ) as challenges,
        patch("kncompanyscraper.composition.build_agent_model_adapter") as adapter,
        patch(
            "kncompanyscraper.composition.build_comparative_review_service"
        ) as service,
    ):
        rankings.return_value.get_ranking_run.return_value = ranking_run
        service.return_value.review.return_value = SimpleNamespace(
            review=SimpleNamespace(cases=[])
        )

        _cmd_adjudicate_monthly_ranking(
            SimpleNamespace(
                ranking_run_id=42,
                provider="openai",
                model=None,
                reasoning_effort=None,
            )
        )

    service.assert_called_once_with(adapter.return_value)
    service.return_value.review.assert_called_once_with(
        ranking_run, analyses.return_value.get_latest_validated_stock_analyses.return_value
    )


def test_scheduler_borsdata_run_uses_canonical_ingestion_factory():
    companies = [MagicMock()]
    mapping = MagicMock()
    job = MagicMock()
    ingestion = MagicMock()

    with (
        patch.object(scheduler.repository, "get_active_companies", side_effect=[companies, companies]),
        patch("kncompanyscraper.scheduler.BorsdataClient") as client,
        patch("kncompanyscraper.scheduler.BorsdataInstrumentMappingService", return_value=mapping),
        patch("kncompanyscraper.composition.build_borsdata_ingestion_service", return_value=ingestion) as factory,
        patch("kncompanyscraper.scheduler.BorsdataJob", return_value=job) as job_factory,
        patch("kncompanyscraper.scheduler.JobRepository") as job_repository,
    ):
        scheduler.run_borsdata_once()

    mapping.map_companies.assert_called_once_with(companies)
    factory.assert_called_once_with()
    job_factory.assert_called_once_with(ingestion, job_repository.return_value)
    job.run.assert_called_once_with(companies)
