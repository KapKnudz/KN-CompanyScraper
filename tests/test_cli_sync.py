import argparse
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.cli import sync


@pytest.mark.parametrize(
    ("command", "handler"),
    [
        ("map-borsdata", sync._cmd_map_borsdata),
        ("sync-borsdata", sync._cmd_sync_borsdata),
        ("sync-fundamental-history", sync._cmd_sync_fundamental_history),
        ("sync-borsdata-insiders", sync._cmd_sync_borsdata_insiders),
        ("sync-borsdata-holdings", sync._cmd_sync_borsdata_holdings),
        ("backfill-borsdata-liquidity", sync._cmd_backfill_borsdata_liquidity),
        ("report-ownership-liquidity", sync._cmd_report_ownership_liquidity),
        ("sync-borsdata-dividends", sync._cmd_sync_borsdata_dividends),
    ],
)
def test_sync_commands_register_handlers(command, handler):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    sync.register(subparsers)

    assert parser.parse_args([command]).func is handler


def test_sync_borsdata_uses_current_ingestion_service_dependencies(capsys):
    companies = [SimpleNamespace(id=1, name="Test", ticker="TST")]
    result = SimpleNamespace(synced=1, failed=0, failures=())

    with (
        patch("kncompanyscraper.borsdata.client.BorsdataClient") as client,
        patch("kncompanyscraper.borsdata.ingestion.BorsdataIngestionService") as service,
        patch("kncompanyscraper.jobs.borsdata_job.BorsdataJob") as job,
        patch("kncompanyscraper.repositories.company_repository.CompanyRepository") as companies_repo,
        patch("kncompanyscraper.repositories.dividend_repository.DividendRepository") as dividends,
        patch("kncompanyscraper.repositories.financial_repository.FinancialRepository") as financials,
        patch("kncompanyscraper.repositories.job_repository.JobRepository") as jobs,
        patch("kncompanyscraper.repositories.valuation_repository.ValuationRepository") as valuations,
    ):
        companies_repo.return_value.get_active_companies.return_value = companies
        job.return_value.run.return_value = result
        sync._cmd_sync_borsdata(SimpleNamespace())

    service.assert_called_once_with(
        client.return_value,
        financials.return_value,
        valuations.return_value,
        dividends.return_value,
    )
    job.assert_called_once_with(service.return_value, jobs.return_value)
    job.return_value.run.assert_called_once_with(companies)
    assert "1 synced, 0 failed" in capsys.readouterr().out


def test_sync_fundamental_history_calls_current_service_method(capsys):
    companies = [SimpleNamespace(id=1, ticker="TST")]

    with (
        patch("kncompanyscraper.borsdata.client.BorsdataClient") as client,
        patch("kncompanyscraper.borsdata.ingestion.BorsdataIngestionService") as service,
        patch("kncompanyscraper.repositories.company_repository.CompanyRepository") as companies_repo,
        patch("kncompanyscraper.repositories.dividend_repository.DividendRepository") as dividends,
        patch("kncompanyscraper.repositories.financial_repository.FinancialRepository") as financials,
        patch("kncompanyscraper.repositories.valuation_repository.ValuationRepository") as valuations,
    ):
        companies_repo.return_value.get_active_companies.return_value = companies
        sync._cmd_sync_fundamental_history(SimpleNamespace())

    service.assert_called_once_with(
        client.return_value,
        financials.return_value,
        valuations.return_value,
        dividends.return_value,
    )
    service.return_value.sync_general_fundamental_history.assert_called_once_with(
        companies[0]
    )
    assert "1 synced, 0 failed" in capsys.readouterr().out


def test_sync_borsdata_holdings_uses_composition_factory(capsys):
    companies = [SimpleNamespace(id=1)]
    result = SimpleNamespace(
        synced=1,
        failed=0,
        buyback_rows=2,
        short_snapshots=1,
        failures=(),
    )
    with (
        patch("kncompanyscraper.composition.build_borsdata_holdings_job") as factory,
        patch(
            "kncompanyscraper.repositories.company_repository.CompanyRepository"
        ) as companies_repo,
    ):
        companies_repo.return_value.get_active_companies.return_value = companies
        factory.return_value.run.return_value = result
        sync._cmd_sync_borsdata_holdings(SimpleNamespace())

    factory.return_value.run.assert_called_once_with(companies)
    assert "1 synced, 0 failed, 2 buyback rows, 1 short snapshots" in capsys.readouterr().out


def test_ownership_liquidity_report_prints_json(capsys):
    report = SimpleNamespace(to_dict=lambda: {"as_of": "2026-08-31", "counts": {}})
    with (
        patch(
            "kncompanyscraper.analysis.ownership_liquidity_coverage."
            "OwnershipLiquidityCoverageReport"
        ) as service,
        patch(
            "kncompanyscraper.repositories.company_repository.CompanyRepository"
        ) as companies,
        patch(
            "kncompanyscraper.repositories.ownership_flow_repository."
            "OwnershipFlowRepository"
        ) as repository,
    ):
        companies.return_value.get_active_companies.return_value = [
            SimpleNamespace(id=1)
        ]
        service.return_value.build.return_value = report
        sync._cmd_report_ownership_liquidity(
            SimpleNamespace(as_of="2026-08-31", stale_after_days=7)
        )

    service.assert_called_once_with(repository.return_value, stale_after_days=7)
    assert '"as_of": "2026-08-31"' in capsys.readouterr().out
