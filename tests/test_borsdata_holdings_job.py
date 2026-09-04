from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.jobs.borsdata_holdings_job import BorsdataHoldingsJob
from kncompanyscraper.models.company import Company
from kncompanyscraper.models.ownership_flow import (
    HoldingsInstrumentResult,
    ShortInterestSnapshot,
)


def company(company_id):
    return Company(company_id, f"Company {company_id}", f"C{company_id}", None,
                   company_id * 10, None)


def short(instrument_id):
    return ShortInterestSnapshot(
        instrument_id, 1.0, 2.0, None, None, None, None, None, None,
        None, None, None, None, None, {},
    )


def test_fetches_shorts_once_and_buybacks_in_batches():
    companies = [company(value) for value in range(1, 52)]
    client = MagicMock()
    client.get_shorts.return_value = {10: short(10)}
    client.get_buybacks.side_effect = lambda ids: {
        value: HoldingsInstrumentResult(value) for value in ids
    }
    repository = MagicMock()
    repository.save_buybacks.return_value = 0
    jobs = MagicMock()
    jobs.start.side_effect = range(100, 151)

    result = BorsdataHoldingsJob(client, repository, jobs).run(
        companies, date(2026, 8, 31)
    )

    assert result.synced == 51
    assert result.short_snapshots == 1
    client.get_shorts.assert_called_once_with()
    assert client.get_buybacks.call_count == 2
    repository.save_short_snapshot.assert_called_once_with(
        1, date(2026, 8, 31), client.get_shorts.return_value[10]
    )


def test_per_instrument_error_is_not_persisted_as_empty_coverage():
    client = MagicMock()
    client.get_shorts.return_value = {}
    client.get_buybacks.return_value = {
        10: HoldingsInstrumentResult(10, error="NOT_ACTIVE")
    }
    repository = MagicMock()
    jobs = MagicMock()
    jobs.start.return_value = 100

    result = BorsdataHoldingsJob(client, repository, jobs).run([company(1)])

    assert result.failed == 1
    repository.save_buybacks.assert_not_called()
    jobs.fail.assert_called_once_with(
        100,
        "buybacks: NOT_ACTIVE",
        {
            "borsdata_id": 10,
            "coverage": {"buybacks": "failed", "shorts": "unknown"},
        },
    )


def test_failed_buyback_batch_does_not_discard_earlier_batch():
    companies = [company(value) for value in range(1, 52)]
    client = MagicMock()
    client.get_shorts.return_value = {}
    client.get_buybacks.side_effect = [
        {value: HoldingsInstrumentResult(value) for value in range(10, 501, 10)},
        RuntimeError("provider unavailable"),
    ]
    repository = MagicMock()
    repository.save_buybacks.return_value = 0
    jobs = MagicMock()
    jobs.start.side_effect = range(100, 151)

    result = BorsdataHoldingsJob(client, repository, jobs).run(companies)

    assert result.synced == 50
    assert result.failed == 1
    assert repository.save_buybacks.call_count == 50
    jobs.fail.assert_called_once()
    assert "buybacks: provider unavailable" in jobs.fail.call_args.args[1]


def test_one_company_persistence_failure_does_not_block_peer():
    client = MagicMock()
    client.get_shorts.return_value = {}
    client.get_buybacks.return_value = {
        10: HoldingsInstrumentResult(10),
        20: HoldingsInstrumentResult(20),
    }
    repository = MagicMock()
    repository.save_buybacks.side_effect = [RuntimeError("database error"), 0]
    jobs = MagicMock()
    jobs.start.side_effect = [100, 101]

    result = BorsdataHoldingsJob(client, repository, jobs).run(
        [company(1), company(2)]
    )

    assert result.synced == 1
    assert result.failed == 1
    assert repository.save_buybacks.call_count == 2
    jobs.complete.assert_called_once_with(
        101,
        {
            "borsdata_id": 20,
            "coverage": {"buybacks": "empty", "shorts": "unknown"},
        },
    )


def test_rejects_missing_identifiers_before_provider_requests():
    missing_local = company(1)
    missing_local.id = None
    missing_borsdata = company(2)
    missing_borsdata.borsdata_id = None
    jobs = MagicMock()
    jobs.start.side_effect = [100, 101]
    client = MagicMock()

    result = BorsdataHoldingsJob(client, MagicMock(), jobs).run(
        [missing_local, missing_borsdata]
    )

    assert result.failed == 2
    client.get_shorts.assert_not_called()
    client.get_buybacks.assert_not_called()
    assert jobs.fail.call_count == 2


def test_records_buyback_and_short_coverage_separately():
    client = MagicMock()
    client.get_shorts.return_value = {10: short(10)}
    client.get_buybacks.return_value = {10: HoldingsInstrumentResult(10)}
    jobs = MagicMock()
    jobs.start.return_value = 100

    BorsdataHoldingsJob(client, MagicMock(), jobs).run([company(1)])

    jobs.complete.assert_called_once_with(
        100,
        {
            "borsdata_id": 10,
            "coverage": {"buybacks": "empty", "shorts": "available"},
        },
    )
