from unittest.mock import MagicMock

from kncompanyscraper.jobs.borsdata_job import BorsdataJob
from kncompanyscraper.models.company import Company


def make_company(company_id: int, name: str) -> Company:
    return Company(
        id=company_id,
        name=name,
        ticker=name.upper(),
        mfn_slug=None,
        borsdata_id=company_id * 10,
        last_updated=None,
    )


def test_job_records_results_and_continues_after_company_failure():
    first = make_company(1, "First")
    broken = make_company(2, "Broken")
    last = make_company(3, "Last")
    ingestion_service = MagicMock()
    ingestion_service.sync_company.side_effect = [None, RuntimeError("API error"), None]
    job_repository = MagicMock()
    job_repository.start.side_effect = [101, 102, 103]

    result = BorsdataJob(ingestion_service, job_repository).run([first, broken, last])

    assert result.synced == 2
    assert result.failed == 1
    assert result.attempted == 3
    assert result.failures == ("Broken: API error",)
    assert ingestion_service.sync_company.call_count == 3
    job_repository.complete.assert_any_call(101, {"borsdata_id": 10})
    job_repository.complete.assert_any_call(103, {"borsdata_id": 30})
    job_repository.fail.assert_called_once_with(102, "API error")
