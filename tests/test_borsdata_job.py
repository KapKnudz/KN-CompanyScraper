from unittest.mock import MagicMock

from kncompanyscraper.jobs.borsdata_job import BorsdataJob
from kncompanyscraper.borsdata.report import InstrumentReportBundle
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
    ingestion_service.get_report_bundles.return_value = {
        10: InstrumentReportBundle(10, (), (), ()),
        20: InstrumentReportBundle(20, (), (), (), error="NOT_ACTIVE"),
        30: InstrumentReportBundle(30, (), (), ()),
    }
    ingestion_service.sync_company.side_effect = [None, RuntimeError("API error"), None]
    job_repository = MagicMock()
    job_repository.start.side_effect = [101, 102, 103]

    result = BorsdataJob(ingestion_service, job_repository).run([first, broken, last])

    assert result.synced == 2
    assert result.failed == 1
    assert result.attempted == 3
    assert result.failures == ("Broken: API error",)
    assert ingestion_service.get_report_bundles.call_args.args == ([10, 20, 30],)
    assert ingestion_service.sync_company.call_count == 3
    job_repository.complete.assert_any_call(101, {"borsdata_id": 10})
    job_repository.complete.assert_any_call(103, {"borsdata_id": 30})
    job_repository.fail.assert_called_once_with(102, "API error")


def test_job_fails_every_company_when_report_batch_request_fails():
    companies = [make_company(1, "First"), make_company(2, "Second")]
    ingestion_service = MagicMock()
    ingestion_service.get_report_bundles.side_effect = RuntimeError("HTTP error")
    job_repository = MagicMock()
    job_repository.start.side_effect = [101, 102]

    result = BorsdataJob(ingestion_service, job_repository).run(companies)

    assert result.synced == 0
    assert result.failed == 2
    assert job_repository.fail.call_args_list[0].args == (101, "HTTP error")
    assert job_repository.fail.call_args_list[1].args == (102, "HTTP error")
    ingestion_service.sync_company.assert_not_called()


def test_job_splits_report_requests_into_batches_of_fifty():
    companies = [make_company(index, f"Company {index}") for index in range(1, 53)]
    ingestion_service = MagicMock()
    ingestion_service.get_report_bundles.side_effect = lambda ids: {
        instrument_id: InstrumentReportBundle(instrument_id, (), (), ())
        for instrument_id in ids
    }
    job_repository = MagicMock()
    job_repository.start.side_effect = range(100, 152)

    result = BorsdataJob(ingestion_service, job_repository).run(companies)

    assert result.synced == 52
    assert [call.args[0] for call in ingestion_service.get_report_bundles.call_args_list] == [
        list(range(10, 510, 10)),
        [510, 520],
    ]
