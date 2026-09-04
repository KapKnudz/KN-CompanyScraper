from types import SimpleNamespace
from unittest.mock import MagicMock

from kncompanyscraper.analysis.company_refresh import CompanyRefreshService
from kncompanyscraper.models.company import Company
from kncompanyscraper.models.refresh import RefreshLimitation


def company(company_id):
    return Company(company_id, f"Company {company_id}", f"C{company_id}", None, company_id * 10, None)


def successful_services():
    ingestion = MagicMock()
    ingestion.refresh_reports.return_value = {}
    ingestion.refresh_prices.return_value = {1: 130}
    ingestion.refresh_dividends.return_value = {1: 0}
    ingestion.refresh_kpis.return_value = {1: 2}
    insider = MagicMock()
    insider.run.return_value = SimpleNamespace(synced=1, failed=0, inserted=0, failures=())
    holdings = MagicMock()
    holdings.run.return_value = SimpleNamespace(
        synced=1, failed=0, buyback_rows=0, short_snapshots=0, failures=()
    )
    evidence = MagicMock()
    evidence.sync_company_delta.return_value = SimpleNamespace(
        releases_added=0, documents_added=0
    )
    return ingestion, insider, holdings, evidence


def test_refresh_runs_every_domain_for_only_the_selected_company_and_then_models():
    ingestion, insider, holdings, evidence = successful_services()
    jobs = MagicMock()
    jobs.start.return_value = 91
    model = MagicMock()
    service = CompanyRefreshService(
        ingestion, insider, holdings, evidence, jobs, model_invoker=model
    )

    selected = company(1)
    result = service.refresh([selected])[0]

    assert result.blocked_before_model is False
    assert [domain.domain for domain in result.domains] == [
        "reports", "prices", "dividends", "kpis", "mfn", "insider", "holdings"
    ]
    for method in (
        ingestion.refresh_reports,
        ingestion.refresh_prices,
        ingestion.refresh_dividends,
        ingestion.refresh_kpis,
        insider.run,
        holdings.run,
    ):
        method.assert_called_once_with([selected])
    evidence.sync_company_delta.assert_called_once_with(selected)
    model.assert_called_once_with(selected, result)
    jobs.complete.assert_called_once()


def test_mandatory_failure_runs_no_model_call_and_remains_blocking():
    ingestion, insider, holdings, evidence = successful_services()
    ingestion.refresh_reports.side_effect = RuntimeError("reports unavailable")
    jobs = MagicMock()
    jobs.start.return_value = 92
    model = MagicMock()

    result = CompanyRefreshService(
        ingestion, insider, holdings, evidence, jobs, model_invoker=model
    ).refresh([company(1)])[0]

    assert result.blocked_before_model is True
    assert result.mandatory_failures[0].domain == "reports"
    model.assert_not_called()
    jobs.fail.assert_called_once()
    assert ingestion.refresh_prices.called
    assert ingestion.refresh_dividends.called
    assert ingestion.refresh_kpis.called
    assert evidence.sync_company_delta.called
    assert insider.run.called
    assert holdings.run.called


def test_optional_failure_is_a_typed_limitation_and_does_not_block_model():
    ingestion, insider, holdings, evidence = successful_services()
    insider.run.return_value = SimpleNamespace(
        synced=0, failed=1, inserted=0, failures=("provider timeout",)
    )
    jobs = MagicMock()
    jobs.start.return_value = 93
    model = MagicMock()

    result = CompanyRefreshService(
        ingestion, insider, holdings, evidence, jobs, model_invoker=model
    ).refresh([company(1)])[0]

    assert result.blocked_before_model is False
    assert result.limitations == (
        RefreshLimitation("insider", "provider timeout", result.limitations[0].attempted_at),
    )
    assert result.domains[5].status == "failed"
    assert result.domains[5].limitation == result.limitations[0]
    model.assert_called_once()
