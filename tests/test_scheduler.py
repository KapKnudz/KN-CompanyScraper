from datetime import time
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


def test_configure_schedule_adds_news_and_nightly_borsdata_jobs(monkeypatch):
    monkeypatch.setattr(scheduler.config, "SCRAPE_INTERVAL_MINUTES", 30)
    monkeypatch.setattr(scheduler.config, "BORSDATA_SYNC_TIME", "02:00")
    monkeypatch.setattr(scheduler.config, "BORSDATA_INSIDER_SYNC_TIME", "03:00")
    scheduler.schedule.clear()

    try:
        scheduler.configure_schedule()
        jobs = scheduler.schedule.get_jobs()

        assert len(jobs) == 3
        assert any(job.job_func.func is scheduler.run_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_borsdata_once for job in jobs)
        assert any(job.job_func.func is scheduler.run_borsdata_insiders_once for job in jobs)
        assert any(job.at_time == time(2, 0) for job in jobs)
        assert any(job.at_time == time(3, 0) for job in jobs)
    finally:
        scheduler.schedule.clear()
