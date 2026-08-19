from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.benchmark_client import NasdaqBenchmarkHistory
from kncompanyscraper.jobs.benchmark_sync_job import BenchmarkSyncJob


def test_job_bootstraps_from_inception_and_stores_gross_total_return():
    client = MagicMock()
    client.get_omxs30gi.return_value = NasdaqBenchmarkHistory(
        [(date(2026, 8, 14), 670.0)],
        (),
    )
    repository = MagicMock()
    repository.get_latest_date.return_value = None
    repository.save_values.return_value = 1

    result = BenchmarkSyncJob(client, repository).run(as_of=date(2026, 8, 18))

    client.get_omxs30gi.assert_called_once_with(
        date(2006, 5, 23), date(2026, 8, 17)
    )
    repository.save_values.assert_called_once_with(
        "OMXS30GI",
        [(date(2026, 8, 14), 670.0)],
        return_basis="gross_total_return",
        source="Nasdaq Global Index Watch ExportHistory/OMXS30GI",
    )
    assert result.synced_count == 1


def test_job_refreshes_seven_day_overlap_and_preserves_diagnostics():
    client = MagicMock()
    client.get_omxs30gi.return_value = NasdaqBenchmarkHistory(
        [(date(2026, 8, 17), 671.0)],
        (date(2026, 8, 16),),
    )
    repository = MagicMock()
    repository.get_latest_date.return_value = date(2026, 8, 15)
    repository.save_values.return_value = 1

    result = BenchmarkSyncJob(client, repository).run(as_of=date(2026, 8, 18))

    client.get_omxs30gi.assert_called_once_with(
        date(2026, 8, 8), date(2026, 8, 17)
    )
    assert result.requested_from == date(2026, 8, 8)
    assert result.omitted_zero_dates == (date(2026, 8, 16),)
