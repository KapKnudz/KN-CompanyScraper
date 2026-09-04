from unittest.mock import MagicMock, call

import pytest
import requests

from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.borsdata.stock_price import StockPrice
from datetime import date
from kncompanyscraper.models.company import Company
from kncompanyscraper.repositories.valuation_repository import ValuationRepository
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.borsdata.report import InstrumentReportBundle


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
    bundle = InstrumentReportBundle(700, tuple(reports), (), ())
    client.get_report_bundles.return_value = {700: bundle}
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
    service.sync_company(company, bundle)

    client.get_report_bundles.assert_not_called()
    client.get_stock_price.assert_called_once_with(700)
    financial_repository.save_report_bundle.assert_called_once_with(7, bundle)
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
    client.get_report_bundles.return_value = {
        700: InstrumentReportBundle(700, (), (), ())
    }
    client.get_stock_price.return_value = []
    client.get_dividends.return_value = {700: []}
    client.get_kpis.side_effect = lambda instrument_id, kpi_id: Kpi(kpi_id, str(kpi_id), 12.5)
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = None

    BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    ).sync_company(company, client.get_report_bundles.return_value[700])

    saved_kpis = [call.args[1] for call in valuation_repository.save_snapshot.call_args_list]
    assert saved_kpis[-len(expected_kpis):] == list(expected_kpis)


def test_sync_company_does_not_overwrite_snapshot_when_api_value_is_missing():
    company = make_company()
    client = MagicMock()
    client.get_report_bundles.return_value = {
        700: InstrumentReportBundle(700, (), (), ())
    }
    client.get_stock_price.return_value = []
    client.get_dividends.return_value = {700: []}
    client.get_kpis.return_value = None
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = None

    service = BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    )
    service.sync_company(company, client.get_report_bundles.return_value[700])

    valuation_repository.save_snapshot.assert_not_called()


def test_refresh_kpis_treats_unavailable_sector_kpi_as_missing():
    company = make_company(branch_id=75)
    client = MagicMock()
    unavailable = requests.Response()
    unavailable.status_code = 400

    def get_kpi(instrument_id, kpi_id):
        if kpi_id == KpiIds.PROPERTY_NAV:
            raise requests.HTTPError("unsupported KPI", response=unavailable)
        return Kpi(kpi_id, str(kpi_id), 12.5)

    client.get_kpis.side_effect = get_kpi
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(
        kpi_id, []
    )
    valuation_repository = MagicMock()

    result = BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    ).refresh_kpis([company])

    assert result == {
        7: len(ValuationRepository.CURRENT_KPIS) + len(KpiIds.PROPERTY_KPIS) - 1
    }
    assert call(700, KpiIds.PROPERTY_PRICE_TO_INCOME) in client.get_kpis.call_args_list
    assert call(7, KpiIds.PROPERTY_NAV, 12.5) not in (
        saved_call.args for saved_call in valuation_repository.save_snapshot.call_args_list
    )


def test_refresh_kpis_keeps_non_400_sector_failure_fatal():
    company = make_company(branch_id=68)
    client = MagicMock()
    failed = requests.Response()
    failed.status_code = 500

    def get_kpi(instrument_id, kpi_id):
        if kpi_id == KpiIds.BANK_COST_INCOME:
            raise requests.HTTPError("server failure", response=failed)
        return Kpi(kpi_id, str(kpi_id), 12.5)

    client.get_kpis.side_effect = get_kpi
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(
        kpi_id, []
    )

    with pytest.raises(requests.HTTPError, match="server failure"):
        BorsdataIngestionService(
            client, MagicMock(), MagicMock(), MagicMock()
        ).refresh_kpis([company])


def test_sync_company_labels_converted_reports_with_listing_currency():
    company = make_company()
    company.currency = "SEK"
    report = MagicMock(currency="USD")
    client = MagicMock()
    bundle = InstrumentReportBundle(700, (report,), (), ())
    client.get_report_bundles.return_value = {700: bundle}
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
    ).sync_company(company, bundle)

    assert report.currency == "USD"
    financial_repository.save_report_bundle.assert_called_once_with(7, bundle)


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


def test_targeted_price_refresh_requests_only_mutable_window_for_selected_company():
    company = make_company()
    client = MagicMock()
    client.get_stock_price.return_value = [StockPrice(date(2026, 8, 1), 100.0)]
    valuation_repository = MagicMock()

    result = BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    ).refresh_prices([company])

    assert result == {7: 1}
    client.get_stock_price.assert_called_once_with(700, max_count=130)
    valuation_repository.save_stock_prices.assert_called_once_with(
        7, client.get_stock_price.return_value, None
    )


def test_targeted_refresh_methods_preserve_explicit_company_scope():
    first = make_company(7, 700)
    second = make_company(8, 800)
    client = MagicMock()
    client.get_stock_price.return_value = []
    valuation_repository = MagicMock()
    valuation_repository.get_stock_price_bounds.return_value = (
        date(2020, 1, 1),
        date(2026, 8, 1),
    )
    client.get_dividends.side_effect = lambda ids: {ids[0]: []}
    client.get_kpis.return_value = None
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(
        kpi_id, []
    )
    service = BorsdataIngestionService(
        client, MagicMock(), valuation_repository, MagicMock()
    )

    service.refresh_prices([first, second])
    service.refresh_dividends([first, second])
    service.refresh_kpis([first, second])

    assert [call.args[0] for call in client.get_stock_price.call_args_list] == [700, 800]
    assert [call.args[0] for call in client.get_dividends.call_args_list] == [[700], [800]]
    assert all(
        call.args[0] in (700, 800)
        for call in client.get_kpis.call_args_list
    )
