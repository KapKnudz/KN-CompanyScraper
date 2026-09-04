from datetime import date
from unittest.mock import MagicMock

from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.jobs.borsdata_liquidity_job import (
    BorsdataLiquidityBackfillJob,
)
from kncompanyscraper.models.company import Company


def company(company_id, borsdata_id=None):
    return Company(
        company_id,
        f"Company {company_id}",
        f"C{company_id}",
        None,
        borsdata_id if borsdata_id is not None else company_id * 10,
        None,
    )


def test_backfill_records_successes_failures_and_retry_requirements():
    client = MagicMock()
    prices = [StockPrice(date(2026, 8, 29), 42, volume=1000)]
    client.get_stock_price.side_effect = [prices, RuntimeError("provider timeout")]
    repository = MagicMock()
    jobs = MagicMock()
    jobs.start.side_effect = [101, 102]

    result = BorsdataLiquidityBackfillJob(client, repository, jobs).run(
        [company(1), company(2)]
    )

    assert (result.requested, result.synced, result.failed, result.price_rows) == (
        2,
        1,
        1,
        1,
    )
    repository.save_stock_prices.assert_called_once_with(1, prices, None)
    jobs.complete.assert_called_once_with(
        101,
        {
            "borsdata_id": 10,
            "coverage": "available",
            "price_rows": 1,
            "retry_required": False,
        },
    )
    jobs.fail.assert_called_once_with(
        102,
        "provider timeout",
        {
            "borsdata_id": 20,
            "coverage": "failed",
            "retry_required": True,
        },
    )


def test_backfill_records_confirmed_empty_price_response():
    client = MagicMock()
    client.get_stock_price.return_value = []
    jobs = MagicMock()
    jobs.start.return_value = 101

    result = BorsdataLiquidityBackfillJob(client, MagicMock(), jobs).run([company(1)])

    assert result.synced == 1
    jobs.complete.assert_called_once_with(
        101,
        {
            "borsdata_id": 10,
            "coverage": "empty",
            "price_rows": 0,
            "retry_required": False,
        },
    )


def test_targeted_backfill_limits_price_request_without_deleting_old_history():
    client = MagicMock()
    client.get_stock_price.return_value = []
    repository = MagicMock()
    jobs = MagicMock()
    jobs.start.return_value = 101

    BorsdataLiquidityBackfillJob(client, repository, jobs).run(
        [company(1)], max_count=130
    )

    client.get_stock_price.assert_called_once_with(10, max_count=130)
    repository.save_stock_prices.assert_called_once_with(1, [], None)
