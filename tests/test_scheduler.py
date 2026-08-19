from datetime import date, time
from unittest.mock import MagicMock, patch

from kncompanyscraper import scheduler


def test_run_borsdata_once_uses_active_companies_and_job():
    companies = [MagicMock()]

    with (
        patch.object(scheduler.repository, "get_active_companies", return_value=companies),
        patch("kncompanyscraper.scheduler.BorsdataClient"),
        patch("kncompanyscraper.scheduler.BorsdataInstrumentMappingService") as mapping,
        patch("kncompanyscraper.scheduler.BorsdataIngestionService") as ingestion,
        patch("kncompanyscraper.scheduler.JobRepository") as job_repository,
        patch("kncompanyscraper.scheduler.BorsdataJob") as job,
    ):
        result = scheduler.run_borsdata_once()

    mapping.return_value.map_companies.assert_called_once_with(companies)
    job.assert_called_once_with(ingestion.return_value, job_repository.return_value)
    job.return_value.run.assert_called_once_with(companies)
    assert result == job.return_value.run.return_value


def test_run_borsdata_insiders_once_uses_active_companies_and_job():
    companies = [MagicMock()]

    with (
        patch.object(scheduler.repository, "get_active_companies", return_value=companies),
        patch("kncompanyscraper.scheduler.BorsdataClient") as client,
        patch("kncompanyscraper.scheduler.InsiderRepository") as insider_repository,
        patch("kncompanyscraper.scheduler.JobRepository") as job_repository,
        patch("kncompanyscraper.scheduler.BorsdataInsiderJob") as job,
    ):
        result = scheduler.run_borsdata_insiders_once()

    job.assert_called_once_with(
        client.return_value,
        insider_repository.return_value,
        job_repository.return_value,
    )
    job.return_value.run.assert_called_once_with(companies)
    assert result == job.return_value.run.return_value


def test_run_benchmark_sync_once_uses_incremental_job():
    with (
        patch("kncompanyscraper.scheduler.NasdaqBenchmarkClient") as client,
        patch("kncompanyscraper.scheduler.BenchmarkRepository") as repository,
        patch("kncompanyscraper.scheduler.BenchmarkSyncJob") as job,
    ):
        job.return_value.run.return_value = MagicMock(
            synced_count=3,
            stored_through=date(2026, 8, 17),
            omitted_zero_dates=(),
        )
        result = scheduler.run_benchmark_sync_once()

    job.assert_called_once_with(client.return_value, repository.return_value)
    job.return_value.run.assert_called_once_with()
    assert result is job.return_value.run.return_value


def test_run_ranking_challenger_performance_once_uses_isolated_repository():
    with (
        patch(
            "kncompanyscraper.scheduler.RankingChallengerRepository"
        ) as repository,
        patch(
            "kncompanyscraper.scheduler.RankingChallengerPerformanceEvaluator"
        ) as evaluator,
        patch(
            "kncompanyscraper.scheduler.RankingChallengerPerformanceJob"
        ) as job,
    ):
        result = scheduler.run_ranking_challenger_performance_once()

    job.assert_called_once_with(repository.return_value, evaluator.return_value)
    job.return_value.run.assert_called_once_with()
    assert result is job.return_value.run.return_value


def test_configure_schedule_adds_news_and_nightly_borsdata_jobs(monkeypatch):
    monkeypatch.setattr(scheduler.config, "SCRAPE_INTERVAL_MINUTES", 30)
    monkeypatch.setattr(scheduler.config, "BORSDATA_SYNC_TIME", "02:00")
    monkeypatch.setattr(scheduler.config, "BORSDATA_INSIDER_SYNC_TIME", "03:00")
    monkeypatch.setattr(scheduler.config, "COMPARATIVE_RANKING_TIME", "04:00")
    monkeypatch.setattr(scheduler.config, "BENCHMARK_SYNC_TIME", "04:10")
    monkeypatch.setattr(scheduler.config, "RANKING_PERFORMANCE_TIME", "04:15")
    scheduler.schedule.clear()

    try:
        scheduler.configure_schedule()
        jobs = scheduler.schedule.get_jobs()

        assert len(jobs) == 7
        assert any(job.job_func.func is scheduler.run_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_borsdata_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_borsdata_insiders_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_comparative_ranking_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_benchmark_sync_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_ranking_performance_once for job in jobs)
        assert any(
            job.job_func.func is scheduler.run_ranking_challenger_performance_once
            for job in jobs
        )
        assert any(job.at_time == time(2, 0) for job in jobs)
        assert any(job.at_time == time(3, 0) for job in jobs)
        assert any(job.at_time == time(4, 0) for job in jobs)
        assert any(job.at_time == time(4, 10) for job in jobs)
        assert any(job.at_time == time(4, 15) for job in jobs)
    finally:
        scheduler.schedule.clear()
