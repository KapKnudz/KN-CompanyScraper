from unittest.mock import MagicMock, call

import pytest

from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.borsdata.stock_price import StockPrice
from datetime import date
from kncompanyscraper.models.company import Company
from kncompanyscraper.repositories.valuation_repository import ValuationRepository
from kncompanyscraper.borsdata.kpi_ids import KpiIds


def make_company(company_id=7, borsdata_id=700, branch_id=None):
    return Company(
        id=company_id,
        name="Test Company",
        ticker="TEST",
        mfn_slug=None,
        borsdata_id=borsdata_id,
        last_updated=None,
        branch_id=branch_id,
    )


def test_sync_company_persists_reports_and_valuation_inputs():
    company = make_company()
    reports = [MagicMock()]
    client = MagicMock()
    client.get_reports.side_effect = [reports, [], []]
    stock_prices = [StockPrice(date(2026, 8, 1), 100.0)]
    client.get_stock_price.return_value = stock_prices
    client.get_dividends.return_value = {700: []}
    client.get_kpis.side_effect = lambda instrument_id, kpi_id: Kpi(kpi_id, str(kpi_id), 12.5)
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    financial_repository = MagicMock()
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = (
        date(2020, 1, 2),
        date(2026, 8, 1),
    )
    dividend_repository = MagicMock()

    service = BorsdataIngestionService(
        client, financial_repository, valuation_repository, dividend_repository
    )
    service.sync_company(company)

    assert client.get_reports.call_args_list == [
        call(700, report_type="year"),
        call(700, report_type="r12"),
        call(700, report_type="quarter"),
    ]
    client.get_stock_price.assert_called_once_with(700)
    assert financial_repository.save_reports.call_args_list == [
        call(7, "year", reports),
        call(7, "r12", []),
        call(7, "quarter", []),
    ]
    valuation_repository.save_stock_prices.assert_called_once_with(7, stock_prices, None)
    client.get_dividends.assert_called_once_with([700])
    dividend_repository.replace_calendar.assert_called_once()
    dividend_call = dividend_repository.replace_calendar.call_args
    assert dividend_call.args == (7, [])
    assert dividend_call.kwargs["covered_from"] == date(2020, 1, 2)
    assert dividend_call.kwargs["source"] == "borsdata:dividend_calendar"
    assert valuation_repository.save_snapshot.call_count == len(ValuationRepository.CURRENT_KPIS)
    assert valuation_repository.save_history.call_count == (
        len(ValuationRepository.HISTORICAL_KPIS)
        + len(KpiIds.GENERAL_FUNDAMENTAL_KPIS)
    )
    assert [
        history_call.args[1]
        for history_call in client.get_kpi_history.call_args_list
    ] == [
        *ValuationRepository.HISTORICAL_KPIS,
        *KpiIds.GENERAL_FUNDAMENTAL_KPIS,
    ]


@pytest.mark.parametrize(
    ("branch_id", "expected_kpis"),
    [
        (75, KpiIds.PROPERTY_KPIS),
        (68, KpiIds.BANK_KPIS),
        (69, KpiIds.BANK_KPIS),
        (70, KpiIds.BANK_KPIS),
    ],
)
def test_sync_company_persists_sector_kpis(branch_id, expected_kpis):
    company = make_company(branch_id=branch_id)
    client = MagicMock()
    client.get_reports.return_value = []
    client.get_stock_price.return_value = []
    client.get_dividends.return_value = {700: []}
    client.get_kpis.side_effect = lambda instrument_id, kpi_id: Kpi(kpi_id, str(kpi_id), 12.5)
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = None

    BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    ).sync_company(company)

    saved_kpis = [call.args[1] for call in valuation_repository.save_snapshot.call_args_list]
    assert saved_kpis[-len(expected_kpis):] == list(expected_kpis)


def test_sync_company_does_not_overwrite_snapshot_when_api_value_is_missing():
    company = make_company()
    client = MagicMock()
    client.get_reports.return_value = []
    client.get_stock_price.return_value = []
    client.get_dividends.return_value = {700: []}
    client.get_kpis.return_value = None
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = None

    service = BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    )
    service.sync_company(company)

    valuation_repository.save_snapshot.assert_not_called()


def test_sync_company_labels_converted_reports_with_listing_currency():
    company = make_company()
    company.currency = "SEK"
    report = MagicMock(currency="USD")
    client = MagicMock()
    client.get_reports.side_effect = [[report], [], []]
    client.get_stock_price.return_value = []
    client.get_dividends.return_value = {700: []}
    client.get_kpis.return_value = None
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    financial_repository = MagicMock()
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = None

    BorsdataIngestionService(
        client,
        financial_repository,
        valuation_repository,
        MagicMock(),
    ).sync_company(company)

    assert report.currency == "SEK"
    assert financial_repository.save_reports.call_args_list[0].args == (7, "year", [report])


@pytest.mark.parametrize(
    "company",
    [make_company(company_id=None), make_company(borsdata_id=None)],
)
def test_sync_company_requires_both_identifiers(company):
    service = BorsdataIngestionService(
        MagicMock(), MagicMock(), MagicMock(), MagicMock()
    )

    with pytest.raises(ValueError, match="both id and borsdata_id"):
        service.sync_company(company)
