from unittest.mock import MagicMock

from kncompanyscraper.jobs.borsdata_insider_job import BorsdataInsiderJob
from kncompanyscraper.models.company import Company


def make_company(company_id: int) -> Company:
    return Company(
        id=company_id,
        name=f"Company {company_id}",
        ticker=f"C{company_id}",
        mfn_slug=None,
        borsdata_id=company_id * 10,
        last_updated=None,
    )


def test_insider_job_batches_requests_and_records_company_results():
    companies = [make_company(company_id) for company_id in range(1, 52)]
    client = MagicMock()
    client.get_insider_transactions.side_effect = lambda ids: {instrument_id: [] for instrument_id in ids}
    insider_repository = MagicMock()
    insider_repository.save_all.return_value = 0
    job_repository = MagicMock()
    job_repository.start.side_effect = range(100, 151)

    result = BorsdataInsiderJob(client, insider_repository, job_repository).run(companies)

    assert result.synced == 51
    assert result.failed == 0
    assert result.inserted == 0
    assert client.get_insider_transactions.call_count == 2
    assert len(client.get_insider_transactions.call_args_list[0].args[0]) == 50
    assert len(client.get_insider_transactions.call_args_list[1].args[0]) == 1
    assert job_repository.complete.call_count == 51


def test_insider_job_isolates_company_persistence_failure():
    companies = [make_company(1), make_company(2)]
    client = MagicMock()
    client.get_insider_transactions.return_value = {10: [], 20: []}
    insider_repository = MagicMock()
    insider_repository.save_all.side_effect = [RuntimeError("database error"), 3]
    job_repository = MagicMock()
    job_repository.start.side_effect = [101, 102]

    result = BorsdataInsiderJob(client, insider_repository, job_repository).run(companies)

    assert result.synced == 1
    assert result.failed == 1
    assert result.inserted == 3
    assert result.failures == ("Company 1: database error",)
    job_repository.fail.assert_called_once_with(101, "database error")
    job_repository.complete.assert_called_once_with(
        102,
        {"borsdata_id": 20, "transactions_inserted": 3},
    )
