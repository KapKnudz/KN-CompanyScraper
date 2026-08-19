from datetime import date
from unittest.mock import MagicMock, call

from kncompanyscraper.borsdata.dividend import CashDividend
from kncompanyscraper.jobs.borsdata_dividend_job import BorsdataDividendJob
from kncompanyscraper.models.company import Company


def company(company_id: int, instrument_id: int | None) -> Company:
    return Company(
        company_id,
        f"Company {company_id}",
        f"C{company_id}",
        None,
        instrument_id,
        None,
    )


def test_dividend_job_batches_and_certifies_price_history_window():
    companies = [company(index, 1000 + index) for index in range(1, 52)]
    client = MagicMock()
    client.get_dividends.side_effect = [
        {item.borsdata_id: [] for item in companies[:50]},
        {1051: [CashDividend(date(2026, 3, 2), 2.0, "SEK", 0)]},
    ]
    valuations = MagicMock()
    valuations.get_stock_price_bounds.return_value = (
        date(2010, 1, 4),
        date(2026, 8, 17),
    )
    dividends = MagicMock()

    result = BorsdataDividendJob(client, dividends, valuations).run(
        companies, as_of=date(2026, 8, 18)
    )

    assert result.synced == 51
    assert result.failed == 0
    assert client.get_dividends.call_args_list == [
        call([item.borsdata_id for item in companies[:50]]),
        call([1051]),
    ]
    assert dividends.replace_calendar.call_count == 51
    assert dividends.replace_calendar.call_args.kwargs == {
        "covered_from": date(2010, 1, 4),
        "covered_through": date(2026, 8, 18),
        "source": "borsdata:dividend_calendar",
    }


def test_dividend_job_keeps_omissions_and_missing_prices_visible():
    companies = [company(1, 1001), company(2, 1002), company(3, None)]
    client = MagicMock()
    client.get_dividends.return_value = {1001: []}
    valuations = MagicMock()
    valuations.get_stock_price_bounds.return_value = None

    result = BorsdataDividendJob(client, MagicMock(), valuations).run(companies)

    assert result.synced == 0
    assert result.failed == 3
    assert any("omitted instrument 1002" in failure for failure in result.failures)
    assert any("no stored stock-price history" in failure for failure in result.failures)
    assert any("missing Börsdata instrument ID" in failure for failure in result.failures)
