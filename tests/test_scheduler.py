from datetime import date, time
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper import scheduler


def test_run_borsdata_once_uses_active_companies_and_job():
    companies = [MagicMock()]

    with (
        patch.object(scheduler.repository, "get_active_companies", return_value=companies),
        patch("kncompanyscraper.scheduler.BorsdataClient"),
        patch("kncompanyscraper.scheduler.BorsdataInstrumentMappingService") as mapping,
        patch(
            "kncompanyscraper.composition.build_borsdata_ingestion_service"
        ) as ingestion_factory,
        patch("kncompanyscraper.scheduler.JobRepository") as job_repository,
        patch("kncompanyscraper.scheduler.BorsdataJob") as job,
    ):
        result = scheduler.run_borsdata_once()

    mapping.return_value.map_companies.assert_called_once_with(companies)
    ingestion_factory.assert_called_once_with()
    job.assert_called_once_with(
        ingestion_factory.return_value, job_repository.return_value
    )
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


def test_run_benchmark_sync_once_contains_job_failure():
    with (
        patch("kncompanyscraper.scheduler.NasdaqBenchmarkClient"),
        patch("kncompanyscraper.scheduler.BenchmarkRepository"),
        patch("kncompanyscraper.scheduler.BenchmarkSyncJob") as job,
        patch.object(scheduler.logger, "exception") as logger_exception,
    ):
        job.return_value.run.side_effect = RuntimeError("temporary failure")

        result = scheduler.run_benchmark_sync_once()

    assert result is None
    logger_exception.assert_called_once_with(
        "Scheduled %s failed; continuing.", "benchmark sync"
    )


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


def test_start_logs_scheduled_job_failure_and_continues(monkeypatch):
    monkeypatch.setattr(scheduler, "run_once", MagicMock())
    monkeypatch.setattr(scheduler, "configure_schedule", MagicMock())
    monkeypatch.setattr(
        scheduler.schedule,
        "run_pending",
        MagicMock(side_effect=[RuntimeError("temporary failure"), KeyboardInterrupt]),
    )
    monkeypatch.setattr(scheduler.time, "sleep", MagicMock())
    monkeypatch.setattr(scheduler.logger, "exception", MagicMock())

    with pytest.raises(KeyboardInterrupt):
        scheduler.start()

    assert scheduler.schedule.run_pending.call_count == 2
    scheduler.time.sleep.assert_called_once_with(1)
    scheduler.logger.exception.assert_called_once_with(
        "Scheduled job failed; continuing."
    )


def test_run_once_completes_scrape_run_with_counts():
    company = MagicMock()
    job = MagicMock()
    job.run.return_value = 3

    with (
        patch.object(scheduler.scrape_run_repository, "start", return_value=17),
        patch.object(scheduler.repository, "get_active_companies", return_value=[company]),
        patch("kncompanyscraper.scheduler.NewsJob", return_value=job),
        patch("kncompanyscraper.scheduler.JobRepository"),
        patch.object(scheduler.scrape_run_repository, "complete") as complete,
        patch.object(scheduler.scrape_run_repository, "fail") as fail,
    ):
        scheduler.run_once()

    complete.assert_called_once_with(17, "success", 1, 3)
    fail.assert_not_called()
    job.run.assert_called_once_with(company)


def test_run_once_marks_failure_and_preserves_partial_counts():
    company = MagicMock()
    job = MagicMock()
    job.run.side_effect = RuntimeError("scrape failed")

    with (
        patch.object(scheduler.scrape_run_repository, "start", return_value=18),
        patch.object(scheduler.repository, "get_active_companies", return_value=[company]),
        patch("kncompanyscraper.scheduler.NewsJob", return_value=job),
        patch("kncompanyscraper.scheduler.JobRepository"),
        patch.object(scheduler.scrape_run_repository, "complete") as complete,
        patch.object(scheduler.scrape_run_repository, "fail") as fail,
    ):
        with pytest.raises(RuntimeError, match="scrape failed"):
            scheduler.run_once()

    complete.assert_not_called()
    fail.assert_called_once_with(18, "scrape failed", 1, 0)
