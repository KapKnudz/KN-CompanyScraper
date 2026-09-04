import json
from pathlib import Path
from kncompanyscraper.logger import get_logger

logger = get_logger("cli.sync")


def register(subparsers):
    import_watchlist_parser = subparsers.add_parser(
        "import-watchlist", help="Import companies from a CSV file"
    )
    import_watchlist_parser.add_argument("--csv", required=True, type=Path)
    import_watchlist_parser.set_defaults(func=_cmd_import_watchlist)

    subparsers.add_parser(
        "map-borsdata", help="Map companies to Börsdata instruments"
    ).set_defaults(func=_cmd_map_borsdata)
    subparsers.add_parser(
        "sync-borsdata", help="Fetch and persist Börsdata inputs"
    ).set_defaults(func=_cmd_sync_borsdata)
    report_sync_parser = subparsers.add_parser(
        "sync-borsdata-reports", help="Backfill only Börsdata financial reports"
    )
    report_sync_parser.add_argument("--company-ids", type=int, nargs="+")
    report_sync_parser.set_defaults(func=_cmd_sync_borsdata_reports)
    subparsers.add_parser(
        "sync-fundamental-history", help="Backfill historical ROIC and net debt/EBITDA"
    ).set_defaults(func=_cmd_sync_fundamental_history)
    subparsers.add_parser(
        "sync-borsdata-insiders", help="Sync insider transactions from Börsdata"
    ).set_defaults(func=_cmd_sync_borsdata_insiders)
    subparsers.add_parser(
        "sync-borsdata-holdings", help="Sync buybacks and short interest from Börsdata"
    ).set_defaults(func=_cmd_sync_borsdata_holdings)
    subparsers.add_parser(
        "backfill-borsdata-liquidity",
        help="Backfill volume-bearing prices for active and backtest companies",
    ).set_defaults(func=_cmd_backfill_borsdata_liquidity)
    coverage_parser = subparsers.add_parser(
        "report-ownership-liquidity",
        help="Report active-universe ownership/liquidity coverage and freshness",
    )
    coverage_parser.add_argument("--as-of", help="Coverage cutoff date (YYYY-MM-DD)")
    coverage_parser.add_argument("--stale-after-days", type=int, default=7)
    coverage_parser.add_argument(
        "--summary-only", action="store_true", help="Omit per-company details"
    )
    coverage_parser.set_defaults(func=_cmd_report_ownership_liquidity)
    subparsers.add_parser(
        "sync-borsdata-dividends", help="Sync dividend calendar from Börsdata"
    ).set_defaults(func=_cmd_sync_borsdata_dividends)

    import_benchmark_parser = subparsers.add_parser(
        "import-benchmark-prices", help="Manual fallback for Nasdaq CSV export"
    )
    import_benchmark_parser.add_argument("--csv", required=True, type=Path)
    import_benchmark_parser.add_argument("--series-code", default="OMXS30GI")
    import_benchmark_parser.add_argument("--return-basis", default="gross_total_return")
    import_benchmark_parser.add_argument("--source", default="Manual CSV import")
    import_benchmark_parser.set_defaults(func=_cmd_import_benchmark_prices)

    sync_omx_parser = subparsers.add_parser(
        "sync-omxs30gi", help="Sync OMXS30GI history from Nasdaq"
    )
    sync_omx_parser.add_argument("--start-date", help="YYYY-MM-DD")
    sync_omx_parser.add_argument("--end-date", help="YYYY-MM-DD")
    sync_omx_parser.set_defaults(func=_cmd_sync_omxs30gi)


def _cmd_import_watchlist(args):
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.watchlist_import import WatchlistImportService

    try:
        result = WatchlistImportService(CompanyRepository()).import_file(args.csv)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"Imported {result.imported} watchlist companies "
        f"({result.created} created, {result.updated} updated)."
    )


def _cmd_map_borsdata(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.borsdata.instrument_mapping import (
        BorsdataInstrumentMappingService,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository

    company_repo = CompanyRepository()
    companies = company_repo.get_active_companies()
    result = BorsdataInstrumentMappingService(BorsdataClient(), company_repo).map_companies(
        companies
    )

    print(f"Mapped {result.mapped} companies to Börsdata instruments.")
    if result.unresolved:
        print(f"Unresolved: {', '.join(result.unresolved)}")


def _cmd_sync_borsdata(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_job import BorsdataJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.job_repository import JobRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.composition import build_borsdata_ingestion_service

    companies = CompanyRepository().get_active_companies()
    result = BorsdataJob(
        build_borsdata_ingestion_service(),
        JobRepository(),
    ).run(companies)
    print(
        f"Börsdata sync complete: {result.synced} synced, "
        f"{result.failed} failed."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_sync_borsdata_reports(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository

    company_repository = CompanyRepository()
    if args.company_ids:
        companies = [
            company_repository.get_by_id(company_id)
            for company_id in args.company_ids
        ]
        missing = [
            company_id
            for company_id, company in zip(args.company_ids, companies)
            if company is None
        ]
        if missing:
            raise SystemExit(
                "Unknown company ID(s): " + ", ".join(str(value) for value in missing)
            )
    else:
        companies = company_repository.get_active_companies()

    eligible = [
        company for company in companies
        if company.id is not None and company.borsdata_id is not None
    ]
    client = BorsdataClient()
    repository = FinancialRepository()
    synced = 0
    failures = []
    for offset in range(0, len(eligible), 50):
        batch = eligible[offset : offset + 50]
        try:
            bundles = client.get_report_bundles(
                [company.borsdata_id for company in batch]
            )
        except Exception as exc:
            failures.extend(f"{company.name}: {exc}" for company in batch)
            continue
        for company in batch:
            bundle = bundles[company.borsdata_id]
            if bundle.error:
                failures.append(f"{company.name}: {bundle.error}")
                continue
            try:
                repository.save_report_bundle(company.id, bundle)
            except Exception as exc:
                failures.append(f"{company.name}: {exc}")
            else:
                synced += 1

    skipped = len(companies) - len(eligible)
    print(
        f"Börsdata report sync complete: {synced} synced, "
        f"{len(failures) + skipped} failed, {len(companies)} attempted."
    )
    for failure in failures:
        print(f"  - {failure}")
    if skipped:
        print(f"  - {skipped} companies missing id or borsdata_id")


def _cmd_sync_fundamental_history(args):
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.composition import build_borsdata_ingestion_service

    company_repository = CompanyRepository()
    service = build_borsdata_ingestion_service()
    companies = company_repository.get_active_companies()
    synced = 0
    failures = []
    for company in companies:
        try:
            service.sync_general_fundamental_history(company)
            synced += 1
        except Exception as exc:
            failures.append(f"{company.id} {company.ticker}: {exc}")
    print(
        f"Fundamental KPI history sync: {synced} synced, "
        f"{len(failures)} failed, {len(companies)} attempted."
    )
    for failure in failures:
        print(f"  - {failure}")


def _cmd_sync_borsdata_insiders(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_insider_job import BorsdataInsiderJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.job_repository import JobRepository

    companies = CompanyRepository().get_active_companies()
    result = BorsdataInsiderJob(
        BorsdataClient(),
        InsiderRepository(),
        JobRepository(),
    ).run(companies)
    print(
        f"Börsdata insider sync complete: {result.synced} synced, "
        f"{result.failed} failed, {result.inserted} transactions inserted."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_sync_borsdata_holdings(args):
    from kncompanyscraper.composition import build_borsdata_holdings_job
    from kncompanyscraper.repositories.company_repository import CompanyRepository

    result = build_borsdata_holdings_job().run(
        CompanyRepository().get_active_companies()
    )
    print(
        f"Börsdata holdings sync complete: {result.synced} synced, "
        f"{result.failed} failed, {result.buyback_rows} buyback rows, "
        f"{result.short_snapshots} short snapshots."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_backfill_borsdata_liquidity(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_liquidity_job import (
        BorsdataLiquidityBackfillJob,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.job_repository import JobRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    company_repository = CompanyRepository()
    companies_by_id = {
        company.id: company
        for company in (
            company_repository.get_active_companies()
            + company_repository.get_backtest_companies()
        )
        if company.id is not None
    }
    result = BorsdataLiquidityBackfillJob(
        BorsdataClient(), ValuationRepository(), JobRepository()
    ).run(list(companies_by_id.values()))
    print(
        f"Börsdata liquidity backfill complete: {result.synced} synced, "
        f"{result.failed} failed, {result.price_rows} price rows, "
        f"{result.requested} requested."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_report_ownership_liquidity(args):
    from datetime import date

    from kncompanyscraper.analysis.ownership_liquidity_coverage import (
        OwnershipLiquidityCoverageReport,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.ownership_flow_repository import (
        OwnershipFlowRepository,
    )

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    companies = CompanyRepository().get_active_companies()
    report = OwnershipLiquidityCoverageReport(
        OwnershipFlowRepository(), stale_after_days=args.stale_after_days
    ).build(companies, as_of=as_of)
    payload = report.to_dict()
    if getattr(args, "summary_only", False):
        payload.pop("companies")
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_sync_borsdata_dividends(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_dividend_job import BorsdataDividendJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.repositories.job_repository import JobRepository

    result = BorsdataDividendJob(
        BorsdataClient(),
        DividendRepository(),
        ValuationRepository(),
        JobRepository(),
    ).run(CompanyRepository().get_active_companies())
    print(
        f"Börsdata dividend sync complete: {result.synced} synced, "
        f"{result.failed} failed."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_import_benchmark_prices(args):
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository

    BenchmarkRepository().import_prices_csv(
        args.csv, args.series_code, args.return_basis, args.source
    )


def _cmd_sync_omxs30gi(args):
    from datetime import date
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository

    start = date.fromisoformat(args.start_date) if args.start_date else None
    end = date.fromisoformat(args.end_date) if args.end_date else None

    # Nasdaq sync uses the Börsdata client for the underlying HTTP session/backoff logic
    BenchmarkRepository().sync_omxs30gi(BorsdataClient(), start_date=start, end_date=end)
