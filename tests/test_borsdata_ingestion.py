from unittest.mock import MagicMock

import pytest

from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
from kncompanyscraper.borsdata.kpi import Kpi
from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.models.company import Company
from kncompanyscraper.repositories.valuation_repository import ValuationRepository


def make_company(company_id=7, borsdata_id=700):
    return Company(
        id=company_id,
        name="Test Company",
        ticker="TEST",
        mfn_slug=None,
        borsdata_id=borsdata_id,
        last_updated=None,
    )


def test_sync_company_persists_reports_and_valuation_inputs():
    company = make_company()
    reports = [MagicMock()]
    client = MagicMock()
    client.get_reports.return_value = reports
    client.get_kpis.side_effect = lambda instrument_id, kpi_id: Kpi(kpi_id, str(kpi_id), 12.5)
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    financial_repository = MagicMock()
    valuation_repository = MagicMock()

    service = BorsdataIngestionService(client, financial_repository, valuation_repository)
    service.sync_company(company)

    client.get_reports.assert_called_once_with(700, report_type="year")
    financial_repository.save_reports.assert_called_once_with(7, "year", reports)
    assert valuation_repository.save_snapshot.call_count == len(ValuationRepository.CURRENT_KPIS)
    assert valuation_repository.save_history.call_count == len(ValuationRepository.HISTORICAL_KPIS)


def test_sync_company_does_not_overwrite_snapshot_when_api_value_is_missing():
    company = make_company()
    client = MagicMock()
    client.get_reports.return_value = []
    client.get_kpis.return_value = None
    client.get_kpi_history.side_effect = lambda instrument_id, kpi_id, **kwargs: KpiHistory(kpi_id, [])
    valuation_repository = MagicMock()

    service = BorsdataIngestionService(client, MagicMock(), valuation_repository)
    service.sync_company(company)

    valuation_repository.save_snapshot.assert_not_called()


@pytest.mark.parametrize(
    "company",
    [make_company(company_id=None), make_company(borsdata_id=None)],
)
def test_sync_company_requires_both_identifiers(company):
    service = BorsdataIngestionService(MagicMock(), MagicMock(), MagicMock())

    with pytest.raises(ValueError, match="both id and borsdata_id"):
        service.sync_company(company)
